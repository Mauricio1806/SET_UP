"""
Mercadona scraper — preços de produtos essenciais da dieta do Mauricio.
Usa a API não-oficial do Mercadona (endpoint público).
"""

from typing import List, Dict
import requests
from .base import BaseScraper


# Lista de produtos essenciais da dieta real do Mauricio
ESSENTIAL_PRODUCTS = {
    "proteína": [
        "pechuga pollo",
        "clara huevo pasteurizada",
        "huevos xl",
        "atun claro",
    ],
    "carboidrato": [
        "arroz integral",
        "patata",
        "pan integral",
    ],
    "gordura": [
        "aceite oliva virgen extra",
        "mantequilla",
        "cacahuete",
        "miel",
    ],
    "bebida": [
        "cafe molido",
        "leche desnatada",
        "leche polvo",
    ],
    "higiene": [
        "champu",
        "pasta dientes",
        "gel ducha",
    ],
    "gato": [
        "pienso gato",
        "arena gato",
    ],
}

# Warehouses do Mercadona por cidade
WAREHOUSE_MAP = {
    "granada": "svq1",       # Sevilla (mais próximo)
    "alicante": "vlc1",      # Valencia
    "nerja": "svq1",         # Sevilla
}


class MercadonaScraper(BaseScraper):
    BASE_URL = "https://tienda.mercadona.es/api"

    def scrape_city(self, city_key: str) -> List[Dict]:
        warehouse = WAREHOUSE_MAP.get(city_key, "svq1")
        products = []
        print(f"  → Mercadona {city_key} (warehouse: {warehouse})...")

        for category, queries in ESSENTIAL_PRODUCTS.items():
            for query in queries:
                try:
                    results = self._search_product(query, warehouse)
                    for result in results[:2]:  # Top 2 por consulta
                        products.append({
                            "source": "mercadona",
                            "city": city_key,
                            "warehouse": warehouse,
                            "category": category,
                            "query": query,
                            "product_name": result.get("display_name", ""),
                            "brand": result.get("brand", ""),
                            "price_eur": result.get("price"),
                            "unit": result.get("unit_name", ""),
                            "url": f"https://tienda.mercadona.es/product/{result.get('id', '')}",
                        })
                except Exception as e:
                    print(f"    [erro] {query}: {e.__class__.__name__}")
                    continue

        print(f"    ✓ {len(products)} produtos")
        return products

    def _search_product(self, query: str, warehouse: str) -> List[Dict]:
        """Busca produto via API não-oficial."""
        url = "https://7uzjkl1dj0-dsn.algolia.net/1/indexes/products_prod_" + warehouse + "_es/query"
        params = {
            "x-algolia-application-id": "7UZJKL1DJ0",
            "x-algolia-api-key": "9d8f2e39e90df472b4f2e559a116fe17",
        }
        payload = {
            "params": f"query={query}&hitsPerPage=3",
        }
        try:
            self.sleep()
            resp = requests.post(url, params=params, json=payload,
                               headers=self.get_headers(), timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for hit in data.get("hits", []):
                    price_data = hit.get("price_instructions", {})
                    results.append({
                        "id": hit.get("id"),
                        "display_name": hit.get("display_name"),
                        "brand": hit.get("brand"),
                        "price": self._extract_price(price_data),
                        "unit_name": price_data.get("unit_name", ""),
                    })
                return results
        except Exception:
            pass
        return []

    def _extract_price(self, price_data: Dict):
        for key in ("unit_price", "bulk_price", "reference_price"):
            val = price_data.get(key)
            if val:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return None
