"""
diet_page_sync.py — ponto 4 do backlog:
Cruza preços reais coletados (Mercadona + multi-market) com a página de dieta real do Notion.
Atualiza totais na página https://app.notion.com/p/38e6d7bcf70c81e2ad46f7d5b6a2fa42

Diferença vs diet_sync.py (que atualiza páginas de cidade):
  → Este módulo atualiza a PRÓPRIA PÁGINA DE DIETA com os preços reais do dia.
  → Recalcula o total mensal real vs estimado original (€295,06).
  → Mostra variação quinzenal de preços.
"""

import os
import json
from typing import List, Dict, Optional
from datetime import datetime, timezone
import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION  = "2022-06-28"

DIET_PAGE_ID = "38e6d7bcf70c81e2ad46f7d5b6a2fa42"   # página dieta real do Notion

# Total estimado original na página Notion (referência)
ESTIMATED_TOTAL_ORIGINAL = 295.06

# Todos os 30 itens com quantities mensais e queries
ALL_DIET_ITEMS = [
    # PROTEÍNAS
    {"label": "Frango peito (pechuga)",        "query": "pechuga pollo congelada",      "qty": 9.0,  "unit": "kg",    "category": "proteína"},
    {"label": "Claras pasteurizadas",           "query": "claras huevo pasteurizadas",   "qty": 6.0,  "unit": "un",    "category": "proteína"},
    {"label": "Ovos M",                         "query": "huevos medianos",              "qty": 8.0,  "unit": "dz",    "category": "proteína"},
    {"label": "Leite em pó integral",           "query": "leche en polvo entera",        "qty": 3.0,  "unit": "×500g", "category": "proteína"},
    {"label": "Queijo manchego",                "query": "queso manchego curado",        "qty": 0.2,  "unit": "kg",    "category": "proteína"},
    {"label": "Mozzarella",                     "query": "queso mozzarella",             "qty": 1.0,  "unit": "kg",    "category": "proteína"},
    # CARBOIDRATOS
    {"label": "Arroz integral",                 "query": "arroz integral",               "qty": 3.0,  "unit": "kg",    "category": "carboidrato"},
    {"label": "Batata",                         "query": "patatas",                      "qty": 6.0,  "unit": "kg",    "category": "carboidrato"},
    {"label": "Pão integral",                   "query": "pan integral rebanado",        "qty": 4.0,  "unit": "un",    "category": "carboidrato"},
    # VEGETAIS/FRUTAS
    {"label": "Verdura congelada mix",          "query": "verduras congeladas mix",      "qty": 3.0,  "unit": "kg",    "category": "vegetal"},
    {"label": "Mirtilo (arándanos)",            "query": "arandanos congelados",         "qty": 1.0,  "unit": "kg",    "category": "vegetal"},
    {"label": "Amora (moras)",                  "query": "moras congeladas",             "qty": 1.0,  "unit": "kg",    "category": "vegetal"},
    {"label": "Morango (fresas)",               "query": "fresas congeladas",            "qty": 2.0,  "unit": "kg",    "category": "vegetal"},
    {"label": "Banana (plátano)",               "query": "platano banana",               "qty": 2.0,  "unit": "kg",    "category": "vegetal"},
    # GORDURAS
    {"label": "Manteiga s/ sal",                "query": "mantequilla sin sal",          "qty": 3.0,  "unit": "×250g", "category": "gordura"},
    {"label": "Amendoim (cacahuete)",           "query": "cacahuete natural",            "qty": 0.5,  "unit": "kg",    "category": "gordura"},
    {"label": "Azeite extra virgem",            "query": "aceite oliva virgen extra",    "qty": 1.0,  "unit": "L",     "category": "gordura"},
    {"label": "Mel",                            "query": "miel flores",                  "qty": 0.5,  "unit": "kg",    "category": "gordura"},
    # BEBIDAS/TEMPEROS
    {"label": "Café molido",                    "query": "cafe molido natural",          "qty": 1.2,  "unit": "kg",    "category": "bebida"},
    {"label": "Leite integral",                 "query": "leche entera",                 "qty": 6.0,  "unit": "L",     "category": "bebida"},
    {"label": "Ketchup Heinz",                  "query": "ketchup heinz",                "qty": 1.0,  "unit": "frs",   "category": "tempero"},
    {"label": "Molho teriyaki Kikkoman",        "query": "salsa teriyaki kikkoman",      "qty": 1.0,  "unit": "frs",   "category": "tempero"},
    # SUPLEMENTOS (Amazon.es)
    {"label": "Creatina monohidrato 150g",      "query": "creatina monohidrato",         "qty": 0.5,  "unit": "emb",   "category": "suplemento"},
    {"label": "Whey protein 2kg",               "query": "proteina whey",                "qty": 1.0,  "unit": "emb",   "category": "suplemento"},
    # HIGIENE
    {"label": "Shampoo anticaspa",              "query": "champu anticaspa hombre",      "qty": 1.0,  "unit": "frs",   "category": "higiene"},
    {"label": "Pasta de dentes",                "query": "pasta dientes blanqueadora",   "qty": 1.0,  "unit": "tubo",  "category": "higiene"},
    {"label": "Gel de banho",                   "query": "gel ducha",                    "qty": 1.0,  "unit": "frs",   "category": "higiene"},
    {"label": "Desodorante roll-on",            "query": "desodorante roll on",          "qty": 1.0,  "unit": "un",    "category": "higiene"},
    # GATO
    {"label": "Ração gato adulto",              "query": "pienso gato adulto",           "qty": 1.0,  "unit": "emb",   "category": "gato"},
    {"label": "Areia gato aglomerante",         "query": "arena gato aglomerante",       "qty": 1.0,  "unit": "emb",   "category": "gato"},
]


