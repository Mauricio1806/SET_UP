"""
Habitaclia scraper v3 — seletores amplos + debug mode + filtros.
"""

import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .base import BaseScraper

INACTIVE_KEYWORDS = ['ya no disponible', 'arrendado', 'alquilado', 'reservado', 'no disponible']

# Reutiliza os mesmos filtros geográficos do pisos.py
CITY_GEO_TERMS = {
    "granada":  ["granada", "zaidín", "albaicín", "realejo", "beiro", "chana",
                 "cartuja", "camino de ronda", "ronda", "genil", "figares",
                 "arabial", "pajaritos", "sacromonte", "armilla"],
    "alicante": ["alicante", "alacant", "benalúa", "carolinas", "ciudad jardín",
                 "playa san juan", "vistahermosa", "florida", "babel",
                 "san blas", "centro", "ensanche"],
    "nerja":    ["nerja", "capistrano", "parador", "balcón de europa",
                 "burriana", "torrecilla", "maro"],
}
FOREIGN_CITY_TERMS = [
    "barcelona", "madrid", "sevilla", "valència", "bilbao", "zaragoza",
    "sant sadurní", "sabadell", "terrassa", "hospitalet", "badalona",
    "cornellà", "lloguer sant", "2026-llog",
]

CARD_SELECTORS = [
    "article.list-item-container",
    "article.property-item",
    "[class*=list-item-container]",
    "[class*=PropertyCard]",
    "[class*=property-card]",
    "[class*=property-item]",
    "[class*=list-item]",
    "article[data-id]",
    "li[data-id]",
    "article",
]

CITY_PATHS = {
    "granada":  ["/alquiler-granada_capital.htm", "/alquiler-granada.htm"],
    "alicante": ["/alquiler-alacant_alicante-cap.htm", "/alquiler-alicante.htm", "/alquiler-alacant.htm"],
    "nerja":    ["/alquiler-nerja.htm"],
}


class HabitacliaScraper(BaseScraper):
    BASE_URL = "https://www.habitaclia.com"

    def scrape_city(self, city_key: str, max_price: int = 9999, max_pages: int = 3) -> List[Dict]:
        listings = []
        seen_urls: set = set()
        paths = CITY_PATHS.get(city_key, [])
        print(f"  → Habitaclia {city_key}...")

        working_path, working_sel = None, None

        for candidate in paths:
            url = f"{self.BASE_URL}{candidate}"
            html = self.fetch(url)
            if not html or len(html) < 3000:
                print(f"    ✗ vazio: {candidate}")
                continue
            if "404" in html[:200]:
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
                for sel in CARD_SELECTORS[:5]:
                    n = len(soup.select(sel))
                    if n: print(f"      {sel}: {n} (sem preço)")
                continue

            working_path = candidate
            working_sel = sel_found
            print(f"    ✓ {candidate} | {sel_found!r} | {len(cards)} cards")

            for card in cards:
                try:
                    listing = self._parse(card, city_key)
                    if listing and listing.get("price") and listing["price"] >= 200 and listing["price"] <= max_price:
                        if not self._is_inactive(listing) and self._is_correct_city(listing, city_key):
                            if listing["url"] not in seen_urls:
                                seen_urls.add(listing["url"])
                                listings.append(listing)
                except Exception:
                    continue
            break

        if not working_path:
            print(f"    [warn] Habitaclia {city_key}: nenhum path funcionou")
            return listings

        for page in range(2, max_pages + 1):
            next_url = f"{self.BASE_URL}{working_path}".replace(".htm", f"-{page}.htm")
            html = self.fetch(next_url)
            if not html: continue
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(working_sel or "article")
            new = 0
            for card in cards:
                try:
                    listing = self._parse(card, city_key)
                    if listing and listing.get("price") and listing["price"] >= 200 and listing["price"] <= max_price:
                        if not self._is_inactive(listing) and self._is_correct_city(listing, city_key):
                            if listing["url"] not in seen_urls:
                                seen_urls.add(listing["url"])
                                listings.append(listing)
                                new += 1
                except Exception:
                    continue
            print(f"    página {page}: {new} novos")
            if not cards: break

        print(f"    ✓ {len(listings)} anúncios Habitaclia")
        return listings

    def _parse(self, article, city_key: str) -> Optional[Dict]:
        title_el = (
            article.select_one(".list-item-title a") or
            article.select_one("h3 a") or article.select_one("h2 a") or
            article.select_one("[class*=title] a") or article.select_one("a[href]")
        )
        price_el = (
            article.select_one(".prices-price") or
            article.select_one("[class*=price]") or article.select_one("[class*=Price]")
        )
        loc_el = (
            article.select_one(".list-item-location") or
            article.select_one("[class*=location]") or article.select_one("[class*=address]")
        )
        det_el = (
            article.select_one(".list-item-details") or
            article.select_one("[class*=detail]") or article.select_one("[class*=features]")
        )

        if not title_el:
            return None

        href = title_el.get("href", "")
        url = href if href.startswith("http") else self.BASE_URL + href

        price = self.parse_price(price_el.get_text()) if price_el else None
        if not price:
            m = re.search(r'(\d{3,4})\s*[€]', article.get_text())
            price = int(m.group(1)) if m else None

        details_text = det_el.get_text(" ", strip=True) if det_el else ""
        desc = article.get_text(" ", strip=True).lower()
        loc_raw = loc_el.get_text(strip=True) if loc_el else ""

        return {
            "source": "habitaclia",
            "city": city_key,
            "title": title_el.get_text(strip=True)[:120],
            "url": url,
            "price": price,
            "location": self._clean_loc(loc_raw),
            "location_raw": loc_raw[:100],
            "rooms": self.parse_rooms(details_text),
            "m2": self.parse_m2(details_text),
            "raw_details": desc[:300],
            "kitchen_type": self._kitchen(desc),
            "has_cooktop_only": self._kitchen(desc) == "cooktop_only",
            "is_seasonal": any(k in desc for k in ['temporada', 'vacacional']),
        }

    def _is_correct_city(self, listing: Dict, city_key: str) -> bool:
        texts = [listing.get("title",""), listing.get("location",""),
                 listing.get("location_raw",""), listing.get("raw_details","")]
        full = " ".join(t for t in texts if t).lower()
        for term in FOREIGN_CITY_TERMS:
            if term in full:
                return False
        for term in CITY_GEO_TERMS.get(city_key, []):
            if term in full:
                return True
        return False

    def _clean_loc(self, loc: str) -> str:
        if not loc: return ""
        parts = [p.strip() for p in re.split(r'[,·|]', loc)]
        filtered = [p for p in parts if p and len(p) > 2
                    and p.lower() not in ('granada', 'alicante', 'nerja')]
        return (filtered[0] if filtered else parts[0] if parts else loc)[:80]

    def _kitchen(self, text: str) -> str:
        for kw in ['microondas', 'cocina americana', 'sin cocina']:
            if kw in text: return "cooktop_only"
        for kw in ['fogón', 'placa de gas', 'vitrocerámica', 'cocina completa']:
            if kw in text: return "gas_or_full"
        return "unknown"

    def _is_inactive(self, listing: Dict) -> bool:
        text = f"{listing.get('raw_details','')} {listing.get('title','')}".lower()
        return any(kw in text for kw in INACTIVE_KEYWORDS)
