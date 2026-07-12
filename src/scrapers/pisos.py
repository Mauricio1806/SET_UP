"""
Pisos.com scraper — fonte alternativa. Menos bloqueio.
"""

from typing import List, Dict
from bs4 import BeautifulSoup
from .base import BaseScraper


class PisosScraper(BaseScraper):
    BASE_URL = "https://www.pisos.com"

    CITY_PATHS = {
        "granada": "/alquiler/pisos-granada_capital/",
        "alicante": "/alquiler/pisos-alicante_capital/",
        "nerja": "/alquiler/pisos-nerja/",
    }

    def scrape_city(self, city_key: str, max_price: int = 1000, max_pages: int = 3) -> List[Dict]:
        listings = []
        path = self.CITY_PATHS.get(city_key)
        if not path:
            print(f"  [info] Pisos.com: cidade {city_key} não mapeada")
            return listings

        print(f"  → Pisos.com {city_key}...")
        for page in range(1, max_pages + 1):
            url = f"{self.BASE_URL}{path}"
            if page > 1:
                url = f"{url}?pagina={page}"

            html = self.fetch(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            cards = (soup.select("div.ad-preview") or soup.select("article") or soup.select("[class*=card]"))

            for card in cards:
                try:
                    listing = self._parse_listing(card, city_key)
                    if listing and listing.get("price") and listing["price"] <= max_price:
                        listings.append(listing)
                except Exception:
                    continue

            if not cards:
                break

        print(f"    ✓ {len(listings)} anúncios ≤ €{max_price}")
        return listings

    def _parse_listing(self, card, city_key: str) -> Dict:
        title_el = (card.select_one(".ad-preview__title") or card.select_one("h2 a") or card.select_one("a"))
        price_el = (card.select_one(".ad-preview__price") or card.select_one("[class*=price]"))
        location_el = card.select_one(".ad-preview__subtitle") or card.select_one("[class*=location]")
        details_el = card.select_one(".ad-preview__char") or card.select_one("[class*=char]")

        if not title_el or not price_el:
            return {}

        href = title_el.get("href", "")
        url = href if href.startswith("http") else self.BASE_URL + href
        details_text = details_el.get_text(" ", strip=True) if details_el else ""

        return {
            "source": "pisos.com",
            "city": city_key,
            "title": title_el.get_text(strip=True),
            "url": url,
            "price": self.parse_price(price_el.get_text()),
            "location": location_el.get_text(strip=True) if location_el else "",
            "rooms": self.parse_rooms(details_text),
            "m2": self.parse_m2(details_text),
            "raw_details": details_text[:200],
        }
