"""
Mercadona scraper v3 — com tracking quinzenal por cidade e consolidado mensal.
"""

import json
from datetime import date
from typing import List, Dict, Optional
import requests
from .base import BaseScraper
from ..config import DATA_DIR

# Dieta REAL do Mauricio (do Notion) com consumo mensal ES
# Substituições BR→ES já aplicadas (cuscuz→arroz+batata, Orfeu→Marcilla, etc.)
DIET_ITEMS: List[Dict] = [
    # PROTEÍNAS (dieta real do Notion)
    {"category": "proteína",    "query": "pechuga pollo congelada",       "consumo_mensal_unidade": "9kg",     "nota": "300g/dia — base da dieta"},
    {"category": "proteína",    "query": "claras huevo pasteurizadas",    "consumo_mensal_unidade": "6un500ml","nota": "100g/dia — Ovonatur equiv."},
    {"category": "proteína",    "query": "huevos medianos",               "consumo_mensal_unidade": "8 dz",    "nota": "3/dia"},
    {"category": "proteína",    "query": "leche en polvo entera",         "consumo_mensal_unidade": "3×500g",  "nota": "100g/dia no shake"},
    {"category": "proteína",    "query": "queso manchego curado",         "consumo_mensal_unidade": "200g",    "nota": "5g/dia — substitui parmesão"},
    {"category": "proteína",    "query": "queso mozzarella",              "consumo_mensal_unidade": "1kg",     "nota": "30g/dia"},

    # CARBOIDRATOS
    {"category": "carboidrato", "query": "arroz integral",                "consumo_mensal_unidade": "3kg",     "nota": "100g/dia — substitui cuscuz almoço"},
    {"category": "carboidrato", "query": "patatas",                       "consumo_mensal_unidade": "6kg",     "nota": "200g/dia — substitui cuscuz jantar"},
    {"category": "carboidrato", "query": "pan integral rebanado",         "consumo_mensal_unidade": "4 un",    "nota": "Substitui cuscuz parcialmente"},

    # VEGETAIS E FRUTAS CONGELADAS
    {"category": "vegetal",     "query": "verduras congeladas mix",       "consumo_mensal_unidade": "3kg",     "nota": "100g/dia"},
    {"category": "vegetal",     "query": "arandanos congelados",          "consumo_mensal_unidade": "1kg",     "nota": "Mirtilos — shake manhã"},
    {"category": "vegetal",     "query": "moras congeladas",              "consumo_mensal_unidade": "1kg",     "nota": "Amoras — shake manhã"},
    {"category": "vegetal",     "query": "fresas congeladas",             "consumo_mensal_unidade": "2kg",     "nota": "Morangos — shake manhã"},
    {"category": "vegetal",     "query": "platano banana",                "consumo_mensal_unidade": "2kg",     "nota": "Fruta fresca"},

    # GORDURAS
    {"category": "gordura",     "query": "mantequilla sin sal",           "consumo_mensal_unidade": "3×250g",  "nota": "30g/dia"},
    {"category": "gordura",     "query": "cacahuete natural",             "consumo_mensal_unidade": "500g",    "nota": "Amendoim jantar"},
    {"category": "gordura",     "query": "aceite oliva virgen extra",     "consumo_mensal_unidade": "1L",      "nota": "Base preparo"},
    {"category": "gordura",     "query": "miel flores",                   "consumo_mensal_unidade": "500g",    "nota": "10g/dia no shake"},

    # BEBIDAS E TEMPEROS
    {"category": "bebida",      "query": "cafe molido natural",           "consumo_mensal_unidade": "1.2kg",   "nota": "40g/dia — 2L café"},
    {"category": "bebida",      "query": "leche entera",                  "consumo_mensal_unidade": "6L",      "nota": "Shake + jantar"},
    {"category": "tempero",     "query": "ketchup heinz",                 "consumo_mensal_unidade": "1 frs",   "nota": "Receita frango"},
    {"category": "tempero",     "query": "salsa teriyaki kikkoman",       "consumo_mensal_unidade": "1 frs",   "nota": "Substitui molho tare"},

    # SUPLEMENTOS
    {"category": "suplemento",  "query": "creatina monohidrato",          "consumo_mensal_unidade": "150g",    "nota": "5g/dia — Amazon.es HSN"},
    {"category": "suplemento",  "query": "proteina whey",                 "consumo_mensal_unidade": "2kg",     "nota": "70g/dia — Amazon.es"},

    # HIGIENE
    {"category": "higiene",     "query": "champu anticaspa hombre",       "consumo_mensal_unidade": "1 frs",   "nota": "H&S equiv."},
    {"category": "higiene",     "query": "pasta dientes blanqueadora",    "consumo_mensal_unidade": "1 tubo",  "nota": "Oral-B equiv."},
    {"category": "higiene",     "query": "gel ducha",                     "consumo_mensal_unidade": "1 frs",   "nota": "Sabonete equiv."},
    {"category": "higiene",     "query": "desodorante roll on",           "consumo_mensal_unidade": "1 un",    "nota": "Mensal"},

    # GATO
    {"category": "gato",        "query": "pienso gato adulto",            "consumo_mensal_unidade": "3kg",     "nota": "Ração mensal"},
    {"category": "gato",        "query": "arena gato aglomerante",        "consumo_mensal_unidade": "5L",      "nota": "Areia mensal"},
]

