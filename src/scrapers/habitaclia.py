"""
Habitaclia scraper — menos bloqueio anti-bot que Idealista.
"""

from typing import List, Dict
from bs4 import BeautifulSoup
from .base import BaseScraper


class HabitacliaScraper(BaseScraper):
    BASE_URL = "https://www.habitaclia.com"

    CITY_PATHS = {
        "granada": "/alquiler-granada_capital.htm",
        "alicante": "/alquiler-alacant_alicante-cap.htm",
        "nerja": "/alquiler-nerja.htm",
    }

    def scrape_city(self, city_key: str, max_price: int = 1000, max_pages: int = 3) -> List[Dict]:
        listings = []
        path = self.CITY_PATHS.get(city_key)
        if not path:
            print(f"  [info] Habitaclia: cidade {city_key} não mapeada")
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
            articles = soup.select("article.list-item-container") or soup.select("article")

            for article in articles:
                try:
                    listing = self._parse_listing(article, city_key)
                    if listing and listing.get("price") and listing["price"] <= max_price:
                        listings.append(listing)
                except Exception:
                    continue

            if not articles:
                break

        print(f"    ✓ {len(listings)} anúncios ≤ €{max_price}")
        return listings

    def _parse_listing(self, article, city_key: str) -> Dict:
        title_el = (article.select_one(".list-item-title a") or article.select_one("h3 a") or article.select_one("a"))
        price_el = (article.select_one(".prices-price") or article.select_one(".price") or article.select_one("[class*=price]"))
        details_el = article.select_one(".list-item-details") or article.select_one(".details")
        location_el = article.select_one(".list-item-title") or article.select_one("h3")

        if not title_el or not price_el:
            return {}

        href = title_el.get("href", "")
        url = href if href.startswith("http") else self.BASE_URL + href

        details_text = details_el.get_text(" ", strip=True) if details_el else ""

        return {
            "source": "habitaclia",
            "city": city_key,
            "title": title_el.get_text(strip=True),
            "url": url,
            "price": self.parse_price(price_el.get_text()),
            "location": location_el.get_text(strip=True) if location_el else "",
            "rooms": self.parse_rooms(details_text),
            "m2": self.parse_m2(details_text),
            "raw_details": details_text[:200],
        }
