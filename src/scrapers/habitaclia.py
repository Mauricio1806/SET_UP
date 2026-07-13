"""
Habitaclia scraper v2 — com filtros de inativo, cooktop, sazonal e deduplicação.
"""

import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .base import BaseScraper

INACTIVE_KEYWORDS = [
    'ya no disponible', 'arrendado', 'alquilado', 'reservado',
    'no disponible', 'anuncio eliminado',
]


class HabitacliaScraper(BaseScraper):
    BASE_URL = "https://www.habitaclia.com"

    CITY_PATHS = {
        "granada": "/alquiler-granada_capital.htm",
        "alicante": "/alquiler-alacant_alicante-cap.htm",
        "nerja": "/alquiler-nerja.htm",
    }

    def scrape_city(self, city_key: str, max_price: int = 1000, max_pages: int = 3) -> List[Dict]:
        listings = []
        seen_urls: set = set()
        path = self.CITY_PATHS.get(city_key)
        if not path:
            return listings

        print(f"  → Habitaclia {city_key}...")
        for page in range(1, max_pages + 1):
            url = f"{self.BASE_URL}{path}"
            if page > 1:
                url = url.replace(".htm", f"-{page}.htm")

            html = self.fetch(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            articles = (
                soup.select("article.list-item-container") or
                soup.select("article.property-item") or
                soup.select("article")
            )

            for article in articles:
                try:
                    listing = self._parse_listing(article, city_key)
                    if not listing:
                        continue
                    if not listing.get("price") or listing["price"] > max_price:
                        continue
                    if self._is_inactive(listing):
                        continue
                    if listing["url"] in seen_urls:
                        continue
                    seen_urls.add(listing["url"])
                    listings.append(listing)
                except Exception:
                    continue

            if not articles:
                break

        print(f"    ✓ {len(listings)} anúncios ativos ≤ €{max_price}")
        return listings

    def _parse_listing(self, article, city_key: str) -> Optional[Dict]:
        title_el = (
            article.select_one(".list-item-title a") or
            article.select_one("h3 a") or
            article.select_one("h2 a")
        )
        price_el = (
            article.select_one(".prices-price") or
            article.select_one(".price") or
            article.select_one("[class*=price]")
        )
        details_el = article.select_one(".list-item-details") or article.select_one(".details")
        location_el = (
            article.select_one(".list-item-location") or
            article.select_one(".location") or
            article.select_one(".list-item-address")
        )
        desc_el = article.select_one(".list-item-description") or article.select_one("[class*=desc]")

        if not title_el or not price_el:
            return None

        href = title_el.get("href", "")
        url = href if href.startswith("http") else self.BASE_URL + href
        details_text = details_el.get_text(" ", strip=True) if details_el else ""
        desc_text = desc_el.get_text(" ", strip=True) if desc_el else ""
        full_text = f"{details_text} {desc_text}".lower()

        location_raw = location_el.get_text(strip=True) if location_el else ""
        location_clean = self._clean_location(location_raw) or title_el.get_text(strip=True)

        kitchen_type = self._detect_kitchen(full_text)
        is_seasonal = self._is_seasonal(full_text)

        return {
            "source": "habitaclia",
            "city": city_key,
            "title": title_el.get_text(strip=True)[:120],
            "url": url,
            "price": self.parse_price(price_el.get_text()),
            "location": location_clean[:80],
            "location_raw": location_raw[:100],
            "rooms": self.parse_rooms(details_text),
            "m2": self.parse_m2(details_text),
            "raw_details": full_text[:300],
            "kitchen_type": kitchen_type,
            "is_seasonal": is_seasonal,
            "has_cooktop_only": kitchen_type == "cooktop_only",
        }

    def _clean_location(self, loc: str) -> str:
        if not loc:
            return ""
        parts = [p.strip() for p in re.split(r'[,·|]', loc)]
        filtered = [p for p in parts if p and len(p) > 2
                    and p.lower() not in ('granada', 'alicante', 'nerja', 'spain')]
        return (filtered[0] if filtered else parts[0] if parts else loc)[:80]

    def _detect_kitchen(self, text: str) -> str:
        for kw in ['microondas', 'cocina americana', 'sin cocina']:
            if kw in text:
                return "cooktop_only"
        for kw in ['fogón', 'placa de gas', 'vitrocerámica', 'cocina completa']:
            if kw in text:
                return "gas_or_full"
        return "unknown"

    def _is_inactive(self, listing: Dict) -> bool:
        text = f"{listing.get('raw_details','')} {listing.get('title','')}".lower()
        return any(kw in text for kw in INACTIVE_KEYWORDS)

    def _is_seasonal(self, text: str) -> bool:
        return any(kw in text for kw in ['temporada', 'vacacional', 'turístico'])