# Warehouses por cidade
WAREHOUSE_MAP = {
    "granada":  "svq1",
    "alicante": "vlc1",
    "nerja":    "svq1",
}

# Outros mercados por cidade para mix de preços
OTHER_MARKETS = {
    "granada": {
        "lidl_granada": {
            "name": "Lidl Granada (Calle Palencia)",
            "categories_cheaper": ["proteína", "carboidrato", "gordura", "higiene"],
        },
        "dia_granada": {
            "name": "DIA Granada",
            "categories_cheaper": ["carboidrato", "tempero"],
        },
    },
    "alicante": {
        "consum_alicante": {
            "name": "Consum Alicante",
            "categories_cheaper": ["proteína", "bebida"],
        },
        "dia_alicante": {
            "name": "DIA Alicante",
            "categories_cheaper": ["carboidrato"],
        },
    },
    "nerja": {
        "dia_nerja": {
            "name": "DIA Nerja",
            "categories_cheaper": ["carboidrato", "tempero"],
        },
    },
}

# Estimativas de preço em outros mercados (vs Mercadona = base 100%)
# Baseado em estudos de preços ES 2025
MARKET_PRICE_FACTOR = {
    "Lidl":    0.85,   # ~15% mais barato na maioria
    "DIA":     0.80,   # ~20% mais barato em básicos
    "Consum":  0.92,   # ~8% mais barato
    "Aldi":    0.83,   # ~17% mais barato
    "Covirán": 1.05,   # ~5% mais caro (conveniência)
    "Carrefour": 0.95, # ~5% mais barato
}


class MercadonaScraper(BaseScraper):
    ALGOLIA_APP = "7UZJKL1DJ0"
    ALGOLIA_KEY = "9d8f2e39e90df472b4f2e559a116fe17"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._history_file = DATA_DIR / "prices_history.json"
        self._history: Dict = self._load_history()

    def scrape_city(self, city_key: str) -> List[Dict]:
        warehouse = WAREHOUSE_MAP.get(city_key, "svq1")
        products = []
        today = date.today().isoformat()
        print(f"  → Mercadona {city_key} (warehouse: {warehouse})...")

        for item in DIET_ITEMS:
            query    = item["query"]
            category = item["category"]
            consumo  = item["consumo_mensal_unidade"]
            nota     = item["nota"]
            try:
                hits = self._search(query, warehouse)
                for hit in hits[:2]:
                    product = {
                        "source":              "mercadona",
                        "city":                city_key,
                        "warehouse":           warehouse,
                        "category":            category,
                        "query":               query,
                        "consumo_mensal":      consumo,
                        "nota_dieta":          nota,
                        "product_name":        hit.get("display_name", ""),
                        "brand":               hit.get("brand", "Hacendado"),
                        "price_eur":           hit.get("price"),
                        "unit":                hit.get("unit_name", ""),
                        "unit_size":           hit.get("unit_size", ""),
                        "price_per_unit":      hit.get("price_per_unit"),
                        "url":                 f"https://tienda.mercadona.es/product/{hit.get('id','')}",
                        "scraped_date":        today,
                        "market":              "Mercadona",
                    }
                    tracking = self._update_history(city_key, query, hit)
                    product.update(tracking)
                    products.append(product)
            except Exception as e:
                print(f"    [erro] {query}: {e.__class__.__name__}")

        self._save_history()
        print(f"    ✓ {len(products)} produtos Mercadona")
        return products

    def _search(self, query: str, warehouse: str) -> List[Dict]:
        url = f"https://7uzjkl1dj0-dsn.algolia.net/1/indexes/products_prod_{warehouse}_es/query"
        params = {
            "x-algolia-application-id": self.ALGOLIA_APP,
            "x-algolia-api-key": self.ALGOLIA_KEY,
        }
        payload = {"params": f"query={query}&hitsPerPage=3"}
        try:
            self.sleep()
            resp = requests.post(url, params=params, json=payload,
                                 headers=self.get_headers(), timeout=self.timeout)
            if resp.status_code == 200:
                results = []
                for hit in resp.json().get("hits", []):
                    pi = hit.get("price_instructions", {})
                    results.append({
                        "id":           hit.get("id"),
                        "display_name": hit.get("display_name"),
                        "brand":        hit.get("brand", ""),
                        "price":        self._extract_price(pi),
                        "unit_name":    pi.get("unit_name", ""),
                        "unit_size":    str(pi.get("total_units", "")),
                        "price_per_unit": pi.get("price_per_liter") or pi.get("price_per_kg"),
                    })
                return results
        except Exception:
            pass
        return []

    def _extract_price(self, pi: Dict) -> Optional[float]:
        for key in ("unit_price", "bulk_price", "reference_price", "selling_price"):
            v = pi.get(key)
            if v is not None:
                try: return round(float(v), 2)
                except: continue
        return None

    # -------------------------------------------------------
    # TRACKING QUINZENAL
    # -------------------------------------------------------

    def _update_history(self, city: str, query: str, hit: Dict) -> Dict:
        today     = date.today()
        today_str = today.isoformat()
        price     = self._extract_price(hit.get("price_instructions", {}))
        if not price:
            return {"price_change_pct": None, "price_trend": "—", "prev_price": None}

        key = f"{city}|{query}|{hit.get('id','')}"
        if key not in self._history:
            self._history[key] = []
        hist = self._history[key]

        if not hist or hist[-1]["date"] != today_str:
            hist.append({"date": today_str, "price": price})
            self._history[key] = hist[-90:]

        fifteen_ago = today.toordinal() - 15
        old = [e for e in hist if date.fromisoformat(e["date"]).toordinal() <= fifteen_ago]
        if not old:
            return {"price_change_pct": None, "price_trend": "novo", "prev_price": None}

        prev  = old[-1]["price"]
        pct   = round(((price - prev) / prev) * 100, 1) if prev else 0
        trend = "↑ subiu" if pct > 5 else "↓ desceu" if pct < -5 else "→ estável"
        return {"price_change_pct": pct, "price_trend": trend, "prev_price": prev}

    def _load_history(self) -> Dict:
        if self._history_file.exists():
            try: return json.loads(self._history_file.read_text(encoding="utf-8"))
            except: pass
        return {}

    def _save_history(self):
        self._history_file.write_text(
            json.dumps(self._history, ensure_ascii=False, indent=2), encoding="utf-8")


