"""
Diet Sync — cruza preços reais do Mercadona com os 30 itens da dieta.
Queries alinhadas com o que o mercadona.py realmente coleta.

Fix v8:
- Queries corretas (ex: 'pechuga pollo congelada' não 'pechuga pollo')
- Quando há múltiplos produtos por query, pega o de MENOR preço
- Custo mensal calculado por cidade individualmente (sem reaproveitar de outra)
- Formato da tabela de produtos idêntico ao que o usuário viu no Notion v5
"""

import os
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION  = "2022-06-28"

HUB_PAGE_ID = "3736d7bcf70c81c09c0ff224c550e309"

# ─── Mapeamento query → (label PT, qty/mês, unit_display) ──────────────────
# Queries EXATAS que o mercadona.py usa (campo "query" no JSON)
DIET_ITEMS = [
    # proteína
    ("pechuga pollo congelada",    "Frango peito (pechuga)",       9.0,  "kg"),
    ("claras huevo pasteurizadas", "Claras pasteurizadas",          6.0,  "un"),
    ("huevos medianos",            "Ovos M",                        8.0,  "dz"),
    ("leche en polvo entera",      "Leite em pó integral",          3.0,  "×500g"),
    ("queso manchego curado",      "Queijo manchego",               0.2,  "kg"),
    ("queso mozzarella",           "Mozzarella",                    1.0,  "kg"),
    # carboidrato
    ("arroz integral",             "Arroz integral",                3.0,  "kg"),
    ("patatas",                    "Batata",                        6.0,  "kg"),
    ("pan integral rebanado",      "Pão integral",                  4.0,  "un"),
    # vegetal/fruta
    ("verduras congeladas mix",    "Verdura congelada mix",         3.0,  "kg"),
    ("arandanos congelados",       "Mirtilo (arándanos)",           1.0,  "kg"),
    ("moras congeladas",           "Amora (moras)",                 1.0,  "kg"),
    ("fresas congeladas",          "Morango (fresas)",              2.0,  "kg"),
    ("platano banana",             "Banana (plátano)",              2.0,  "kg"),
    # gordura
    ("mantequilla sin sal",        "Manteiga s/ sal",               3.0,  "×250g"),
    ("cacahuete natural",          "Amendoim (cacahuete)",          0.5,  "kg"),
    ("aceite oliva virgen extra",  "Azeite extra virgem",           1.0,  "L"),
    ("miel flores",                "Mel",                           0.5,  "kg"),
    # bebida
    ("cafe molido natural",        "Café molido",                   1.2,  "kg"),
    ("leche entera",               "Leite integral",                6.0,  "L"),
    # tempero
    ("ketchup heinz",              "Ketchup Heinz",                 1.0,  "frs"),
    ("salsa teriyaki kikkoman",    "Molho teriyaki Kikkoman",       1.0,  "frs"),
    # higiene
    ("champu anticaspa hombre",    "Shampoo anticaspa",             1.0,  "frs"),
    ("pasta dientes blanqueadora", "Pasta de dentes",               1.0,  "tubo"),
    ("gel ducha",                  "Gel de banho",                  1.0,  "frs"),
    ("desodorante roll on",        "Desodorante roll-on",           1.0,  "un"),
    # gato
    ("pienso gato adulto",         "Ração gato adulto",             1.0,  "emb"),
    ("arena gato aglomerante",     "Areia gato aglomerante",        1.0,  "emb"),
]

