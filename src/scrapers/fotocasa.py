"""
Fotocasa scraper — segunda melhor fonte depois do Idealista.
Menos anti-bot que o Idealista. Funciona sem API key.
"""

import re
import json
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .base import BaseScraper

INACTIVE_KEYWORDS = [
    'ya no disponible', 'arrendado', 'alquilado', 'reservado', 'no disponible',
]


class FotocasaScraper(BaseScraper):
    BASE_URL = "https://www.fotocasa.es"

    CITY_PATHS = {
        "granada":  "/es/alquiler/viviendas/granada-capital/todas-las-zonas/l",
        "alicante": "/es/alquiler/viviendas/alicante-capital/todas-las-zonas/l",
        "nerja":    "/es/alquiler/viviendas/nerja/todas-las-zonas/l",
    }

    def __init__(self, **kwargs):
        kwargs.setdefault("delay_range", (3.0, 6.0))
        super().__init__(**kwargs)

    def scrape_city(self, city_key: str, max_price: int = 1000, max_pages: int = 3) -> List[Dict]:
        listings = []
        seen_urls: set = set()
        path = self.CITY_PATHS.get(city_key)
        if not path:
            return listings

        print(f"  → Fotocasa {city_key}...")
        for page in range(1, max_pages + 1):
            url = f"{self.BASE_URL}{path}"
            if page > 1:
                url = f"{url}?combinedLocationIds=0_0_0_0_0_0_0_0_{page}"

            html = self.fetch(url)
            if not html:
                continue

            # Fotocasa embute JSON com os dados no __NEXT_DATA__
            items = self._extract_from_next_data(html, city_key, max_price)
            if items:
                for item in items:
                    if item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        listings.append(item)
                print(f"    página {page}: {len(items)} anúncios (JSON embutido)")
            else:
                # Fallback: parse HTML direto
                items = self._parse_html(html, city_key, max_price)
                for item in items:
                    if item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        listings.append(item)
                print(f"    página {page}: {len(items)} anúncios (HTML parse)")

            if not items:
                break

        print(f"    ✓ {len(listings)} anúncios Fotocasa ≤ €{max_price}")
        return listings

    def _extract_from_next_data(self, html: str, city_key: str, max_price: int) -> List[Dict]:
        """Extrai dados do JSON __initial_props__ embutido pelo Fotocasa."""
        try:
            match = re.search(
                r'<script[^>]*id="__initial_props__"[^>]*>(.*?)</script>', html, re.DOTALL
            )
            if not match:
                return []
            data = json.loads(match.group(1))
            items_raw = (
                data.get("initialSearch", {}).get("result", {})
                    .get("resultsV2", {}).get("items")
                or data.get("initialSearch", {}).get("result", {}).get("realEstates")
                or []
            )

            listings = []
            for item in items_raw:
                try:
                    parsed = self._parse_next_item(item, city_key)
                    if parsed and parsed.get("price") and parsed["price"] <= max_price:
                        listings.append(parsed)
                except Exception:
                    continue
            return listings
        except Exception:
            return []

    def _parse_next_item(self, item: Dict, city_key: str) -> Optional[Dict]:
        """Parse de um item do JSON __initial_props__ do Fotocasa."""
        price = (item.get("price") or {}).get("amount")
        if not price:
            return None

        features = item.get("features", {}) or {}
        rooms = features.get("rooms")
        m2 = features.get("surface")

        location = item.get("location", {}) or {}
        location_name = location.get("municipality") or location.get("zone") or ""

        property_code = item.get("propertyId") or item.get("id", "")
        url_path = item.get("detailUrl", "")
        url = url_path if url_path.startswith("http") else f"{self.BASE_URL}{url_path}"
        if not url or url == self.BASE_URL:
            url = f"{self.BASE_URL}/es/inmueble/{property_code}/"

        desc = (location.get("address") or "").lower()
        kitchen_type = "unknown"

        ptype = "Estudio" if features.get("rooms") == 0 else "Piso"
        title = f"{ptype} en {location_name}".strip() or "Anúncio Fotocasa"

        return {
            "source":         "fotocasa",
            "city":           city_key,
            "title":          title[:120],
            "url":            url,
            "price":          int(price),
            "location":       location_name[:80],
            "location_raw":   (location.get("address") or "")[:100],
            "rooms":          rooms,
            "m2":             m2,
            "kitchen_type":   kitchen_type,
            "has_cooktop_only": False,
            "is_seasonal":    bool(item.get("isTemporaryRental")),
            "raw_details":    desc[:300],
        }

    def _parse_html(self, html: str, city_key: str, max_price: int) -> List[Dict]:
        """Parse HTML direto como fallback."""
        soup = BeautifulSoup(html, "html.parser")
        cards = (
            soup.select("article[data-testid='cardDetail']") or
            soup.select("article.re-CardPackMinimal") or
            soup.select("article") or
            soup.select("[class*='Card']")
        )
        listings = []
        for card in cards:
            try:
                price_el = (card.select_one("[class*='price']") or
                            card.select_one("[class*='Price']"))
                title_el = (card.select_one("a[class*='Link']") or
                            card.select_one("a[href*='/inmueble/']") or
                            card.select_one("a"))
                if not price_el or not title_el:
                    continue

                price = self.parse_price(price_el.get_text())
                if not price or price > max_price:
                    continue

                href = title_el.get("href", "")
                url = href if href.startswith("http") else self.BASE_URL + href

                desc = card.get_text(" ", strip=True).lower()
                kitchen_type = self._detect_kitchen(desc)

                listings.append({
                    "source":          "fotocasa",
                    "city":            city_key,
                    "title":           (title_el.get("title") or title_el.get_text(strip=True))[:120],
                    "url":             url,
                    "price":           price,
                    "location":        "",
                    "location_raw":    "",
                    "rooms":           self.parse_rooms(desc),
                    "m2":              self.parse_m2(desc),
                    "kitchen_type":    kitchen_type,
                    "has_cooktop_only": kitchen_type == "cooktop_only",
                    "is_seasonal":     False,
                    "raw_details":     desc[:300],
                })
            except Exception:
                continue
        return listings

    def _detect_kitchen(self, text: str) -> str:
        cooktop = ['microondas', 'sin cocina', 'kitchenette', 'cocina americana sin']
        full    = ['fogón', 'placa de gas', 'vitrocerámica', 'cocina completa', 'cocina equipada']
        for kw in cooktop:
            if kw in text: return "cooktop_only"
        for kw in full:
            if kw in text: return "gas_or_full"
        return "unknown"