# -------------------------------------------------------
# CONSOLIDADOR — mix de mercados por preço mais baixo
# -------------------------------------------------------

def build_shopping_consolidado(mercadona_products: List[Dict], city_key: str) -> Dict:
    """
    Para cada item da dieta, compara Mercadona com estimativas dos outros mercados
    e monta o carrinho ótimo (mais barato por categoria).
    Retorna dicionário com total mensal e breakdown por mercado.
    """
    other_markets = OTHER_MARKETS.get(city_key, {})
    city_name = {"granada": "Granada (Zaidín)", "alicante": "Alicante (Benalúa)", "nerja": "Nerja"}.get(city_key, city_key)

    # Índice Mercadona por query
    mercadona_index: Dict[str, Dict] = {}
    for p in mercadona_products:
        q = p.get("query", "")
        if q not in mercadona_index or (p.get("price_eur") or 0) < (mercadona_index[q].get("price_eur") or 999):
            mercadona_index[q] = p

    carrinho: List[Dict] = []
    total_mercadona = 0.0
    total_otimizado = 0.0
    por_mercado: Dict[str, float] = {"Mercadona": 0.0}

    for item in DIET_ITEMS:
        q         = item["query"]
        category  = item["category"]
        consumo   = item["consumo_mensal_unidade"]
        nota      = item["nota"]

        mercadona_data = mercadona_index.get(q, {})
        price_mercadona = mercadona_data.get("price_eur")

        if not price_mercadona:
            continue

        # Verifica se outro mercado é mais barato nessa categoria
        best_market = "Mercadona"
        best_price  = price_mercadona

        for market_key, market_info in other_markets.items():
            if category in market_info.get("categories_cheaper", []):
                # Estima preço com base no fator do mercado
                market_name = market_info["name"].split()[0]   # pega só o nome
                factor      = MARKET_PRICE_FACTOR.get(market_name, 1.0)
                est_price   = round(price_mercadona * factor, 2)
                if est_price < best_price:
                    best_price  = est_price
                    best_market = market_info["name"]

        economy = round(price_mercadona - best_price, 2)
        pct_saved = round((economy / price_mercadona) * 100, 1) if price_mercadona else 0

        entry = {
            "item":             item["query"],
            "product_name":     mercadona_data.get("product_name") or q,
            "category":         category,
            "consumo_mensal":   consumo,
            "nota_dieta":       nota,
            "price_mercadona":  price_mercadona,
            "best_market":      best_market,
            "best_price":       best_price,
            "economy":          economy,
            "pct_saved":        pct_saved,
            "trend":            mercadona_data.get("price_trend", "—"),
            "change_pct":       mercadona_data.get("price_change_pct"),
        }
        carrinho.append(entry)
        total_mercadona += price_mercadona
        total_otimizado += best_price
        por_mercado[best_market] = por_mercado.get(best_market, 0.0) + best_price

    total_economy = round(total_mercadona - total_otimizado, 2)
    pct_total_saved = round((total_economy / total_mercadona) * 100, 1) if total_mercadona else 0

    return {
        "city":             city_key,
        "city_name":        city_name,
        "carrinho":         carrinho,
        "total_mercadona":  round(total_mercadona, 2),
        "total_otimizado":  round(total_otimizado, 2),
        "total_economy":    total_economy,
        "pct_total_saved":  pct_total_saved,
        "por_mercado":      por_mercado,
        "num_items":        len(carrinho),
    }
