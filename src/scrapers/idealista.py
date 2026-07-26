"""
Idealista scraper v4 — ZenRows com JS render ativo.

SETUP (2 min, free tier 1000 créditos):
1. Já tem conta em zenrows.com (você criou antes)
2. Dashboard → API Key → copiar
3. Adicione no .env:
   ZENROWS_KEY=sua_api_key_aqui

ZenRows com js_render=true contorna Cloudflare do Idealista.
Custo: ~5 créditos por request com JS render (free tier = 200 requests com JS).
Suficiente para testar as 3 cidades e ajustar antes de ativar no Actions diário.

Fallback automático para API oficial quando IDEALISTA_API_KEY também estiver configurada.
"""

import os
import re
import json
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .base import BaseScraper

INACTIVE_KEYWORDS = [
    'ya no disponible', 'arrendado', 'alquilado', 'reservado', 'no disponible',
]

TARGET_CITY_NAMES = {
    "granada": "Granada",
    "alicante": "Alicante",
    "nerja": "Nerja",
}


class IdealistaScraper(BaseScraper):

    # URLs do Idealista por cidade — com filtro de preço embutido na URL
    CITY_URLS = {
        "granada":  "https://www.idealista.com/alquiler-viviendas/granada-granada/con-precio-hasta_{max_price},de-un-dormitorio/",
        "alicante": "https://www.idealista.com/alquiler-viviendas/alicante-alacant/con-precio-hasta_{max_price}/",
        "nerja":    "https://www.idealista.com/alquiler-viviendas/nerja-malaga/con-precio-hasta_{max_price}/",
    }

    def __init__(self, **kwargs):
        super().__init__(delay_range=(2.0, 4.0), **kwargs)
        self.zenrows_key    = os.getenv("ZENROWS_KEY", "")
        self.api_key        = os.getenv("IDEALISTA_API_KEY", "")
        self.api_secret     = os.getenv("IDEALISTA_API_SECRET", "")
        self._token: Optional[str] = None

    # ----------------------------------------------------------
    # ENTRY POINT
    # ----------------------------------------------------------

    def scrape_city(self, city_key: str, max_price: int = 9999, max_pages: int = 3) -> List[Dict]:
        # Prioridade: API oficial > ZenRows > nada
        if self.api_key and self.api_secret:
            return self._scrape_via_api(city_key, max_price, max_pages)
        elif self.zenrows_key:
            return self._scrape_via_zenrows(city_key, max_price, max_pages)
        else:
            print(f"  → Idealista [{city_key}]: sem credenciais")
            print(f"     Opção A (recomendada): IDEALISTA_API_KEY + IDEALISTA_API_SECRET")
            print(f"       → developers.idealista.com (gratuito, ~24h para aprovar)")
            print(f"     Opção B (imediata): ZENROWS_KEY")
            print(f"       → zenrows.com (free tier ativo, 2 min para configurar)")
            return []

    # ----------------------------------------------------------
    # ZENROWS COM JS RENDER
    # ----------------------------------------------------------

    def _scrape_via_zenrows(self, city_key: str, max_price: int, max_pages: int) -> List[Dict]:
        url_template = self.CITY_URLS.get(city_key)
        if not url_template:
            return []

        listings = []
        seen_urls: set = set()
        print(f"  → Idealista [{city_key}] via ZenRows JS render...")

        for page in range(1, max_pages + 1):
            target_url = url_template.format(max_price=max_price)
            if page > 1:
                target_url = target_url.rstrip("/") + f"/pagina-{page}.htm"

            # ZenRows com JS render — passa a URL do Idealista como parâmetro
            zenrows_url = (
                f"https://api.zenrows.com/v1/"
                f"?apikey={self.zenrows_key}"
                f"&url={target_url}"
                f"&js_render=true"          # essencial para passar Cloudflare
                f"&wait=3000"               # aguarda 3s para JS carregar
                f"&premium_proxy=true"      # proxy residencial (contorna geo-bloqueio)
            )

            self.sleep()
            html = self.fetch(zenrows_url)
            if not html:
                print(f"    [ZenRows] sem resposta na página {page}")
                break

            # Detecta bloqueio residual
            if "Just a moment" in html or "Access denied" in html or len(html) < 2000:
                print(f"    [ZenRows] ainda bloqueado — tente premium_proxy=true ou aumente wait")
                break

            new_items = self._parse_idealista_html(html, city_key, max_price, seen_urls)
            listings.extend(new_items)
            print(f"    página {page}: {len(new_items)} novos ({len(listings)} total)")

            if not new_items:
                break

        print(f"    ✓ {len(listings)} anúncios Idealista ZenRows")
        return listings

    def _parse_idealista_html(self, html: str, city_key: str, max_price: int, seen_urls: set) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")

        # Tenta extrair do JSON embutido pelo Idealista (mais confiável que seletores)
        items_from_json = self._extract_from_json(html, city_key)
        if items_from_json:
            result = []
            for item in items_from_json:
                if item.get("url") and item["url"] not in seen_urls:
                    if not item.get("price") or item["price"] <= max_price:
                        seen_urls.add(item["url"])
                        result.append(item)
            return result

        # Fallback: parse HTML com seletores conhecidos do Idealista
        articles = (
            soup.select("article.item") or
            soup.select("article[data-element-id]") or
            soup.select(".item-info-container") or
            soup.select("article")
        )

        result = []
        for article in articles:
            try:
                listing = self._parse_article(article, city_key)
                if not listing or not listing.get("price"):
                    continue
                if listing["price"] > max_price:
                    continue
                if self._is_inactive(listing):
                    continue
                if listing["url"] in seen_urls:
                    continue
                seen_urls.add(listing["url"])
                result.append(listing)
            except Exception:
                continue
        return result

    def _extract_from_json(self, html: str, city_key: str) -> List[Dict]:
        """O Idealista embute dados em window.__INITIAL_PROPS__ ou similar."""
        patterns = [
            r'window\.__INITIAL_PROPS__\s*=\s*({.*?})(?:;|\s*</script>)',
            r'window\.LISTING_DATA\s*=\s*(\[.*?\])(?:;|\s*</script>)',
            r'"adList"\s*:\s*(\[.*?\])',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                continue
            try:
                raw = match.group(1)
                data = json.loads(raw)

                # Navega pela estrutura para encontrar a lista
                if isinstance(data, list):
                    ad_list = data
                elif isinstance(data, dict):
                    ad_list = (
                        data.get("adList") or
                        data.get("items") or
                        data.get("ads") or
                        []
                    )
                else:
                    continue

                listings = []
                for ad in ad_list:
                    parsed = self._parse_json_ad(ad, city_key)
                    if parsed:
                        listings.append(parsed)
                if listings:
                    return listings
            except (json.JSONDecodeError, Exception):
                continue
        return []

    def _parse_json_ad(self, ad: Dict, city_key: str) -> Optional[Dict]:
        price = ad.get("price") or ad.get("priceInfo", {}).get("amount")
        if not price:
            return None

        ad_id = ad.get("adId") or ad.get("propertyCode") or ""
        url = ad.get("url") or ad.get("detailUrl") or f"https://www.idealista.com/inmueble/{ad_id}/"
        if not url.startswith("http"):
            url = "https://www.idealista.com" + url

        desc = (ad.get("description") or "").lower()
        location = (
            ad.get("neighborhood") or
            ad.get("district") or
            ad.get("address") or ""
        )

        type_map = {"flat": "Piso", "penthouse": "Ático", "studio": "Estudio",
                    "duplex": "Dúplex", "house": "Casa"}
        ptype = type_map.get(ad.get("propertyType", "flat"), "Piso")
        title = f"{ptype} en {location}, {TARGET_CITY_NAMES.get(city_key, '')}"

        return {
            "source": "idealista",
            "city": city_key,
            "title": title.strip(", ")[:120],
            "url": url,
            "price": int(price),
            "location": location[:80],
            "location_raw": location[:100],
            "rooms": ad.get("rooms"),
            "m2": ad.get("size"),
            "kitchen_type": self._detect_kitchen(desc),
            "has_cooktop_only": self._detect_kitchen(desc) == "cooktop_only",
            "is_seasonal": False,
            "raw_details": desc[:300],
        }

    def _parse_article(self, article, city_key: str) -> Optional[Dict]:
        title_el = (
            article.select_one("a.item-link") or
            article.select_one(".item-title a") or
            article.select_one("a[href*='/inmueble/']") or
            article.select_one("a[title]")
        )
        price_el = (
            article.select_one(".item-price") or
            article.select_one(".price-row") or
            article.select_one("[class*=price]")
        )
        if not title_el:
            return None

        href = title_el.get("href", "")
        url = href if href.startswith("http") else "https://www.idealista.com" + href
        if not url or url == "https://www.idealista.com":
            return None

        desc = article.get_text(" ", strip=True).lower()
        loc_el = article.select_one("[class*=location]") or article.select_one("[class*=Location]")
        location = loc_el.get_text(strip=True) if loc_el else self._extract_loc_from_title(
            title_el.get("title") or title_el.get_text()
        )

        return {
            "source": "idealista",
            "city": city_key,
            "title": (title_el.get("title") or title_el.get_text(strip=True))[:120],
            "url": url,
            "price": self.parse_price(price_el.get_text()) if price_el else None,
            "location": location[:80],
            "location_raw": location[:100],
            "rooms": self.parse_rooms(desc),
            "m2": self.parse_m2(desc),
            "kitchen_type": self._detect_kitchen(desc),
            "has_cooktop_only": self._detect_kitchen(desc) == "cooktop_only",
            "is_seasonal": False,
            "raw_details": desc[:300],
        }

    def _extract_loc_from_title(self, title: str) -> str:
        if not title:
            return ""
        m = re.search(r'en alquiler en (.+?)(?:,\s*\w+)?$', title, re.IGNORECASE)
        return m.group(1).strip()[:80] if m else title[:80]

    # ----------------------------------------------------------
    # API OFICIAL (mantida como prioridade se tiver as keys)
    # ----------------------------------------------------------

    def _scrape_via_api(self, city_key: str, max_price: int, max_pages: int) -> List[Dict]:
        """Usa a API OAuth do Idealista quando as keys estão configuradas."""
        import base64, requests as req

        OAUTH_URL  = "https://api.idealista.com/oauth/token"
        SEARCH_URL = "https://api.idealista.com/3.5/es/search"
        CITY_CENTERS = {
            "granada":  {"center": "37.1773,-3.5986", "distance": 3000},
            "alicante": {"center": "38.3452,-0.4810", "distance": 3000},
            "nerja":    {"center": "36.7503,-3.8747", "distance": 2000},
        }

        if not self._token:
            creds = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
            try:
                r = req.post(OAUTH_URL, headers={"Authorization": f"Basic {creds}",
                    "Content-Type": "application/x-www-form-urlencoded"},
                    data={"grant_type": "client_credentials", "scope": "read"}, timeout=15)
                if r.status_code == 200:
                    self._token = r.json().get("access_token")
                    print(f"  → Idealista API [{city_key}] ✓ autenticado")
                else:
                    print(f"  → Idealista API: auth falhou {r.status_code}")
                    return []
            except Exception as e:
                print(f"  → Idealista API: {e}"); return []

        city_cfg = CITY_CENTERS.get(city_key, {})
        listings, seen_urls = [], set()

        for page in range(1, max_pages + 1):
            params = {
                "center": city_cfg["center"], "distance": city_cfg["distance"],
                "propertyType": "homes", "operation": "rent",
                "maxPrice": max_price, "minRooms": 1,
                "numPage": page, "maxItems": 50,
                "order": "price", "sort": "asc",
                "furnished": "furnished", "country": "es", "language": "es",
            }
            try:
                self.sleep()
                r = req.get(SEARCH_URL,
                    headers={"Authorization": f"Bearer {self._token}"},
                    params=params, timeout=20)
                if r.status_code == 429:
                    print(f"    [API] rate limit"); break
                if r.status_code != 200:
                    print(f"    [API] status {r.status_code}"); break
                items = r.json().get("elementList", [])
                new = 0
                for item in items:
                    parsed = self._parse_api_item(item, city_key)
                    if parsed and parsed["url"] not in seen_urls:
                        seen_urls.add(parsed["url"])
                        listings.append(parsed)
                        new += 1
                print(f"    página {page}: {new} novos")
                if len(items) < 50: break
            except Exception as e:
                print(f"    [API erro] {e}"); break

        print(f"    ✓ {len(listings)} anúncios Idealista API")
        return listings

    def _parse_api_item(self, item: Dict, city_key: str) -> Optional[Dict]:
        price = item.get("price")
        if not price:
            return None
        prop_code = item.get("propertyCode", "")
        url = item.get("url") or f"https://www.idealista.com/inmueble/{prop_code}/"
        if not url.startswith("http"):
            url = "https://www.idealista.com" + url
        location = item.get("neighborhood") or item.get("district") or item.get("address") or ""
        desc = item.get("description", "").lower()
        type_map = {"flat": "Piso", "penthouse": "Ático", "studio": "Estudio",
                    "duplex": "Dúplex", "house": "Casa"}
        ptype = type_map.get(item.get("propertyType", "flat"), "Piso")
        return {
            "source": "idealista",
            "city": city_key,
            "title": f"{ptype} en {location}, {TARGET_CITY_NAMES.get(city_key, '')}".strip(", ")[:120],
            "url": url,
            "price": int(price),
            "location": location[:80],
            "location_raw": location[:100],
            "rooms": item.get("rooms"),
            "m2": item.get("size"),
            "kitchen_type": self._detect_kitchen(desc),
            "has_cooktop_only": self._detect_kitchen(desc) == "cooktop_only",
            "is_seasonal": False,
            "raw_details": desc[:300],
        }

    # ----------------------------------------------------------
    # UTILS
    # ----------------------------------------------------------

    def _detect_kitchen(self, text: str) -> str:
        for kw in ['microondas', 'sin cocina', 'kitchenette', 'cocina americana sin']:
            if kw in text: return "cooktop_only"
        for kw in ['fogón', 'placa de gas', 'vitrocerámica', 'cocina completa', 'cocina equipada']:
            if kw in text: return "gas_or_full"
        return "unknown"

    def _is_inactive(self, listing: Dict) -> bool:
        text = f"{listing.get('raw_details','')} {listing.get('title','')}".lower()
        return any(kw in text for kw in INACTIVE_KEYWORDS)