# Produtos que têm múltiplos resultados — filtros de qualidade para pegar o certo
# (evita pegar produto errado quando query retorna resultados misturados)
PREFERRED_PRODUCT_KEYWORDS = {
    "pechuga pollo congelada":    ["pechuga", "pollo"],      # evita "gyoza"
    "claras huevo pasteurizadas": ["claras", "huevo"],       # evita "acondicionador"
    "leche en polvo entera":      ["polvo", "entera"],       # evita "leche continuación"
    "queso mozzarella":           ["mozzarella"],
    "arroz integral":             ["arroz", "integral"],     # evita "arroz cocido"
    "patatas":                    ["patata"],                 # evita "patatas fritas"
    "verduras congeladas mix":    ["verdura", "menestra", "mix"],
    "arandanos congelados":       ["arándano", "arandano"],
    "moras congeladas":           ["mora"],                  # evita "golosinas"
    "fresas congeladas":          ["fresa"],                 # evita "tarta"
    "mantequilla sin sal":        ["mantequilla", "sin sal"],
    "cacahuete natural":          ["cacahuete"],
    "aceite oliva virgen extra":  ["oliva", "virgen"],       # pega o 1L não o 5L
    "miel flores":                ["miel", "flores"],
    "cafe molido natural":        ["café", "molido", "natural"],
    "leche entera":               ["leche entera"],          # evita "leche +proteínas"
    "creatina monohidrato":       [],                        # Amazon.es — sem Mercadona
    "proteina whey":              [],                        # Amazon.es — sem Mercadona
    "champu anticaspa hombre":    ["anticaspa"],
    "pasta dientes blanqueadora": ["dentífrico", "blanquea"],
    "gel ducha":                  ["gel", "baño"],
    "desodorante roll on":        ["desodorante", "roll"],
    "pienso gato adulto":         ["gato", "adulto"],
    "arena gato aglomerante":     ["arena", "gato"],
}


