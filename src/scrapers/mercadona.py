"""
Mercadona scraper v2 — com:
- Filtro por cidade (warehouse correto)
- Tracking quinzenal de variação de preços
- Histórico em data/prices_history.json
- Alerta quando preço sobe/cai >5%
"""

import json
from datetime import datetime, timezone, date
from pathlib import Path
from typing import List, Dict, Optional
import requests
from .base import BaseScraper
from ..config import DATA_DIR


ESSENTIAL_PRODUCTS = {
    "proteína": [
        "pechuga pollo",
        "clara huevo pasteurizada",
        "huevos xl",
        "atun claro",
        "salmon",
    ],
    "carboidrato": [
        "arroz integral",
        "patata",
        "pan integral",
        "avena",
    ],
    "gordura": [
        "aceite oliva virgen extra",
        "mantequilla sin sal",
        "cacahuete tostado",
        "miel",
    ],
    "bebida": [
        "cafe molido",
        "leche desnatada",
        "leche en polvo",
        "creatina",
    ],
    "higiene": [
        "champu anticaspa",
        "pasta dientes",
        "gel ducha",
        "desodorante",
    ],
    "gato": [
        "pienso gato adulto",
        "arena gato",
    ],
    "suplemento": [
        "proteina whey",
        "vitamina d3",
        "omega 3",
        "magnesio",
    ],
}

# Warehouses por cidade — testados e confirmados
WAREHOUSE_MAP = {
    "granada":  "svq1",   # Sevilla (cobre Andaluzia)
    "alicante": "vlc1",   # Valencia
    "nerja":    "svq1",
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

        for category, queries in ESSENTIAL_PRODUCTS.items():
            for query in queries:
                try:
                    hits = self._search_product(query, warehouse)
                    for hit in hits[:2]:
                        product = {
                            "source": "mercadona",
                            "city": city_key,
                            "warehouse": warehouse,
                            "category": category,
                            "query": query,
                            "product_name": hit.get("display_name", ""),
                            "brand": hit.get("brand", "Hacendado"),
                            "price_eur": hit.get("price"),
                            "unit": hit.get("unit_name", ""),
                            "unit_size": hit.get("unit_size", ""),
                            "price_per_unit": hit.get("price_per_unit"),
                            "url": f"https://tienda.mercadona.es/product/{hit.get('id', '')}",
                            "scraped_date": today,
                        }

                        # Tracking quinzenal
                        tracking = self._update_price_history(city_key, query, hit)
                        product["price_change_pct"] = tracking.get("change_pct")
                        product["price_trend"] = tracking.get("trend")
                        product["prev_price"] = tracking.get("prev_price")

                        products.append(product)
                except Exception as e:
                    print(f"    [erro] {query}: {e.__class__.__name__}")
                    continue

        self._save_history()
        print(f"    ✓ {len(products)} produtos em {city_key}")
        return products

    def _search_product(self, query: str, warehouse: str) -> List[Dict]:
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
                        "id": hit.get("id"),
                        "display_name": hit.get("display_name"),
                        "brand": hit.get("brand", ""),
                        "price": self._parse_price(pi),
                        "unit_name": pi.get("unit_name", ""),
                        "unit_size": pi.get("total_units", ""),
                        "price_per_unit": pi.get("price_per_liter") or pi.get("price_per_kg"),
                    })
                return results
        except Exception:
            pass
        return []

    def _parse_price(self, price_data: Dict) -> Optional[float]:
        for key in ("unit_price", "bulk_price", "reference_price", "selling_price"):
            val = price_data.get(key)
            if val is not None:
                try:
                    return round(float(val), 2)
                except (TypeError, ValueError):
                    continue
        return None

    # ----------------------------------------------------------
    # TRACKING QUINZENAL
    # ----------------------------------------------------------

    def _update_price_history(self, city: str, query: str, hit: Dict) -> Dict:
        """Registra preço e calcula variação vs 15 dias atrás."""
        today = date.today()
        today_str = today.isoformat()
        price = self._parse_price(hit.get("price_instructions", {}))
        if not price:
            return {}

        key = f"{city}|{query}|{hit.get('id','')}"
        if key not in self._history:
            self._history[key] = []

        history = self._history[key]

        # Adiciona entrada de hoje se não existe
        if not history or history[-1]["date"] != today_str:
            history.append({"date": today_str, "price": price})
            # Mantém só últimos 60 registros
            self._history[key] = history[-60:]

        # Compara com registro mais antigo dos últimos 15 dias
        fifteen_days_ago = (today.toordinal() - 15)
        old_entries = [e for e in history
                       if date.fromisoformat(e["date"]).toordinal() <= fifteen_days_ago]

        if not old_entries:
            return {"trend": "new", "change_pct": None, "prev_price": None}

        prev = old_entries[-1]["price"]
        change_pct = round(((price - prev) / prev) * 100, 1) if prev else 0

        if change_pct > 5:
            trend = "↑ subiu"
        elif change_pct < -5:
            trend = "↓ desceu"
        else:
            trend = "→ estável"

        return {"trend": trend, "change_pct": change_pct, "prev_price": prev}

    def _load_history(self) -> Dict:
        if self._history_file.exists():
            try:
                return json.loads(self._history_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_history(self):
        self._history_file.write_text(
            json.dumps(self._history, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
