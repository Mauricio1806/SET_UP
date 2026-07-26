"""
Diet Sync — lê a dieta real do Notion e cruza com preços reais do Mercadona.
Atualiza as páginas de cidade com:
1. Custo mensal real da dieta com preços do dia
2. Top aluguéis por bairro com distâncias reais
"""

import os
import json
from datetime import datetime, timezone
from typing import List, Dict
import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION  = "2022-06-28"

# IDs das páginas do Notion (do hub já existente)
DIET_PAGE_ID    = "38e6d7bcf70c81e2ad46f7d5b6a2fa42"
BAIRROS_PAGE_ID = "3726d7bcf70c81eba93ce3a57599d06c"
HUB_PAGE_ID     = "3736d7bcf70c81c09c0ff224c550e309"

# Bairros alvo por cidade (extraídos da análise existente)
TARGET_NEIGHBORHOODS = {
    "granada": ["Zaídín", "Camino de Ronda", "Chana", "Centro", "Beiro"],
    "alicante": ["Benalúa", "Carolinas", "Ensanche", "San Blas", "Centro"],
    "nerja": ["Centro", "Capistrano", "Parador"],
}

# Itens da dieta real com quantidades mensais (do Notion)
DIET_ITEMS_MONTHLY = {
    "pechuga pollo":            {"qty": 9.0,  "unit": "kg",  "label": "Frango peito"},
    "huevos xl":                {"qty": 8.0,  "unit": "dz",  "label": "Ovos M/L"},
    "claras huevo pasteurizadas":{"qty": 6.0, "unit": "un",  "label": "Claras pasteurizadas"},
    "arroz integral":           {"qty": 3.0,  "unit": "kg",  "label": "Arroz integral"},
    "patatas":                  {"qty": 6.0,  "unit": "kg",  "label": "Batata"},
    "pan integral rebanado":    {"qty": 4.0,  "unit": "un",  "label": "Pão integral"},
    "verduras congeladas":      {"qty": 3.0,  "unit": "kg",  "label": "Verdura congelada"},
    "mantequilla sin sal":      {"qty": 3.0,  "unit": "un",  "label": "Manteiga s/ sal"},
    "cacahuete tostado":        {"qty": 1.0,  "unit": "kg",  "label": "Amendoim"},
    "aceite oliva virgen extra": {"qty": 1.0, "unit": "L",   "label": "Azeite 1L"},
    "miel":                     {"qty": 0.5,  "unit": "kg",  "label": "Mel 500g"},
    "cafe molido":              {"qty": 1.2,  "unit": "kg",  "label": "Café molido"},
    "leche entera":             {"qty": 6.0,  "unit": "L",   "label": "Leite integral"},
    "leche en polvo":           {"qty": 3.0,  "unit": "un",  "label": "Leite em pó"},
    "salsa teriyaki":           {"qty": 1.0,  "unit": "frs", "label": "Molho teriyaki"},
    "ketchup":                  {"qty": 1.0,  "unit": "frs", "label": "Ketchup Heinz"},
}


