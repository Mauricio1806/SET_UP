"""
City Sync v8 — atualiza bloco LIVE nas páginas de cidade do Notion.

Fix v8:
- Remove blocos LIVE antigos via API REST DIRETA (sem passar por Claude/Haiku)
  → antes: mandava prompt pro Haiku que respondia com código mas não executava
  → agora: faz GET /blocks/{page_id}/children + DELETE direto aqui no Python
- Links de aluguéis: usa a URL exata do pisos.com (já está correta no scraper)
- Tabela de preços: formato real com produto, preço, qty/mês (como era no v5)
- Bug diet_cost por cidade: cada cidade recebe o SEU custo calculado
- Filtros Idealista: URLs testadas e validadas por bairro
"""

import os
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION  = "2022-06-28"

CITY_PAGE_IDS = {
    "granada":  "3736d7bcf70c81fa99b6f425e9585326",
    "alicante": "3736d7bcf70c81cf80c9e70f08b9c264",
    "nerja":    "3736d7bcf70c816cbb7ac922c2c0138e",
}

CITY_NAMES = {
    "granada":  "Granada",
    "alicante": "Alicante",
    "nerja":    "Nerja",
}

PRIORITY_NEIGHBORHOODS = {
    "granada":  ["Zaidín", "Arabial", "Camino de Ronda", "Chana", "Beiro"],
    "alicante": ["Benalúa", "Carolinas", "Centro", "San Blas"],
    "nerja":    ["Centro", "Capistrano", "Parador"],
}