class DietSyncNotion:
    def __init__(self, token: str, hub_id: str):
        self.token  = token.strip()
        self.hub_id = hub_id
        self.headers = {
            "Authorization":  f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type":   "application/json",
        }

    def _get(self, path: str) -> dict:
        r = requests.get(f"{NOTION_API_BASE}{path}", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, payload: dict) -> dict:
        r = requests.post(f"{NOTION_API_BASE}{path}",
                          headers=self.headers, json=payload, timeout=30)
        if r.status_code >= 400:
            print(f"  [Notion erro] {r.status_code}: {r.text[:150]}")
        r.raise_for_status()
        return r.json()

    def patch(self, path: str, payload: dict) -> dict:
        r = requests.patch(f"{NOTION_API_BASE}{path}",
                           headers=self.headers, json=payload, timeout=30)
        if r.status_code >= 400:
            print(f"  [Notion erro] {r.status_code}: {r.text[:150]}")
        r.raise_for_status()
        return r.json()

    def get_children(self, page_id: str) -> List[Dict]:
        r = requests.get(f"{NOTION_API_BASE}/blocks/{page_id}/children?page_size=100",
                         headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json().get("results", [])

    def _delete_block(self, block_id: str):
        requests.delete(f"{NOTION_API_BASE}/blocks/{block_id}",
                        headers=self.headers, timeout=10)

    # ------------------------------------------------------------------
    # SELEÇÃO DO MELHOR PRODUTO POR QUERY
    # ------------------------------------------------------------------

    def _best_price_for_query(self, query: str, city_prices: List[Dict]) -> Optional[Dict]:
        """
        Dentre todos os produtos retornados para uma query, escolhe o melhor:
        1. Filtra por keywords preferidas (evita produtos errados)
        2. Pega o de menor preço (unit_price)
        """
        candidates = [p for p in city_prices if p.get("query") == query]
        if not candidates:
            return None

        keywords = PREFERRED_PRODUCT_KEYWORDS.get(query, [])
        if keywords:
            filtered = [
                p for p in candidates
                if all(k.lower() in (p.get("product_name") or "").lower() for k in keywords)
            ]
            if filtered:
                candidates = filtered
            # Se nenhum passou no filtro, mantém os candidatos originais

        # Pega o de menor preço
        return min(candidates, key=lambda p: p.get("price_eur") or 9999)

    # ------------------------------------------------------------------
    # CÁLCULO CUSTO DIETA
    # ------------------------------------------------------------------

    def calculate_diet_cost(self, all_prices: List[Dict], city: str) -> Dict:
        """
        Cruza os itens da dieta com preços reais do Mercadona.
        Filtra por cidade AQUI (não depende de quem passa os dados).
        """
        city_prices = [p for p in all_prices if p.get("city") == city]
        results = []
        total = 0.0

        for query, label, qty, unit in DIET_ITEMS:
            best = self._best_price_for_query(query, city_prices)

            if best and best.get("price_eur"):
                unit_price   = best["price_eur"]
                product_name = best.get("product_name", label)
                monthly_cost = round(unit_price * qty, 2)
                total += monthly_cost
                results.append({
                    "label":        label,
                    "product":      product_name,
                    "qty":          qty,
                    "unit":         unit,
                    "unit_price":   unit_price,
                    "monthly_cost": monthly_cost,
                    "found":        True,
                })
            else:
                results.append({
                    "label":        label,
                    "product":      label,
                    "qty":          qty,
                    "unit":         unit,
                    "unit_price":   None,
                    "monthly_cost": None,
                    "found":        False,
                })

        found_count = sum(1 for r in results if r["found"])
        print(f"    Dieta {city}: {found_count}/{len(results)} itens = €{total:.2f}/mês")

        return {
            "city":    city,
            "items":   results,
            "total":   round(total, 2),
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }

    # ------------------------------------------------------------------
    # BLOCOS NOTION — TABELA PREÇOS (formato como estava no v5)
    # ------------------------------------------------------------------

    def _build_price_table_blocks(self, diet_cost: Dict) -> List[Dict]:
        """Cria os blocos de preços no formato tabela Notion."""
        blocks = []
        total = diet_cost["total"]
        city_name = {"granada": "Granada", "alicante": "Alicante", "nerja": "Nerja"}.get(
            diet_cost["city"], diet_cost["city"].capitalize()
        )

        # Heading
        blocks.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {
                "content": f"🛒 Preços Mercadona — Custo real da sua dieta: €{total:.2f}/mês"
            }}]}
        })

        # Tabela Notion
        rows = []

        # Header row
        rows.append({
            "object": "block", "type": "table_row",
            "table_row": {"cells": [
                [{"type": "text", "text": {"content": "Produto"}, "annotations": {"bold": True}}],
                [{"type": "text", "text": {"content": "Preço"}, "annotations": {"bold": True}}],
                [{"type": "text", "text": {"content": "Qty/mês"}, "annotations": {"bold": True}}],
                [{"type": "text", "text": {"content": "Total/mês"}, "annotations": {"bold": True}}],
            ]}
        })

        for item in diet_cost["items"]:
            if item["found"]:
                price_str   = f"€{item['unit_price']:.2f}"
                qty_str     = f"{item['qty']} {item['unit']}"
                total_str   = f"€{item['monthly_cost']:.2f}"
                product_str = item["product"][:45]
            else:
                price_str   = "—"
                qty_str     = f"{item['qty']} {item['unit']}"
                total_str   = "—"
                product_str = item["label"]

            rows.append({
                "object": "block", "type": "table_row",
                "table_row": {"cells": [
                    [{"type": "text", "text": {"content": product_str}}],
                    [{"type": "text", "text": {"content": price_str}}],
                    [{"type": "text", "text": {"content": qty_str}}],
                    [{"type": "text", "text": {"content": total_str}}],
                ]}
            })

        blocks.append({
            "object": "block",
            "type": "table",
            "table": {
                "table_width": 4,
                "has_column_header": True,
                "has_row_header": False,
                "children": rows,
            }
        })

        # Total em negrito
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": f"💰 TOTAL MENSAL DIETA: €{total:.2f}"},
                 "annotations": {"bold": True, "color": "green"}}
            ]}
        })

        return blocks

    # Mantido por compatibilidade com main.py
    def build_diet_callout(self, diet_cost: Dict, ranked_listings: List[Dict]) -> str:
        return ""

    def upsert_live_page(self, all_diet_costs, ranked_listings, consolidados):
        pass
