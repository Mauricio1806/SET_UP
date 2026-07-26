"""
Pisos.com scraper v4 — filtro geográfico rigoroso por cidade.
"""

import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .base import BaseScraper

INACTIVE_KEYWORDS = [
    'ya no disponible', 'arrendado', 'alquilado', 'reservado', 'no disponible',
]

CARD_SELECTORS = [
    "div.ad-preview", "article.property-listing", "article.ad-preview",
    "[class*=ad-preview]", "[class*=property-listing]", "[class*=PropertyCard]",
    "article[data-ad-id]", "article[data-id]", "li[data-ad-id]", "li[data-id]",
    "article",
]

# Termos geográficos que CONFIRMAM que o anúncio é da cidade certa
CITY_GEO_TERMS = {
    "granada": [
        "granada", "zaidín", "albaicín", "realejo", "beiro", "chana",
        "cartuja", "camino de ronda", "ronda", "genil", "figares",
        "arabial", "pajaritos", "sacromonte", "armilla", "vegas",
    ],
    "alicante": [
        "alicante", "alacant", "benalúa", "carolinas", "ciudad jardín",
        "playa san juan", "vistahermosa", "florida", "babel",
        "san blas", "centro", "castillo", "ensanche",
    ],
    "nerja": [
        "nerja", "capistrano", "parador", "balcón de europa",
        "burriana", "torrecilla", "maro",
    ],
}

# Termos que indicam que o anúncio é de OUTRA cidade (descartar)
FOREIGN_CITY_TERMS = [
    "barcelona", "madrid", "sevilla", "valència", "valencia capital",
    "bilbao", "málaga capital", "murcia", "palma", "zaragoza",
    "sant sadurní", "sabadell", "terrassa", "hospitalet",
    "badalona", "cornellà", "l'hospitalet",
]