class DietSyncNotion:
    def __init__(self, token: str, hub_id: str):
        self.token  = token.strip()
        self.hub_id = hub_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def post(self, path, payload):
        r = requests.post(f"{NOTION_API_BASE}{path}",
                          headers=self.headers, json=payload, timeout=30)
        if r.status_code >= 400:
            print(f"  [Notion erro] {r.status_code}: {r.text[:150]}")
        r.raise_for_status()
        return r.json()

    def patch(self, path, payload):
        r = requests.patch(f"{NOTION_API_BASE}{path}",
                           headers=self.headers, json=payload, timeout=30)
        if r.status_code >= 400:
            print(f"  [Notion erro] {r.status_code}: {r.text[:150]}")
        r.raise_for_status()
        return r.json()

    def get_children(self, page_id):
        r = requests.get(f"{NOTION_API_BASE}/blocks/{page_id}/children?page_size=100",
                         headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])

    # ------------------------------------------------------------------
    # CUSTO REAL DA DIETA
    # ------------------------------------------------------------------

    def calculate_diet_cost(self, mercadona_prices: List[Dict], city: str) -> Dict:
        """Cruza os itens da dieta com preços reais do Mercadona."""
        city_prices = {p["query"]: p for p in mercadona_prices if p.get("city") == city}
        results = []
        total = 0.0

        for query, meta in DIET_ITEMS_MONTHLY.items():
            price_data = city_prices.get(query, {})
            unit_price = price_data.get("price_eur")
            product_name = price_data.get("product_name", meta["label"])

            if unit_price:
                monthly_cost = round(unit_price * meta["qty"], 2)
                total += monthly_cost
                results.append({
                    "label":        meta["label"],
                    "product":      product_name,
                    "qty":          meta["qty"],
                    "unit":         meta["unit"],
                    "unit_price":   unit_price,
                    "monthly_cost": monthly_cost,
                    "found":        True,
                })
            else:
                results.append({
                    "label":      meta["label"],
                    "product":    meta["label"],
                    "qty":        meta["qty"],
                    "unit":       meta["unit"],
                    "unit_price": None,
                    "monthly_cost": None,
                    "found":      False,
                })

        return {
            "city":    city,
            "items":   results,
            "total":   round(total, 2),
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }

    # ------------------------------------------------------------------
    # MONTA BLOCO MARKDOWN PARA NOTION
    # ------------------------------------------------------------------

    def build_diet_callout(self, diet_cost: Dict, ranked_listings: List[Dict]) -> str:
        """Gera o conteúdo da seção Live a ser inserida nas páginas de cidade."""
        city     = diet_cost["city"]
        total    = diet_cost["total"]
        updated  = diet_cost["updated"]
        city_name = {"granada": "Granada", "alicante": "Alicante", "nerja": "Nerja"}.get(city, city)

        # Top listings desta cidade
        city_listings = [l for l in ranked_listings if l.get("city") == city][:5]

        lines = [
            f"## 🔴 LIVE — Atualizado em {updated}",
            "",
            f"### 🍳 Custo real da dieta este mês — {city_name}",
            "",
            "| Item | Produto | Qty/mês | €/un | Total € |",
            "|---|---|---|---|---|",
        ]

        for item in diet_cost["items"]:
            if item["found"]:
                lines.append(
                    f"| {item['label']} | {item['product'][:35]} | "
                    f"{item['qty']} {item['unit']} | "
                    f"€{item['unit_price']} | "
                    f"**€{item['monthly_cost']}** |"
                )
            else:
                lines.append(
                    f"| {item['label']} | *(sem preço hoje)* | "
                    f"{item['qty']} {item['unit']} | — | — |"
                )

        lines += [
            "",
            f"**🧾 TOTAL MENSAL COMIDA: €{total:.2f}**",
            "",
        ]

        if city_listings:
            lines += [
                f"### 🏠 Melhores aluguéis disponíveis agora — {city_name}",
                "",
                "| Score | Preço | Bairro | 🛒 Supermercado | 💪 Academia | Link |",
                "|---|---|---|---|---|---|",
            ]
            for l in city_listings:
                score = l.get("scores", {}).get("total", 0)
                price = l.get("price", "?")
                loc   = l.get("location", "")[:25]
                sm    = f"{l.get('nearest_supermarket_m','?')}m · {l.get('nearest_supermarket_name','')[:15]}" if l.get("nearest_supermarket_m") else "—"
                gm    = f"{l.get('nearest_gym_m','?')}m · {l.get('nearest_gym_name','')[:12]}" if l.get("nearest_gym_m") else "—"
                url   = l.get("url", "#")
                title = l.get("title", "")[:30]
                lines.append(
                    f"| {score:.0f}pt | **€{price}**/mês | {loc} | {sm} | {gm} | [ver]({url}) |"
                )
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # CRIA/ATUALIZA PÁGINA LIVE NO HUB
    # ------------------------------------------------------------------

    def upsert_live_page(self, all_diet_costs: List[Dict],
                         ranked_listings: List[Dict],
                         consolidados: List[Dict]):
        """Cria (ou atualiza) uma página 'Live Dashboard' no hub com tudo."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        content_parts = [
            f"> 🤖 Atualizado automaticamente por SET_UP — {now}",
            "> Dados em tempo real: preços Mercadona + melhores aluguéis por bairro.",
            "",
        ]

        for diet_cost in all_diet_costs:
            city = diet_cost["city"]
            listings = [l for l in ranked_listings if l.get("city") == city]
            content_parts.append(self.build_diet_callout(diet_cost, listings))
            content_parts.append("---")

        # Tabela de economia por mercado
        if consolidados:
            content_parts.append("## 💰 Economia com mix de mercados")
            content_parts.append("")
            content_parts.append("| Cidade | Tudo Mercadona | Mix otimizado | Economia/mês |")
            content_parts.append("|---|---|---|---|")
            for c in consolidados:
                content_parts.append(
                    f"| {c['city_name']} | €{c['total_mercadona']:.2f} "
                    f"| €{c['total_otimizado']:.2f} "
                    f"| **€{c['total_economy']:.2f}** ({c['pct_total_saved']}%) |"
                )
            content_parts.append("")

        content = "\n".join(content_parts)

        # Verifica se já existe página Live
        children = self.get_children(self.hub_id)
        live_page_id = None
        for block in children:
            if block.get("type") == "child_page":
                title = block.get("child_page", {}).get("title", "")
                if "LIVE" in title.upper() and "SET_UP" in title.upper():
                    live_page_id = block["id"]
                    break

        if live_page_id:
            print(f"  → Atualizando página Live existente ({live_page_id[:8]}...)")
            # Apaga conteúdo antigo e recria
            old_blocks = self.get_children(live_page_id)
            for block in old_blocks:
                requests.delete(
                    f"{NOTION_API_BASE}/blocks/{block['id']}",
                    headers=self.headers, timeout=10
                )
            # Insere conteúdo novo em chunks
            self._append_markdown(live_page_id, content)
        else:
            print(f"  → Criando página Live no hub...")
            result = self.post("/pages", {
                "parent": {"page_id": self.hub_id},
                "icon":   {"type": "emoji", "emoji": "🔴"},
                "properties": {
                    "title": [{"text": {"content": f"🔴 LIVE — SET_UP Dashboard ({now})"}}]
                },
                "children": self._markdown_to_blocks(content)[:100],
            })
            live_page_id = result.get("id", "")
            print(f"  ✓ Página Live criada: {live_page_id[:8]}...")

        return live_page_id

    def _markdown_to_blocks(self, text: str) -> List[Dict]:
        """Converte markdown simples em blocos Notion."""
        blocks = []
        for line in text.split("\n"):
            if line.startswith("## "):
                blocks.append({"object": "block", "type": "heading_2",
                    "heading_2": {"rich_text": [{"text": {"content": line[3:]}}]}})
            elif line.startswith("### "):
                blocks.append({"object": "block", "type": "heading_3",
                    "heading_3": {"rich_text": [{"text": {"content": line[4:]}}]}})
            elif line.startswith("> "):
                blocks.append({"object": "block", "type": "callout",
                    "callout": {"rich_text": [{"text": {"content": line[2:]}}],
                                "icon": {"emoji": "🤖"}}})
            elif line.startswith("---"):
                blocks.append({"object": "block", "type": "divider", "divider": {}})
            elif line.strip() == "":
                blocks.append({"object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": []}})
            else:
                blocks.append({"object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": line}}]}})
        return blocks

    def _append_markdown(self, page_id: str, text: str):
        """Adiciona blocos à página existente em chunks de 100."""
        blocks = self._markdown_to_blocks(text)
        for i in range(0, min(len(blocks), 400), 100):
            chunk = blocks[i:i+100]
            try:
                requests.patch(
                    f"{NOTION_API_BASE}/blocks/{page_id}/children",
                    headers=self.headers,
                    json={"children": chunk},
                    timeout=30,
                )
            except Exception as e:
                print(f"    [warn] append chunk {i}: {e}")
