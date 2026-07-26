"""
Lidl ES scraper — preços públicos via API Lidl Plus / catálogo web.
Endpoint: https://www.lidl.es/c/ofertas-de-la-semana/a10008298
API REST pública: api.lidl-statics.com/p/es/nonfood/offers

Estratégia: busca por categoria nos itens da dieta real.
Sem login necessário — preços de catálogo público.
"""

import re
import json
import time
import random
from typing import List, Dict, Optional
import requests

from .base import BaseScraper

# Mapeamento de queries da dieta → busca Lidl
LIDL_SEARCH_MAP = {
    "pechuga pollo congelada":      ["pechuga pollo", "filete pollo"],
    "arroz integral":               ["arroz integral"],
    "patatas":                      ["patatas"],
    "pan integral rebanado":        ["pan integral", "pan molde"],
    "verduras congeladas mix":      ["menestra congelada", "verduras congeladas"],
    "arandanos congelados":         ["arandanos", "frutos rojos congelados"],
    "moras congeladas":             ["moras congeladas"],
    "fresas congeladas":            ["fresas congeladas"],
    "platano banana":               ["platanos", "banana"],
    "mantequilla sin sal":          ["mantequilla sin sal"],
    "cacahuete natural":            ["cacahuetes sin sal", "cacahuetes tostados"],
    "aceite oliva virgen extra":    ["aceite oliva virgen extra"],
    "miel flores":                  ["miel"],
    "cafe molido natural":          ["cafe molido"],
    "leche entera":                 ["leche entera"],
    "leche en polvo entera":        ["leche polvo"],
    "champu anticaspa hombre":      ["champu anticaspa"],
    "pasta dientes blanqueadora":   ["pasta dental", "dentifrico"],
    "gel ducha":                    ["gel ducha"],
    "desodorante roll on":          ["desodorante"],
    "pienso gato adulto":           ["pienso gato"],
    "arena gato aglomerante":       ["arena gato"],
}

LIDL_API_URL = "https://www.lidl.es/api/search/v3/public/search"
LIDL_CATALOG_URL = "https://www.lidl.es/p/es/search"


class LidlScraper(BaseScraper):
    """Scraper de preços Lidl ES — catálogo público."""

    MARKET_NAME = "Lidl"
    PRICE_FACTOR = 0.85  # fallback: ~15% mais barato que Mercadona

    def __init__(self, **kwargs):
        super().__init__(delay_range=(1.5, 3.0), **kwargs)

    def _get_lidl_headers(self) -> Dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-ES,es;q=0.9",
            "Origin": "https://www.lidl.es",
            "Referer": "https://www.lidl.es/",
        }

    def search_product(self, query: str) -> Optional[Dict]:
        """Busca um produto no catálogo Lidl. Retorna melhor match ou None."""
        try:
            time.sleep(random.uniform(1.0, 2.5))
            params = {
                "q": query,
                "page": 1,
                "pageSize": 5,
                "sortBy": "relevance",
                "country": "ES",
                "language": "es",
            }
            r = self.session.get(
                LIDL_API_URL,
                params=params,
                headers=self._get_lidl_headers(),
                timeout=15,
            )
            if r.status_code != 200:
                return None

            data = r.json()
            hits = data.get("results", data.get("hits", []))
            if not hits:
                return None

            # Pegar primeiro resultado com preço
            for hit in hits[:3]:
                price = (
                    hit.get("price")
                    or hit.get("currentRetailPrice")
                    or hit.get("priceData", {}).get("price")
                )
                if price:
                    name = (
                        hit.get("name")
                        or hit.get("fullName")
                        or hit.get("title", query)
                    )
                    return {
                        "product_name": name,
                        "price_eur": round(float(price), 2),
                        "unit": hit.get("unit", hit.get("priceUnit", "")),
                        "market": self.MARKET_NAME,
                    }
        except Exception as e:
            print(f"    [Lidl] erro busca '{query}': {e}")
        return None

    def scrape_city(self, city_key: str) -> List[Dict]:
        """
        Coleta preços Lidl para itens da dieta real.
        Retorna lista de dicts compatível com formato Mercadona.
        """
        print(f"    [Lidl] scraping {city_key}...")
        results = []

        for diet_query, search_terms in LIDL_SEARCH_MAP.items():
            found = None
            for term in search_terms:
                found = self.search_product(term)
                if found:
                    break

            results.append({
                "city":         city_key,
                "market":       self.MARKET_NAME,
                "query":        diet_query,
                "product_name": found["product_name"] if found else diet_query,
                "price_eur":    found["price_eur"] if found else None,
                "unit":         found.get("unit", "") if found else "",
                "found":        found is not None,
                "source":       "lidl_api",
            })

        found_count = sum(1 for r in results if r["found"])
        print(f"    [Lidl] {found_count}/{len(results)} itens encontrados")
        return results
