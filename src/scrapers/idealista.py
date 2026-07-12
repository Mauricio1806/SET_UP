"""
Idealista scraper — a fonte que o Mauricio quer prioritariamente.
Aviso: Idealista tem Cloudflare forte. Este scraper tenta com técnicas
básicas mas provavelmente vai ser bloqueado em muitas execuções.
Se bloquear, cai automaticamente para Habitaclia/Pisos como fonte principal.
"""

from typing import List, Dict
from bs4 import BeautifulSoup
from .base import BaseScraper


class IdealistaScraper(BaseScraper):
    BASE_URL = "https://www.idealista.com"

    CITY_PATHS = {
        "granada": "/alquiler-viviendas/granada-granada/",
        "alicante": "/alquiler-viviendas/alicante-alacant/",
        "nerja": "/alquiler-viviendas/nerja-malaga/",
    }

    def __init__(self, **kwargs):
        # Idealista precisa de delays maiores
        super().__init__(delay_range=(5.0, 10.0), **kwargs)

    def scrape_city(self, city_key: str, max_price: int = 1000, max_pages: int = 2) -> List[Dict]:
        listings = []
        path = self.CITY_PATHS.get(city_key)
        if not path:
            return listings

        print(f"  → Idealista {city_key} (tentativa com anti-bot)...")
        for page in range(1, max_pages + 1):
            url = f"{self.BASE_URL}{path}"
            if page > 1:
                url = f"{url}pagina-{page}.htm"

            html = self.fetch(url)
            if not html:
                continue

            # Detecta bloqueio Cloudflare
            if "Just a moment" in html or "cf-mitigated" in html or "Access denied" in html:
                print(f"    [bloqueado] Cloudflare em Idealista — pulando")
                return listings

            soup = BeautifulSoup(html, "html.parser")
            articles = soup.select("article.item") or soup.select("article[data-element-id]")

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
        title_el = article.select_one(".item-link") or article.select_one("a.item-link")
        price_el = article.select_one(".item-price")
        details_el = article.select_one(".item-detail-char")
        desc_el = article.select_one(".item-description")

        if not title_el or not price_el:
            return {}

        href = title_el.get("href", "")
        url = href if href.startswith("http") else self.BASE_URL + href
        details_text = details_el.get_text(" ", strip=True) if details_el else ""

        return {
            "source": "idealista",
            "city": city_key,
            "title": title_el.get("title") or title_el.get_text(strip=True),
            "url": url,
            "price": self.parse_price(price_el.get_text()),
            "location": title_el.get_text(strip=True),
            "rooms": self.parse_rooms(details_text),
            "m2": self.parse_m2(details_text),
            "raw_details": (desc_el.get_text(" ", strip=True) if desc_el else details_text)[:200],
        }