class PisosScraper(BaseScraper):
    BASE_URL = "https://www.pisos.com"

    CITY_PATHS = {
        "granada": [
            "/alquiler/pisos-granada_capital/",
            "/alquiler/pisos-granada/",
        ],
        "alicante": [
            "/alquiler/pisos-alicante/",
            "/alquiler/pisos-alacant_alicante-cap/",
            "/alquiler/pisos-alicante_capital/",
        ],
        "nerja": [
            "/alquiler/pisos-nerja/",
        ],
    }

    def scrape_city(self, city_key: str, max_price: int = 9999, max_pages: int = 3) -> List[Dict]:
        listings = []
        seen_urls: set = set()
        paths = self.CITY_PATHS.get(city_key, [])
        if not paths:
            return listings

        working_path = None
        working_selector = None
        print(f"  → Pisos.com {city_key}...")

        for candidate in paths:
            test_url = f"{self.BASE_URL}{candidate}"
            html = self.fetch(test_url)
            if not html or len(html) < 3000:
                print(f"    ✗ vazio/bloqueado: {candidate}")
                continue
            if "404" in html[:200] or "página no encontrada" in html.lower()[:500]:
                print(f"    ✗ 404: {candidate}")
                continue

            soup = BeautifulSoup(html, "html.parser")
            cards, sel_found = [], None
            for sel in CARD_SELECTORS:
                cands = soup.select(sel)
                valid = [c for c in cands if re.search(r'\d{3,4}\s*[€e]', c.get_text())]
                if valid:
                    cards = cands
                    sel_found = sel
                    break

            if not cards:
                print(f"    ✗ sem cards: {candidate}")
                continue

            working_path = candidate
            working_selector = sel_found
            print(f"    ✓ path: {candidate} | {sel_found!r} | {len(cards)} cards")

            for card in cards:
                try:
                    listing = self._parse_listing(card, city_key)
                    if not listing or not listing.get("price"):
                        continue
                    if listing["price"] > max_price:
                        continue
                    if listing["price"] < 200:          # preço impossível — dado errado
                        continue
                    if self._is_inactive(listing):
                        continue
                    if not self._is_correct_city(listing, city_key):
                        continue
                    if listing["url"] in seen_urls:
                        continue
                    seen_urls.add(listing["url"])
                    listings.append(listing)
                except Exception:
                    continue
            break

        if not working_path:
            print(f"    [warn] Pisos.com {city_key}: nenhum path funcionou")
            return listings

        for page in range(2, max_pages + 1):
            url = f"{self.BASE_URL}{working_path}?pagina={page}"
            html = self.fetch(url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(working_selector) if working_selector else []
            new = 0
            for card in cards:
                try:
                    listing = self._parse_listing(card, city_key)
                    if not listing or not listing.get("price"):
                        continue
                    if listing["price"] > max_price or listing["price"] < 200:
                        continue
                    if self._is_inactive(listing) or not self._is_correct_city(listing, city_key):
                        continue
                    if listing["url"] in seen_urls:
                        continue
                    seen_urls.add(listing["url"])
                    listings.append(listing)
                    new += 1
                except Exception:
                    continue
            print(f"    página {page}: {new} novos")
            if not cards:
                break

        print(f"    ✓ {len(listings)} anúncios Pisos.com ≤ €{max_price}")
        return listings

    def _is_correct_city(self, listing: Dict, city_key: str) -> bool:
        """Verifica se o anúncio é realmente da cidade alvo."""
        # Textos a verificar
        texts = [
            listing.get("title", ""),
            listing.get("location", ""),
            listing.get("location_raw", ""),
            listing.get("raw_details", ""),
        ]
        full_text = " ".join(t for t in texts if t).lower()

        # Rejeita se contém termos de outras cidades
        for term in FOREIGN_CITY_TERMS:
            if term in full_text:
                return False

        # Aceita se contém termo geográfico da cidade certa
        geo_terms = CITY_GEO_TERMS.get(city_key, [])
        for term in geo_terms:
            if term in full_text:
                return True

        # Sem confirmação geográfica — rejeita por segurança
        return False

    def _parse_listing(self, card, city_key: str) -> Optional[Dict]:
        title_el = (
            card.select_one(".ad-preview__title a") or
            card.select_one("h2 a") or card.select_one("h3 a") or
            card.select_one("[class*=title] a") or
            card.select_one("a[href*='/alquiler/']") or
            card.select_one("a[href]")
        )
        price_el = (
            card.select_one(".ad-preview__price") or
            card.select_one("[class*=price]") or
            card.select_one("[class*=Price]")
        )
        location_el = (
            card.select_one(".ad-preview__subtitle") or
            card.select_one("[class*=location]") or
            card.select_one("[class*=address]")
        )
        details_el = (
            card.select_one(".ad-preview__char") or
            card.select_one("[class*=char]") or
            card.select_one("[class*=features]")
        )

        if not title_el:
            return None

        href = title_el.get("href", "")
        url = href if href.startswith("http") else self.BASE_URL + href
        if not url or url == self.BASE_URL:
            return None

        price = None
        if price_el:
            price = self.parse_price(price_el.get_text())
        if not price:
            m = re.search(r'(\d{3,4})\s*[€]', card.get_text())
            if m:
                price = int(m.group(1))

        details_text = details_el.get_text(" ", strip=True) if details_el else ""
        full_text = card.get_text(" ", strip=True).lower()
        location_raw = location_el.get_text(strip=True) if location_el else ""

        return {
            "source": "pisos.com",
            "city": city_key,
            "title": title_el.get_text(strip=True)[:120],
            "url": url,
            "price": price,
            "location": self._clean_location(location_raw),
            "location_raw": location_raw[:100],
            "rooms": self.parse_rooms(details_text),
            "m2": self.parse_m2(details_text),
            "raw_details": full_text[:300],
            "kitchen_type": self._detect_kitchen(full_text),
            "has_cooktop_only": self._detect_kitchen(full_text) == "cooktop_only",
            "is_seasonal": self._is_seasonal(full_text),
        }

    def _clean_location(self, loc: str) -> str:
        if not loc:
            return ""
        parts = [p.strip() for p in re.split(r'[,·|]', loc)]
        filtered = [p for p in parts if p and len(p) > 2
                    and p.lower() not in ('granada', 'alicante', 'nerja', 'spain')]
        return (filtered[0] if filtered else parts[0] if parts else loc)[:80]

    def _detect_kitchen(self, text: str) -> str:
        for kw in ['microondas', 'cocina americana', 'sin cocina', 'kitchenette']:
            if kw in text:
                return "cooktop_only"
        for kw in ['fogón', 'fogones', 'placa de gas', 'vitrocerámica',
                   'cocina completa', 'cocina equipada', 'cocina con gas']:
            if kw in text:
                return "gas_or_full"
        return "unknown"

    def _is_inactive(self, listing: Dict) -> bool:
        text = f"{listing.get('raw_details','')} {listing.get('title','')}".lower()
        return any(kw in text for kw in INACTIVE_KEYWORDS)

    def _is_seasonal(self, text: str) -> bool:
        return any(kw in text for kw in ['temporada', 'vacacional', 'turístico'])