# URLs validadas manualmente — bairros que existem no Idealista
# Formato: /alquiler-viviendas/{slug}/{filtros}
IDEALISTA_FILTERS: Dict[str, List[tuple]] = {
    "granada": [
        ("Zaidín (MELHOR custo-benefício)",
         "https://www.idealista.com/alquiler-viviendas/zaidin-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ("Arabial / Pajaritos (4 academias)",
         "https://www.idealista.com/alquiler-viviendas/arabial-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ("Camino de Ronda",
         "https://www.idealista.com/alquiler-viviendas/camino-de-ronda-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ("Chana (mais barato)",
         "https://www.idealista.com/alquiler-viviendas/chana-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ("Beiro",
         "https://www.idealista.com/alquiler-viviendas/beiro-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
    ],
    "alicante": [
        ("Benalúa (MELHOR)",
         "https://www.idealista.com/alquiler-viviendas/benalua-alicante-alacant/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ("Carolinas Bajas",
         "https://www.idealista.com/alquiler-viviendas/carolinas-bajas-alicante-alacant/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ("Centro Alicante",
         "https://www.idealista.com/alquiler-viviendas/centro-alicante-alacant/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ("San Blas",
         "https://www.idealista.com/alquiler-viviendas/san-blas-alicante-alacant/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
    ],
    "nerja": [
        ("Centro Nerja",
         "https://www.idealista.com/alquiler-viviendas/nerja-malaga/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ("Capistrano / Burriana",
         "https://www.idealista.com/alquiler-viviendas/nerja-malaga/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
    ],
}

# Marcador de início/fim do bloco LIVE — usado para identificar e remover
LIVE_START_MARKER = "🔴 LIVE SET_UP"


class CitySyncNotion:
    def __init__(self, token: str):
        self.token = token.strip()
        self.headers = {
            "Authorization":  f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type":   "application/json",
        }

    def _get(self, path: str) -> dict:
        r = requests.get(f"{NOTION_API_BASE}{path}", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, payload: dict) -> dict:
        r = requests.patch(f"{NOTION_API_BASE}{path}",
                           headers=self.headers, json=payload, timeout=30)
        if r.status_code >= 400:
            print(f"    [notion {r.status_code}] {r.text[:150]}")
        r.raise_for_status()
        return r.json()

    def _delete(self, block_id: str) -> bool:
        """Deleta bloco e retorna True se bem-sucedido."""
        try:
            r = requests.delete(f"{NOTION_API_BASE}/blocks/{block_id}",
                                headers=self.headers, timeout=10)
            if r.status_code not in (200, 204):
                print(f"    [delete {r.status_code}] {block_id[:8]}: {r.text[:80]}")
                return False
            return True
        except Exception as e:
            print(f"    [delete erro] {block_id[:8]}: {e}")
            return False

    # ------------------------------------------------------------------
    # REMOÇÃO DE BLOCOS LIVE ANTIGOS — API REST DIRETA
    # ------------------------------------------------------------------

    def _remove_old_live_blocks(self, page_id: str) -> int:
        """
        Remove TODOS os blocos LIVE de qualquer posição na página.
        Varre com paginação completa — coleta IDs de tudo que é LIVE
        (callout com marcador + heading_3/bullets/divider imediatamente após),
        depois deleta em lote.
        """
        # 1. Coletar todos os blocos da página com paginação
        all_blocks = []
        cursor = None
        for _ in range(10):  # max 10 páginas = 500 blocos
            path = f"/blocks/{page_id}/children?page_size=50"
            if cursor:
                path += f"&start_cursor={cursor}"
            try:
                resp = self._get(path)
            except Exception as e:
                print(f"    [warn] GET blocos falhou: {e}")
                break
            all_blocks.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")

        print(f"    [remove] {len(all_blocks)} blocos encontrados na página")

        # 2. Identificar IDs a deletar — qualquer bloco dentro de um grupo LIVE
        to_delete = []
        in_live   = False

        for block in all_blocks:
            b_type = block.get("type", "")
            b_id   = block.get("id", "")

            if b_type == "callout":
                texts = block.get("callout", {}).get("rich_text", [])
                text  = "".join(t.get("text", {}).get("content", "") for t in texts)
                if LIVE_START_MARKER in text:
                    in_live = True
                    to_delete.append(b_id)
                    continue
                else:
                    in_live = False  # callout que não é LIVE encerra o grupo

            if in_live:
                if b_type in ("heading_3", "bulleted_list_item", "divider",
                              "paragraph", "table"):
                    to_delete.append(b_id)
                else:
                    in_live = False  # bloco desconhecido encerra o grupo

        print(f"    [remove] {len(to_delete)} blocos LIVE para deletar")

        # 3. Deletar em sequência com delay
        removed = 0
        for block_id in to_delete:
            if self._delete(block_id):
                removed += 1
            time.sleep(0.15)

        return removed

    # ------------------------------------------------------------------
    # BUILD BLOCOS LIVE
    # ------------------------------------------------------------------

    def _build_live_blocks(
        self,
        city_key: str,
        now: str,
        listings: List[Dict],
        prices: List[Dict],
        diet_cost: Dict,
    ) -> List[Dict]:
        blocks    = []
        city_name = CITY_NAMES[city_key]
        total_diet = diet_cost.get("total", 0)
        n_listings = len(listings)

        # ── Callout principal ──────────────────────────────────────────
        blocks.append({
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content":
                    f"🔴 LIVE SET_UP — {now}  |  {n_listings} anúncios  |  Dieta real: €{total_diet:.2f}/mês  |  Fonte: pisos.com"
                }}],
                "icon":  {"emoji": "🔴"},
                "color": "red_background",
            }
        })

        # ── Melhores aluguéis ─────────────────────────────────────────
        if listings:
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {
                    "content": f"🏠 Melhores aluguéis disponíveis agora — {city_name}"
                }}]}
            })

            priority = PRIORITY_NEIGHBORHOODS.get(city_key, [])
            sorted_listings = sorted(
                listings,
                key=lambda l: (
                    not any(nb.lower() in (l.get("location") or "").lower()
                            for nb in priority),
                    -(l.get("scores", {}).get("total", 0))
                )
            )[:8]

            for l in sorted_listings:
                price    = l.get("price", "?")
                loc      = (l.get("location") or "")[:30]
                score    = l.get("scores", {}).get("total", 0)
                url      = l.get("url", "")
                title    = (l.get("title") or "")[:55]

                sm_m     = l.get("nearest_supermarket_m")
                sm_name  = (l.get("nearest_supermarket_name") or "")[:12]
                gm_m     = l.get("nearest_gym_m")
                gm_name  = (l.get("nearest_gym_name") or "")[:12]

                sm_txt   = f"🛒 {sm_m}m {sm_name}" if sm_m else "🛒 ?"
                gm_txt   = f"💪 {gm_m}m {gm_name}" if gm_m else "💪 ?"
                kitchen  = l.get("kitchen_type", "")
                fogao    = " ✅fogão" if kitchen == "gas_or_full" else (
                           " 🍳cooktop" if kitchen == "cooktop_only" else "")

                line_prefix = f"€{price}/mês{fogao} · {loc} · {sm_txt} · {gm_txt} · {score:.0f}pt → "

                if url:
                    blocks.append({
                        "object": "block", "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": [
                            {"type": "text", "text": {"content": line_prefix}},
                            {"type": "text",
                             "text": {"content": title or "ver anúncio", "link": {"url": url}},
                             "annotations": {"color": "blue", "underline": True}},
                        ]}
                    })
                else:
                    blocks.append({
                        "object": "block", "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": [
                            {"type": "text", "text": {"content": line_prefix + (title or "")}}
                        ]}
                    })

        # ── Tabela de preços Mercadona ────────────────────────────────
        diet_items = diet_cost.get("items", [])
        if diet_items and total_diet > 0:
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {
                    "content": f"🛒 Preços Mercadona — Custo real da sua dieta: €{total_diet:.2f}/mês"
                }}]}
            })

            # Tabela Notion com 4 colunas
            table_rows = []

            # Header
            table_rows.append({
                "object": "block", "type": "table_row",
                "table_row": {"cells": [
                    [{"type": "text", "text": {"content": "Produto"}, "annotations": {"bold": True}}],
                    [{"type": "text", "text": {"content": "Preço"}, "annotations": {"bold": True}}],
                    [{"type": "text", "text": {"content": "Qty/mês"}, "annotations": {"bold": True}}],
                    [{"type": "text", "text": {"content": "Total"}, "annotations": {"bold": True}}],
                ]}
            })

            for item in diet_items:
                if item["found"]:
                    p_str = f"€{item['unit_price']:.2f}"
                    q_str = f"{item['qty']} {item['unit']}"
                    t_str = f"€{item['monthly_cost']:.2f}"
                    n_str = (item.get("product") or item["label"])[:45]
                else:
                    p_str = "—"
                    q_str = f"{item['qty']} {item['unit']}"
                    t_str = "—"
                    n_str = item["label"]

                table_rows.append({
                    "object": "block", "type": "table_row",
                    "table_row": {"cells": [
                        [{"type": "text", "text": {"content": n_str}}],
                        [{"type": "text", "text": {"content": p_str}}],
                        [{"type": "text", "text": {"content": q_str}}],
                        [{"type": "text", "text": {"content": t_str}}],
                    ]}
                })

            blocks.append({
                "object": "block", "type": "table",
                "table": {
                    "table_width": 4,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": table_rows,
                }
            })

        # ── Links Idealista por bairro ────────────────────────────────
        city_filters = IDEALISTA_FILTERS.get(city_key, [])
        if city_filters:
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {
                    "content": "🔍 Buscar agora no Idealista — por bairro (1 quarto mobilhado, preço crescente)"
                }}]}
            })
            for label, url in city_filters:
                blocks.append({
                    "object": "block", "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [
                        {"type": "text", "text": {"content": f"{label} → "}},
                        {"type": "text",
                         "text": {"content": "abrir no Idealista", "link": {"url": url}},
                         "annotations": {"color": "blue", "underline": True}},
                    ]}
                })

        # ── Divisor final ─────────────────────────────────────────────
        blocks.append({"object": "block", "type": "divider", "divider": {}})

        return blocks

    # ------------------------------------------------------------------
    # ORCHESTRATOR
    # ------------------------------------------------------------------

    def update_all_cities(
        self,
        ranked_listings: List[Dict],
        mercadona_prices: List[Dict],
        diet_costs: Dict,
    ):
        """Atualiza o bloco LIVE em cada página de cidade."""
        for city_key, page_id in CITY_PAGE_IDS.items():
            try:
                print(f"  → Atualizando {CITY_NAMES[city_key]}...")
                self._update_city_page(
                    city_key, page_id, ranked_listings, mercadona_prices, diet_costs
                )
                print(f"    ✓ {CITY_NAMES[city_key]} atualizada")
            except Exception as e:
                print(f"    [ERRO] {city_key}: {e}")

    def _update_city_page(
        self,
        city_key: str,
        page_id:  str,
        all_listings:  List[Dict],
        all_prices:    List[Dict],
        diet_costs:    Dict,
    ):
        # Filtrar por cidade
        city_listings = [l for l in all_listings if l.get("city") == city_key]
        city_prices   = [p for p in all_prices   if p.get("city") == city_key]
        diet_cost     = diet_costs.get(city_key, {"total": 0, "items": []})

        now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        # 1. Remover blocos LIVE antigos via API REST direta
        removed = self._remove_old_live_blocks(page_id)
        if removed:
            print(f"    {removed} blocos LIVE antigos removidos")
            time.sleep(0.5)

        # 2. Inserir novo LIVE no topo
        new_blocks = self._build_live_blocks(
            city_key, now, city_listings, city_prices, diet_cost
        )

        # Notion aceita max 100 blocos por request — chunk se necessário
        for i in range(0, len(new_blocks), 100):
            chunk = new_blocks[i:i+100]
            self._patch(f"/blocks/{page_id}/children", {"children": chunk})
            if i + 100 < len(new_blocks):
                time.sleep(0.3)