class DietPageSync:
    """Atualiza a página de dieta real do Notion com preços reais coletados."""

    def __init__(self, token: str):
        self.token   = token.strip()
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
            print(f"  [Notion] {r.status_code}: {r.text[:150]}")
        r.raise_for_status()
        return r.json()

    def _delete_block(self, block_id: str):
        requests.delete(f"{NOTION_API_BASE}/blocks/{block_id}",
                        headers=self.headers, timeout=10)

    def calculate_totals(self, all_prices: List[Dict], city: str = "granada") -> Dict:
        """
        Cruza os 30 itens com preços reais coletados.
        Prioriza preços reais; fallback para None.
        Retorna breakdown por categoria + totais.
        """
        # Índice: query → {market → price}
        price_idx: Dict[str, Dict[str, float]] = {}
        for p in all_prices:
            if p.get("city") != city:
                continue
            q = p.get("query", "")
            m = p.get("market", "Mercadona")
            v = p.get("price_eur")
            if q and v:
                if q not in price_idx:
                    price_idx[q] = {}
                if m not in price_idx[q] or v < price_idx[q][m]:
                    price_idx[q][m] = v

        results      = []
        total_real   = 0.0
        total_merc   = 0.0
        by_category: Dict[str, float] = {}

        for item in ALL_DIET_ITEMS:
            q = item["query"]
            prices_for_item = price_idx.get(q, {})

            # Melhor preço disponível
            best_price  = None
            best_market = None
            if prices_for_item:
                best_market, best_price = min(prices_for_item.items(), key=lambda x: x[1])

            merc_price = prices_for_item.get("Mercadona")

            monthly_cost = round(best_price * item["qty"], 2) if best_price else None
            merc_monthly = round(merc_price * item["qty"], 2) if merc_price else None

            if monthly_cost:
                total_real += monthly_cost
                cat = item["category"]
                by_category[cat] = by_category.get(cat, 0.0) + monthly_cost

            if merc_monthly:
                total_merc += merc_monthly

            results.append({
                **item,
                "best_price":    best_price,
                "best_market":   best_market,
                "merc_price":    merc_price,
                "monthly_cost":  monthly_cost,
                "merc_monthly":  merc_monthly,
                "found":         best_price is not None,
            })

        return {
            "city":          city,
            "items":         results,
            "total_real":    round(total_real, 2),
            "total_merc":    round(total_merc, 2),
            "total_original_estimate": ESTIMATED_TOTAL_ORIGINAL,
            "diff_vs_estimate": round(total_real - ESTIMATED_TOTAL_ORIGINAL, 2),
            "by_category":   {k: round(v, 2) for k, v in by_category.items()},
            "found_count":   sum(1 for r in results if r["found"]),
            "total_items":   len(results),
            "updated":       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }

    def build_live_blocks(self, totals: Dict) -> List[Dict]:
        """Constrói blocos Notion para inserir no topo da página de dieta."""
        blocks  = []
        now     = totals["updated"]
        total   = totals["total_real"]
        diff    = totals["diff_vs_estimate"]
        diff_s  = f"+€{diff:.2f}" if diff >= 0 else f"€{diff:.2f}"
        found   = totals["found_count"]
        n_items = totals["total_items"]

        # Callout principal
        blocks.append({
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content":
                    f"🔴 LIVE DIETA — {now}  |  {found}/{n_items} itens com preço real  |  "
                    f"Total: €{total:.2f}/mês  |  vs estimativa: {diff_s}"
                }}],
                "icon":  {"emoji": "🍳"},
                "color": "orange_background",
            }
        })

        # Tabela por categoria
        blocks.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "💰 Custo real por categoria"}}]}
        })

        for cat, total_cat in sorted(totals["by_category"].items(), key=lambda x: -x[1]):
            pct = round(total_cat / total * 100, 1) if total > 0 else 0
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content":
                    f"{cat.capitalize()}: €{total_cat:.2f}/mês ({pct}%)"
                }}]}
            })

        # Totais comparativos
        blocks.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "📊 Totais comparativos"}}]}
        })
        comparisons = [
            f"🔴 Total REAL hoje (mix mercados): €{total:.2f}/mês",
            f"🏪 Tudo Mercadona: €{totals['total_merc']:.2f}/mês",
            f"📋 Estimativa original (Notion): €{ESTIMATED_TOTAL_ORIGINAL:.2f}/mês",
            f"{'↑' if diff >= 0 else '↓'} Diferença real vs estimativa: {diff_s}/mês = {diff_s.replace('€','')}×12 = €{abs(diff)*12:.0f}/ano",
        ]
        for line in comparisons:
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line}}]}
            })

        # Itens não encontrados
        missing = [r for r in totals["items"] if not r["found"]]
        if missing:
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content":
                    f"⚠️ Itens sem preço coletado ({len(missing)})"
                }}]}
            })
            for r in missing:
                blocks.append({
                    "object": "block", "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content":
                        f"{r['label']} ({r['category']}) — scraper não retornou preço"
                    }}]}
                })

        blocks.append({"object": "block", "type": "divider", "divider": {}})
        return blocks

    def remove_old_live_blocks(self):
        """Remove blocos LIVE antigos da página de dieta (evita acúmulo)."""
        try:
            children = self._get(f"/blocks/{DIET_PAGE_ID}/children?page_size=50")
            blocks   = children.get("results", [])
            removed  = 0
            for block in blocks:
                b_type = block.get("type", "")
                # Remover callouts LIVE anteriores
                if b_type == "callout":
                    texts = block.get("callout", {}).get("rich_text", [])
                    text  = "".join(t.get("text", {}).get("content", "") for t in texts)
                    if "LIVE DIETA" in text or "🔴 LIVE" in text:
                        self._delete_block(block["id"])
                        removed += 1
                # Remover headings de seções LIVE
                elif b_type == "heading_3":
                    texts = block.get("heading_3", {}).get("rich_text", [])
                    text  = "".join(t.get("text", {}).get("content", "") for t in texts)
                    if any(s in text for s in ["💰 Custo real", "📊 Totais", "⚠️ Itens sem"]):
                        self._delete_block(block["id"])
                        removed += 1
                elif b_type == "divider" and removed > 0:
                    self._delete_block(block["id"])
                    removed += 1
                    break  # parar no primeiro divisor após os LIVE blocks
            print(f"  [diet_page] {removed} blocos LIVE antigos removidos")
        except Exception as e:
            print(f"  [diet_page] erro ao remover blocos antigos: {e}")

    def update_diet_page(self, all_prices: List[Dict], city: str = "granada"):
        """
        Atualiza a página de dieta real com preços do dia.
        Usa Granada como cidade de referência (preços mais completos).
        """
        print(f"  [diet_page] Calculando totais reais para {city}...")
        totals = self.calculate_totals(all_prices, city)

        print(f"  [diet_page] {totals['found_count']}/{totals['total_items']} itens encontrados")
        print(f"  [diet_page] Total real: €{totals['total_real']:.2f}/mês "
              f"(vs estimativa €{ESTIMATED_TOTAL_ORIGINAL:.2f})")

        # Remove blocos antigos
        self.remove_old_live_blocks()

        # Insere blocos novos no topo
        new_blocks = self.build_live_blocks(totals)
        try:
            self._patch(f"/blocks/{DIET_PAGE_ID}/children", {"children": new_blocks})
            print(f"  [diet_page] ✓ Página de dieta atualizada ({len(new_blocks)} blocos)")
        except Exception as e:
            print(f"  [diet_page] ERRO ao inserir blocos: {e}")

        return totals
