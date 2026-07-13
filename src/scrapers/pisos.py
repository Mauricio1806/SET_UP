"""
Pisos.com scraper v2 — com:
- filtro de anúncios fechados/inativos
- detecção de cooktop vs fogão real
- deduplicação por URL
- extração de rua/bairro da localização
"""

import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .base import BaseScraper


# Palavras que indicam cozinha com fogão real (não cooktop)
GAS_KEYWORDS = [
    'cocina con gas', 'cocina de gas', 'fogón', 'fogones',
    'cocina equipada', 'vitrocerámica', 'placa de gas',
]
COOKTOP_ONLY = [
    'microondas', 'solo microondas', 'cocina americana',
    'sin cocina', 'kitchenette',
]

# Indicadores de anúncio fechado/inativo
INACTIVE_KEYWORDS = [
    'ya no disponible', 'arrendado', 'alquilado', 'reservado',
    'no disponible', 'vendido', 'this property is no longer available',
    'anuncio eliminado', 'anuncio expirado',
]


class PisosScraper(BaseScraper):
    BASE_URL = "https://www.pisos.com"

    CITY_PATHS = {
        "granada": "/alquiler/pisos-granada_capital/",
        "alicante": "/alquiler/pisos-alicante_capital/",
        "nerja": "/alquiler/pisos-nerja/",
    }

    def scrape_city(self, city_key: str, max_price: int = 1000, max_pages: int = 3) -> List[Dict]:
        listings = []
        seen_urls: set = set()
        path = self.CITY_PATHS.get(city_key)
        if not path:
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
            cards = (
                soup.select("div.ad-preview") or
                soup.select("article.property-listing") or
                soup.select("[class*=ad-preview]")
            )

            for card in cards:
                try:
                    listing = self._parse_listing(card, city_key)
                    if not listing:
                        continue
                    # Filtros
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

            if not cards:
                break

        print(f"    ✓ {len(listings)} anúncios ativos ≤ €{max_price}")
        return listings

    def _parse_listing(self, card, city_key: str) -> Optional[Dict]:
        title_el = (
            card.select_one("a.ad-preview__title") or
            card.select_one(".ad-preview__title a") or
            card.select_one("h2 a") or
            card.select_one(".property-title a") or
            card.select_one("a[href*='/alquilar/']") or
            card.select_one("a[href*='/alquiler/']")
        )
        price_el = (
            card.select_one(".ad-preview__price") or
            card.select_one("[class*=price]")
        )
        location_el = (
            card.select_one(".ad-preview__subtitle") or
            card.select_one("[class*=location]") or
            card.select_one(".ad-preview__address")
        )
        details_el = (
            card.select_one(".ad-preview__char") or
            card.select_one("[class*=char]") or
            card.select_one(".property-features")
        )
        desc_el = (
            card.select_one(".ad-preview__description") or
            card.select_one("[class*=description]")
        )

        if not title_el or not price_el:
            return None

        href = title_el.get("href", "")
        url = href if href.startswith("http") else self.BASE_URL + href
        details_text = details_el.get_text(" ", strip=True) if details_el else ""
        desc_text = desc_el.get_text(" ", strip=True) if desc_el else ""
        full_text = f"{details_text} {desc_text}".lower()

        # Extrai localização real (rua/bairro)
        location_raw = location_el.get_text(strip=True) if location_el else ""
        location_clean = self._clean_location(location_raw)

        # Detecta fogão vs cooktop
        kitchen_type = self._detect_kitchen(full_text)

        # Detecta se temporada (>3 meses = longa duração ok)
        is_seasonal = self._is_seasonal(full_text)

        return {
            "source": "pisos.com",
            "city": city_key,
            "title": title_el.get_text(strip=True)[:120],
            "url": url,
            "price": self.parse_price(price_el.get_text()),
            "location": location_clean,
            "location_raw": location_raw[:100],
            "rooms": self.parse_rooms(details_text),
            "m2": self.parse_m2(details_text),
            "raw_details": full_text[:300],
            "kitchen_type": kitchen_type,   # 'gas', 'electric', 'unknown'
            "is_seasonal": is_seasonal,
            "has_cooktop_only": kitchen_type == "cooktop_only",
        }

    def _clean_location(self, loc: str) -> str:
        """Remove lixo de localização e extrai parte útil."""
        if not loc:
            return ""
        # Pisos.com geralmente retorna: 'Zaidín, Granada'
        parts = [p.strip() for p in re.split(r'[,·|]', loc)]
        # Filtra partes muito genéricas
        filtered = [p for p in parts if p and len(p) > 2 and
                    p.lower() not in ('granada', 'alicante', 'nerja', 'spain', 'españa')]
        if filtered:
            return filtered[0][:80]
        return parts[0][:80] if parts else loc[:80]

    def _detect_kitchen(self, text: str) -> str:
        for kw in COOKTOP_ONLY:
            if kw in text:
                return "cooktop_only"
        for kw in GAS_KEYWORDS:
            if kw in text:
                return "gas_or_full"
        return "unknown"

    def _is_inactive(self, listing: Dict) -> bool:
        text = (listing.get("raw_details") or "").lower()
        title = (listing.get("title") or "").lower()
        full = f"{text} {title}"
        return any(kw in full for kw in INACTIVE_KEYWORDS)

    def _is_seasonal(self, text: str) -> bool:
        seasonal_kws = ['temporada', 'vacacional', 'turístico', 'días', 'semanas',
                        'noches', 'airbnb', 'booking', 'verano', 'vacaciones']
        return any(kw in text for kw in seasonal_kws)
