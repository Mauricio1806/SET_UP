"""
Idealista scraper v2 — 3 estratégias para driblar Cloudflare:
  1. ScraperAPI free tier (1000 req/mês grátis, sem cartão)
  2. Zenrows free tier (1000 req/mês grátis)  
  3. HTML direto com headers avançados (último recurso)

Setup gratuito:
  - Cadastre em https://www.scraperapi.com (free, sem cartão)
  - Pegue sua API key e adicione no .env:  SCRAPERAPI_KEY=xxx
  OU
  - Cadastre em https://app.zenrows.com (free)
  - Adicione: ZENROWS_KEY=xxx
  
  Se nenhuma key, tenta direto (vai bloquear na maioria das vezes).
"""

import os
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .base import BaseScraper

# Indicadores de anúncio inativo
INACTIVE_KEYWORDS = [
    'ya no disponible', 'arrendado', 'alquilado', 'reservado',
    'no disponible', 'anuncio eliminado', 'this property',
]


class IdealistaScraper(BaseScraper):
    BASE_URL = "https://www.idealista.com"

    CITY_PATHS = {
        "granada":  "/alquiler-viviendas/granada-granada/con-precio-hasta_{max_price},de-un-dormitorio/",
        "alicante": "/alquiler-viviendas/alicante-alacant/con-precio-hasta_{max_price},de-un-dormitorio/",
        "nerja":    "/alquiler-viviendas/nerja-malaga/con-precio-hasta_{max_price},de-un-dormitorio/",
    }

    def __init__(self, **kwargs):
        super().__init__(delay_range=(4.0, 8.0), **kwargs)
        self.scraperapi_key = os.getenv("SCRAPERAPI_KEY", "")
        self.zenrows_key = os.getenv("ZENROWS_KEY", "")

    def _build_url_with_proxy(self, target_url: str) -> str:
        """Envolve URL com proxy anti-bot se disponível."""
        if self.scraperapi_key:
            return (
                f"http://api.scraperapi.com"
                f"?api_key={self.scraperapi_key}"
                f"&url={target_url}"
                f"&render=false"
                f"&country_code=es"
            )
        if self.zenrows_key:
            return (
                f"https://api.zenrows.com/v1/"
                f"?apikey={self.zenrows_key}"
                f"&url={target_url}"
                f"&js_render=false"
            )
        return target_url  # sem proxy

    def scrape_city(self, city_key: str, max_price: int = 1000, max_pages: int = 3) -> List[Dict]:
        listings = []
        seen_urls: set = set()
        path_template = self.CITY_PATHS.get(city_key)
        if not path_template:
            return listings

        path = path_template.format(max_price=max_price)
        proxy_type = "ScraperAPI" if self.scraperapi_key else ("Zenrows" if self.zenrows_key else "direto")
        print(f"  → Idealista {city_key} [{proxy_type}]...")

        for page in range(1, max_pages + 1):
            target_url = self.BASE_URL + path
            if page > 1:
                target_url = target_url.rstrip("/") + f"/pagina-{page}.htm"

            fetch_url = self._build_url_with_proxy(target_url)
            html = self.fetch(fetch_url)
            if not html:
                continue

            # Detecta bloqueios
            if any(s in html for s in ["Just a moment", "cf-mitigated", "Access denied",
                                        "Ray ID", "Checking your browser"]):
                print(f"    [bloqueado] Cloudflare detectado — adicione SCRAPERAPI_KEY ao .env")
                break

            if "captcha" in html.lower():
                print(f"    [bloqueado] CAPTCHA detectado")
                break

            soup = BeautifulSoup(html, "html.parser")
            articles = (
                soup.select("article.item") or
                soup.select("article[data-element-id]") or
                soup.select("div.item-info-container") or
                soup.select(".items-list article")
            )

            if not articles:
                # Tenta outro seletor (Idealista muda HTML às vezes)
                articles = soup.select("[class*='item-info']")

            new_in_page = 0
            for article in articles:
                try:
                    listing = self._parse_listing(article, city_key)
                    if not listing:
                        continue
                    if listing.get("price") and listing["price"] > max_price:
                        continue
                    if self._is_inactive(listing):
                        continue
                    if listing["url"] in seen_urls:
                        continue
                    seen_urls.add(listing["url"])
                    listings.append(listing)
                    new_in_page += 1
                except Exception:
                    continue

            print(f"    página {page}: {new_in_page} novos anúncios")
            if new_in_page == 0:
                break

        print(f"    ✓ {len(listings)} anúncios Idealista ≤ €{max_price}")
        return listings

    def _parse_listing(self, article, city_key: str) -> Optional[Dict]:
        # Vários seletores possíveis que o Idealista usa
        title_el = (
            article.select_one("a.item-link") or
            article.select_one(".item-title a") or
            article.select_one("a[title]")
        )
        price_el = (
            article.select_one(".item-price") or
            article.select_one(".price-row") or
            article.select_one("[class*=price]")
        )
        details_el = (
            article.select_one(".item-detail-char") or
            article.select_one(".item-details") or
            article.select_one("[class*=detail]")
        )
        desc_el = (
            article.select_one(".item-description p") or
            article.select_one(".item-description")
        )
        location_el = (
            article.select_one(".item-detail-location") or
            article.select_one("[class*=location]")
        )

        if not title_el:
            return None

        href = title_el.get("href", "")
        url = href if href.startswith("http") else self.BASE_URL + href
        if not url or url == self.BASE_URL:
            return None

        details_text = details_el.get_text(" ", strip=True) if details_el else ""
        desc_text = desc_el.get_text(" ", strip=True) if desc_el else ""
        full_text = f"{details_text} {desc_text}".lower()

        location_raw = location_el.get_text(strip=True) if location_el else ""
        # Para Idealista o title do link geralmente tem a localização
        title_attr = title_el.get("title") or title_el.get_text(strip=True)

        # Extrai rua/bairro do título
        location_clean = location_raw or self._extract_location_from_title(title_attr)

        price_text = price_el.get_text() if price_el else ""
        price = self.parse_price(price_text)

        # Detecta fogão vs cooktop
        kitchen_type = self._detect_kitchen(full_text)
        is_seasonal = self._is_seasonal(full_text)

        return {
            "source": "idealista",
            "city": city_key,
            "title": title_attr[:120],
            "url": url,
            "price": price,
            "location": location_clean[:80],
            "location_raw": location_raw[:100],
            "rooms": self.parse_rooms(details_text),
            "m2": self.parse_m2(details_text),
            "raw_details": full_text[:300],
            "kitchen_type": kitchen_type,
            "is_seasonal": is_seasonal,
            "has_cooktop_only": kitchen_type == "cooktop_only",
        }

    def _extract_location_from_title(self, title: str) -> str:
        """Extrai bairro/rua de 'Piso en alquiler en Calle Arabial, Granada'."""
        if not title:
            return ""
        # Padrão Idealista: 'Piso en alquiler en LOCALIZAÇÃO, CIDADE'
        match = re.search(r'en alquiler en (.+?)(?:,\s*\w+)?$', title, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:80]
        return title[:80]

    def _detect_kitchen(self, text: str) -> str:
        cooktop_kws = ['microondas', 'cocina americana', 'sin cocina', 'kitchenette']
        gas_kws = ['cocina con gas', 'fogón', 'fogones', 'placa de gas',
                   'vitrocerámica', 'cocina equipada', 'cocina completa']
        for kw in cooktop_kws:
            if kw in text:
                return "cooktop_only"
        for kw in gas_kws:
            if kw in text:
                return "gas_or_full"
        return "unknown"

    def _is_inactive(self, listing: Dict) -> bool:
        text = f"{listing.get('raw_details','')} {listing.get('title','')}".lower()
        return any(kw in text for kw in INACTIVE_KEYWORDS)

    def _is_seasonal(self, text: str) -> bool:
        kws = ['temporada', 'vacacional', 'turístico', 'vacaciones', 'verano']
        return any(kw in text for kw in kws)
