"""
Consum ES scraper — cooperativa valenciana com forte presença em Alicante.
API pública: tienda.consum.es/api/rest/products/search

Consum: ~8% mais barato que Mercadona em proteínas e laticínios.
Presença: Alicante ✓✓ (forte), Granada ✓ (limitada), Nerja ✗
"""

import time
import random
from typing import List, Dict, Optional
import requests

from .base import BaseScraper

# Consum é relevante principalmente em Alicante
CONSUM_CITIES = {"alicante", "granada"}

CONSUM_SEARCH_MAP = {
    "pechuga pollo congelada":      "pechuga pollo",
    "claras huevo pasteurizadas":   "claras huevo",
    "huevos medianos":              "huevos M",
    "leche entera":                 "leche entera",
    "leche en polvo entera":        "leche polvo",
    "queso manchego curado":        "queso manchego",
    "queso mozzarella":             "mozzarella",
    "arroz integral":               "arroz integral",
    "patatas":                      "patatas",
    "pan integral rebanado":        "pan integral",
    "verduras congeladas mix":      "verduras congeladas",
    "mantequilla sin sal":          "mantequilla sin sal",
    "aceite oliva virgen extra":    "aceite oliva virgen extra",
    "cafe molido natural":          "cafe molido",
    "ketchup heinz":                "ketchup heinz",
}

CONSUM_API_URL = "https://tienda.consum.es/api/rest/V1.5/catalog/search"


class ConsumScraper(BaseScraper):
    """Scraper de preços Consum ES — cooperativa valenciana."""

    MARKET_NAME  = "Consum"
    PRICE_FACTOR = 0.92

    def __init__(self, **kwargs):
        super().__init__(delay_range=(2.0, 4.0), **kwargs)

    def _get_consum_headers(self) -> Dict:
        return {
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept":          "application/json",
            "Accept-Language": "es-ES,es;q=0.9,ca;q=0.8",
            "Origin":          "https://tienda.consum.es",
            "Referer":         "https://tienda.consum.es/",
        }

    def search_product(self, query: str) -> Optional[Dict]:
        """Busca produto na API Consum. Retorna melhor match ou None."""
        try:
            time.sleep(random.uniform(1.5, 3.0))
            params = {
                "query":    query,
                "rows":     5,
                "start":    0,
                "orderBy":  "RELEVANCE",
            }
            r = self.session.get(
                CONSUM_API_URL,
                params=params,
                headers=self._get_consum_headers(),
                timeout=15,
            )
            if r.status_code != 200:
                return None

            data     = r.json()
            products = data.get("products", data.get("items", []))
            if not products:
                return None

            for product in products[:3]:
                price = (
                    product.get("price")
                    or product.get("currentPrice")
                    or product.get("priceWithDiscount")
                    or (product.get("prices", [{}])[0].get("value") if product.get("prices") else None)
                )
                if price:
                    name = product.get("name", product.get("description", query))
                    return {
                        "product_name": name,
                        "price_eur":    round(float(price), 2),
                        "unit":         product.get("unitOfMeasure", product.get("format", "")),
                        "market":       self.MARKET_NAME,
                    }
        except Exception as e:
            print(f"    [Consum] erro busca '{query}': {e}")
        return None

    def scrape_city(self, city_key: str) -> List[Dict]:
        """Coleta preços Consum. Só roda para cidades com presença real."""
        if city_key not in CONSUM_CITIES:
            print(f"    [Consum] sem lojas em {city_key} — skip")
            return []

        print(f"    [Consum] scraping {city_key}...")
        results = []

        for diet_query, search_term in CONSUM_SEARCH_MAP.items():
            found = self.search_product(search_term)
            results.append({
                "city":         city_key,
                "market":       self.MARKET_NAME,
                "query":        diet_query,
                "product_name": found["product_name"] if found else diet_query,
                "price_eur":    found["price_eur"] if found else None,
                "unit":         found.get("unit", "") if found else "",
                "found":        found is not None,
                "source":       "consum_api",
            })

        found_count = sum(1 for r in results if r["found"])
        print(f"    [Consum] {found_count}/{len(results)} itens encontrados")
        return results
