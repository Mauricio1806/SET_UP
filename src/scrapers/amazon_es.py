"""
Amazon.es scraper — suplementos que NÃO existem no Mercadona.
Foco: whey protein, creatina, vitaminas.

Estratégia: Amazon Product Advertising API via afiliados públicos,
ou fallback para scraping do resultado de busca com parsing de JSON-LD.

Itens alvo (30 itens dieta — só os ausentes do Mercadona):
  - proteina whey 2kg (HSN, MyProtein, Gold Standard)
  - creatina monohidrato 150g (HSN, MyProtein)
  - vitamina D3 + K2 (opcional)
  - multivitamínico (opcional)
"""

import re
import time
import random
import json
from typing import List, Dict, Optional
import requests

from .base import BaseScraper

# Suplementos a monitorar — busca direta Amazon.es
SUPPLEMENT_SEARCHES = [
    {
        "query":        "creatina monohidrato",
        "diet_query":   "creatina monohidrato",
        "search_term":  "HSN creatina monohidrato 300g",
        "preferred_brands": ["HSN", "MyProtein", "Optimum", "Prozis"],
        "target_size":  "300g",
        "monthly_qty":  0.5,   # 150g/mês = meia embalagem de 300g
    },
    {
        "query":        "proteina whey",
        "diet_query":   "proteina whey",
        "search_term":  "HSN whey protein 2kg chocolate",
        "preferred_brands": ["HSN", "MyProtein", "Gold Standard", "Prozis"],
        "target_size":  "2kg",
        "monthly_qty":  1.0,   # 2kg/mês = 1 embalagem
    },
    {
        "query":        "vitamina D3 K2",
        "diet_query":   "vitamina D3 K2",
        "search_term":  "vitamina D3 K2 suplemento",
        "preferred_brands": ["HSN", "Solgar", "Now Foods"],
        "target_size":  "60-90 caps",
        "monthly_qty":  1.0,
    },
]

# URL busca Amazon.es
AMAZON_SEARCH_URL = "https://www.amazon.es/s"


class AmazonEsScraper(BaseScraper):
    """Scraper Amazon.es para suplementos — parsing JSON-LD + regex."""

    MARKET_NAME  = "Amazon.es"
    PRICE_FACTOR = 1.0  # referência própria, não comparar com Mercadona

    def __init__(self, **kwargs):
        super().__init__(delay_range=(3.0, 6.0), timeout=25, **kwargs)

    def _get_amazon_headers(self) -> Dict:
        return {
            "User-Agent":      (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer":         "https://www.amazon.es/",
            "DNT":             "1",
        }

    def _parse_price_from_html(self, html: str, brand_pref: List[str]) -> Optional[Dict]:
        """Extrai preço do HTML Amazon via regex e JSON-LD."""
        # Tentar JSON-LD primeiro
        json_ld_matches = re.findall(
            r'"price"\s*:\s*"?([\d,\.]+)"?', html
        )
        price = None
        for match in json_ld_matches:
            try:
                p = float(match.replace(",", "."))
                if 5.0 < p < 200.0:   # range razoável para suplementos
                    price = p
                    break
            except ValueError:
                continue

        # Fallback: regex de preço visível
        if not price:
            price_patterns = [
                r'class="a-price-whole">(\d+)<',
                r'"priceAmount":([\d\.]+)',
                r'data-asin-price="([\d\.]+)"',
                r'"price":\{"value":([\d\.]+)',
            ]
            for pattern in price_patterns:
                m = re.search(pattern, html)
                if m:
                    try:
                        p = float(m.group(1))
                        if 5.0 < p < 200.0:
                            price = p
                            break
                    except ValueError:
                        continue

        # Nome do produto
        name_m = re.search(r'"name"\s*:\s*"([^"]{10,100})"', html)
        product_name = name_m.group(1) if name_m else "Suplemento Amazon.es"

        if price:
            return {
                "product_name": product_name[:80],
                "price_eur":    round(price, 2),
                "market":       self.MARKET_NAME,
            }
        return None

    def search_product(self, item: Dict) -> Optional[Dict]:
        """Busca suplemento na Amazon.es. Retorna preço ou None."""
        search_term = item["search_term"]
        try:
            time.sleep(random.uniform(3.0, 6.0))
            params = {"k": search_term, "ref": "nb_sb_noss"}
            r = self.session.get(
                AMAZON_SEARCH_URL,
                params=params,
                headers=self._get_amazon_headers(),
                timeout=self.timeout,
            )
            if r.status_code != 200:
                print(f"    [Amazon.es] status {r.status_code} para '{search_term}'")
                return None

            html   = r.text
            result = self._parse_price_from_html(html, item["preferred_brands"])
            return result

        except Exception as e:
            print(f"    [Amazon.es] erro busca '{search_term}': {e}")
            return None

    def scrape_city(self, city_key: str) -> List[Dict]:
        """
        Scrapa preços suplementos Amazon.es.
        Retorna mesmo formato dos outros scrapers mas com market=Amazon.es.
        Preços são iguais para todas as cidades (Amazon.es nacional).
        """
        print(f"    [Amazon.es] scraping suplementos ({city_key})...")
        results = []

        for item in SUPPLEMENT_SEARCHES:
            # Evitar re-fetch se já temos resultado para outra cidade
            found = self.search_product(item)
            results.append({
                "city":         city_key,
                "market":       self.MARKET_NAME,
                "query":        item["diet_query"],
                "product_name": found["product_name"] if found else item["search_term"],
                "price_eur":    found["price_eur"] if found else None,
                "unit":         item.get("target_size", ""),
                "monthly_qty":  item.get("monthly_qty", 1.0),
                "found":        found is not None,
                "source":       "amazon_es",
            })
            time.sleep(random.uniform(2.0, 4.0))

        found_count = sum(1 for r in results if r["found"])
        print(f"    [Amazon.es] {found_count}/{len(results)} suplementos com preço")
        return results
