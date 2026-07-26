"""
DIA ES scraper — preços via API pública superdía.es / dia.es.
Endpoint buscável: https://www.dia.es/api/2.0/catalog/search

DIA: ~20% mais barato que Mercadona em básicos.
Presença: Granada ✓, Alicante ✓, Nerja ✓ (cidade pequena — DIA Compra)
"""

import time
import random
from typing import List, Dict, Optional
import requests

from .base import BaseScraper

# Mapeamento itens dieta → busca DIA
DIA_SEARCH_MAP = {
    "pechuga pollo congelada":      "pechuga pollo",
    "arroz integral":               "arroz integral",
    "patatas":                      "patatas bolsa",
    "pan integral rebanado":        "pan integral molde",
    "verduras congeladas mix":      "menestra verduras congelada",
    "mantequilla sin sal":          "mantequilla sin sal",
    "cacahuete natural":            "cacahuetes",
    "aceite oliva virgen extra":    "aceite oliva virgen extra",
    "miel flores":                  "miel",
    "cafe molido natural":          "cafe molido",
    "leche entera":                 "leche entera",
    "ketchup heinz":                "ketchup",
    "salsa teriyaki kikkoman":      "salsa teriyaki",
    "champu anticaspa hombre":      "champu anticaspa",
    "pasta dientes blanqueadora":   "pasta dientes",
    "gel ducha":                    "gel ducha",
    "desodorante roll on":          "desodorante roll on",
    "pienso gato adulto":           "pienso gato",
    "arena gato aglomerante":       "arena gato",
}

DIA_API_URL   = "https://www.dia.es/api/2.0/catalog/search"
DIA_STORE_MAP = {
    "granada":  "1234",   # placeholder — DIA usa storeId mas retorna preços nacionais
    "alicante": "5678",
    "nerja":    "9012",
}


class DiaScraper(BaseScraper):
    """Scraper de preços DIA ES."""

    MARKET_NAME  = "DIA"
    PRICE_FACTOR = 0.80

    def __init__(self, **kwargs):
        super().__init__(delay_range=(1.5, 3.0), **kwargs)

    def _get_dia_headers(self) -> Dict:
        return {
            "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept":       "application/json",
            "Accept-Language": "es-ES,es;q=0.9",
            "Origin":       "https://www.dia.es",
            "Referer":      "https://www.dia.es/compra-online",
        }

    def search_product(self, query: str, store_id: str = "1234") -> Optional[Dict]:
        """Busca produto via API DIA. Retorna melhor match ou None."""
        try:
            time.sleep(random.uniform(1.0, 2.5))
            params = {
                "q":       query,
                "rows":    5,
                "start":   0,
                "storeId": store_id,
            }
            r = self.session.get(
                DIA_API_URL,
                params=params,
                headers=self._get_dia_headers(),
                timeout=15,
            )
            if r.status_code != 200:
                return None

            data = r.json()
            products = (
                data.get("products")
                or data.get("response", {}).get("docs", [])
                or data.get("items", [])
            )
            if not products:
                return None

            for product in products[:3]:
                price = (
                    product.get("price")
                    or product.get("currentPrice")
                    or product.get("priceValue")
                )
                if price:
                    name = (
                        product.get("name")
                        or product.get("displayName")
                        or product.get("title", query)
                    )
                    unit = product.get("unit", product.get("format", ""))
                    return {
                        "product_name": name,
                        "price_eur":    round(float(price), 2),
                        "unit":         unit,
                        "market":       self.MARKET_NAME,
                    }
        except Exception as e:
            print(f"    [DIA] erro busca '{query}': {e}")
        return None

    def scrape_city(self, city_key: str) -> List[Dict]:
        """Coleta preços DIA para itens da dieta. Formato compatível com Mercadona."""
        print(f"    [DIA] scraping {city_key}...")
        store_id = DIA_STORE_MAP.get(city_key, "1234")
        results  = []

        for diet_query, search_term in DIA_SEARCH_MAP.items():
            found = self.search_product(search_term, store_id)
            results.append({
                "city":         city_key,
                "market":       self.MARKET_NAME,
                "query":        diet_query,
                "product_name": found["product_name"] if found else diet_query,
                "price_eur":    found["price_eur"] if found else None,
                "unit":         found.get("unit", "") if found else "",
                "found":        found is not None,
                "source":       "dia_api",
            })

        found_count = sum(1 for r in results if r["found"])
        print(f"    [DIA] {found_count}/{len(results)} itens encontrados")
        return results
