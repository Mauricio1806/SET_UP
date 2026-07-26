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

    # Múltiplos candidatos por cidade — tenta em ordem até obter resultados
    CITY_PATHS = {
        "granada": [
            "/es/alquiler/viviendas/granada-capital/todas-las-zonas/l",
            "/es/alquiler/pisos/granada-capital/todas-las-zonas/l",
            "/es/alquiler/viviendas/granada/todas-las-zonas/l",
        ],
        "alicante": [
            "/es/alquiler/viviendas/alicante-alacant/todas-las-zonas/l",   # correto
            "/es/alquiler/viviendas/alicante/todas-las-zonas/l",
            "/es/alquiler/pisos/alicante-alacant/todas-las-zonas/l",
        ],
        "nerja": [
            "/es/alquiler/viviendas/nerja/todas-las-zonas/l",
            "/es/alquiler/pisos/nerja/todas-las-zonas/l",
        ],
    }

    def __init__(self, **kwargs):
        kwargs.setdefault("delay_range", (3.0, 6.0))
        super().__init__(**kwargs)

    def scrape_city(self, city_key: str, max_price: int = 1000, max_pages: int = 3) -> List[Dict]:
        listings = []
        seen_urls: set = set()
        paths = self.CITY_PATHS.get(city_key, [])
        if not paths:
            return listings

        # Descobre qual path retorna resultados
        working_path = None
        print(f"  → Fotocasa {city_key} (testando paths)...")
        for candidate in paths:
            test_url = f"{self.BASE_URL}{candidate}"
            html = self.fetch(test_url)
            if html and len(html) > 5000 and "404" not in html[:200]:
                working_path = candidate
                print(f"    ✓ path: {candidate}")
                # Processa a primeira página já carregada
                items = self._extract_from_next_data(html, city_key, max_price)
                if not items:
                    items = self._parse_html(html, city_key, max_price)
                for item in items:
                    if item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        listings.append(item)
                break
            else:
                print(f"    ✗ path sem resultado: {candidate}")

        if not working_path:
            print(f"    [warn] Nenhum path funcionou para {city_key}")
            return listings

        # Páginas restantes
        for page in range(2, max_pages + 1):
            url = f"{self.BASE_URL}{working_path}"
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
        """Extrai dados do JSON __NEXT_DATA__ embutido pelo Next.js."""
        try:
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if not match:
                return []
            data = json.loads(match.group(1))
            # Navega pela estrutura do Next.js
            props = data.get("props", {}).get("pageProps", {})
            result = props.get("initialProps", {}) or props.get("serverSideProps", {})

            # Tenta vários caminhos onde as listagens podem estar
            items_raw = (
                result.get("items") or
                result.get("realEstateLists", {}).get("items") or
                props.get("items") or
                []
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
        """Parse de um item do JSON Next.js do Fotocasa."""
        price_info = item.get("price", {}) or {}
        price = price_info.get("value") or item.get("monthlyPrice")
        if not price:
            return None

        features = item.get("features", {}) or {}
        rooms = features.get("roomsNumber") or item.get("rooms")
        m2    = features.get("constructedArea") or item.get("surface")

        address = item.get("address") or {}
        location_parts = [
            address.get("neighborhoodName", ""),
            address.get("districtName", ""),
        ]
        location = next((p for p in location_parts if p), "")

        property_code = item.get("id") or item.get("realEstateCode", "")
        url_path = item.get("url") or item.get("detail", {}).get("url", "")
        url = url_path if url_path.startswith("http") else f"{self.BASE_URL}{url_path}"
        if not url or url == self.BASE_URL:
            url = f"{self.BASE_URL}/es/inmueble/{property_code}/"

        desc = (item.get("description") or "").lower()
        kitchen_type = self._detect_kitchen(desc)

        title_type = item.get("propertyType") or item.get("typology", {}).get("name", "Piso")
        title = f"{title_type} en {location}".strip() or "Anúncio Fotocasa"

        return {
            "source":         "fotocasa",
            "city":           city_key,
            "title":          title[:120],
            "url":            url,
            "price":          int(price),
            "location":       location[:80],
            "location_raw":   location[:100],
            "rooms":          rooms,
            "m2":             m2,
            "kitchen_type":   kitchen_type,
            "has_cooktop_only": kitchen_type == "cooktop_only",
            "is_seasonal":    False,
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
