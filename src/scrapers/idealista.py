"""
Idealista scraper v3 — usa a API OFICIAL do Idealista.

SETUP (5 min, gratuito):
1. Acesse https://developers.idealista.com/
2. Clique "Request an API key"
3. Preencha nome, email, finalidade: "Personal research rental market"
4. Em ~24h recebe IDEALISTA_API_KEY e IDEALISTA_API_SECRET por email
5. Adicione no .env:
   IDEALISTA_API_KEY=xxxxxxxxxxxxx
   IDEALISTA_API_SECRET=xxxxxxxxxxxx

Limites do plano gratuito: 100 requests/dia — suficiente pra 2x/dia em 3 cidades.
Docs: https://developers.idealista.com/

Enquanto não tem a key, o scraper reporta a situação claramente.
"""

import os
import base64
import re
from typing import List, Dict, Optional
import requests
from .base import BaseScraper

INACTIVE_KEYWORDS = [
    'ya no disponible', 'arrendado', 'alquilado', 'reservado', 'no disponible',
]


class IdealistaScraper(BaseScraper):

    OAUTH_URL = "https://api.idealista.com/oauth/token"
    SEARCH_URL = "https://api.idealista.com/3.5/es/search"

    # Coordenadas centrais + raio por cidade
    CITY_SEARCH = {
        "granada": {
            "center": "37.1773,-3.5986",
            "distance": 3000,   # metros do centro
            "label": "Granada capital",
        },
        "alicante": {
            "center": "38.3452,-0.4810",
            "distance": 3000,
            "label": "Alicante capital",
        },
        "nerja": {
            "center": "36.7503,-3.8747",
            "distance": 2000,
            "label": "Nerja",
        },
    }

    def __init__(self, **kwargs):
        super().__init__(delay_range=(2.0, 4.0), **kwargs)
        self.api_key    = os.getenv("IDEALISTA_API_KEY", "")
        self.api_secret = os.getenv("IDEALISTA_API_SECRET", "")
        self._token: Optional[str] = None

    # ----------------------------------------------------------
    # AUTH
    # ----------------------------------------------------------

    def _get_token(self) -> Optional[str]:
        if self._token:
            return self._token
        if not self.api_key or not self.api_secret:
            return None
        credentials = base64.b64encode(
            f"{self.api_key}:{self.api_secret}".encode()
        ).decode()
        try:
            resp = requests.post(
                self.OAUTH_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials", "scope": "read"},
                timeout=15,
            )
            if resp.status_code == 200:
                self._token = resp.json().get("access_token")
                return self._token
            else:
                print(f"    [Idealista auth] status {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"    [Idealista auth erro] {e}")
        return None

    # ----------------------------------------------------------
    # SCRAPE
    # ----------------------------------------------------------

    def scrape_city(self, city_key: str, max_price: int = 1000, max_pages: int = 3) -> List[Dict]:
        if not self.api_key:
            print(f"  → Idealista [{city_key}]: SEM API KEY")
            print(f"     Cadastre em https://developers.idealista.com/ (gratuito, 5min)")
            print(f"     Depois adicione ao .env: IDEALISTA_API_KEY=... IDEALISTA_API_SECRET=...")
            return []

        token = self._get_token()
        if not token:
            print(f"  → Idealista [{city_key}]: token inválido — verifique IDEALISTA_API_KEY")
            return []

        city_config = self.CITY_SEARCH.get(city_key)
        if not city_config:
            return []

        listings = []
        seen_urls: set = set()
        print(f"  → Idealista API [{city_key}] ✓ autenticado...")

        for page in range(1, max_pages + 1):
            params = {
                "center":         city_config["center"],
                "distance":       city_config["distance"],
                "propertyType":   "homes",
                "operation":      "rent",
                "maxPrice":       max_price,
                "minRooms":       1,
                "numPage":        page,
                "maxItems":       50,
                "order":          "price",
                "sort":           "asc",
                "furnished":      "furnished",     # amueblado
                "country":        "es",
                "language":       "es",
            }
            try:
                self.sleep()
                resp = requests.get(
                    self.SEARCH_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    timeout=20,
                )

                if resp.status_code == 401:
                    print(f"    [Idealista] token expirou — refresh")
                    self._token = None
                    token = self._get_token()
                    continue

                if resp.status_code == 429:
                    print(f"    [Idealista] rate limit atingido (100/dia no free tier)")
                    break

                if resp.status_code != 200:
                    print(f"    [Idealista] status {resp.status_code}")
                    break

                data = resp.json()
                items = data.get("elementList", [])
                total = data.get("total", 0)

                if page == 1:
                    print(f"    Total disponível na API: {total} imóveis")

                new_in_page = 0
                for item in items:
                    listing = self._parse_item(item, city_key)
                    if not listing:
                        continue
                    if listing["url"] in seen_urls:
                        continue
                    seen_urls.add(listing["url"])
                    listings.append(listing)
                    new_in_page += 1

                print(f"    página {page}: {new_in_page} novos ({len(listings)} total)")

                if len(items) < 50 or not items:
                    break  # última página

            except Exception as e:
                print(f"    [Idealista erro] {e}")
                break

        print(f"    ✓ {len(listings)} anúncios Idealista ≤ €{max_price}")
        return listings

    # ----------------------------------------------------------
    # PARSER
    # ----------------------------------------------------------

    def _parse_item(self, item: Dict, city_key: str) -> Optional[Dict]:
        prop_code = item.get("propertyCode", "")
        url = item.get("url", f"https://www.idealista.com/inmueble/{prop_code}/")
        if not url.startswith("http"):
            url = "https://www.idealista.com" + url

        price = item.get("price")
        if not price:
            return None

        # Localização detalhada
        neighborhood = item.get("neighborhood", "")
        district     = item.get("district", "")
        address      = item.get("address", "")
        location     = neighborhood or district or address or ""

        # Detalhes do imóvel
        rooms = item.get("rooms")
        size  = item.get("size")       # m²
        floor = item.get("floor")
        exterior = item.get("exterior")  # exterior/interior

        # Descrição
        description = item.get("description", "").lower()

        # Detecta fogão vs cooktop
        kitchen_type = self._detect_kitchen(description, item)

        # Imagens (usa thumbnail se houver)
        thumbnail = item.get("thumbnail", "")
        images    = [img.get("url", "") for img in item.get("multimedia", {}).get("images", [])[:3]]

        # Comodidades extras da API
        has_parking  = item.get("parkingSpace", {}).get("hasParkingSpace", False)
        has_elevator = item.get("hasLift", False)
        has_ac       = item.get("hasAirConditioning", False)
        has_terrace  = item.get("hasTerrace", False)

        # Título humanizado
        type_map = {
            "flat": "Piso", "penthouse": "Ático", "studio": "Estudio",
            "duplex": "Dúplex", "chalet": "Chalet", "house": "Casa",
        }
        ptype = type_map.get(item.get("propertyType", "flat"), "Piso")
        title = f"{ptype} en {location}, {TARGET_CITY_NAMES.get(city_key, city_key.capitalize())}"

        extras = []
        if has_ac:      extras.append("A/C")
        if has_terrace: extras.append("Terraza")
        if has_elevator:extras.append("Ascensor")
        if has_parking: extras.append("Garaje")

        return {
            "source":        "idealista",
            "city":          city_key,
            "title":         title,
            "url":           url,
            "price":         int(price),
            "location":      location,
            "location_raw":  f"{address}, {district}".strip(", "),
            "neighborhood":  neighborhood,
            "district":      district,
            "rooms":         rooms,
            "m2":            size,
            "floor":         floor,
            "exterior":      exterior,
            "kitchen_type":  kitchen_type,
            "has_cooktop_only": kitchen_type == "cooktop_only",
            "is_seasonal":   False,  # API já filtra por aluguel de longa duração
            "extras":        extras,
            "thumbnail":     thumbnail,
            "images":        images,
            "raw_details":   description[:300],
        }

    def _detect_kitchen(self, description: str, item: Dict) -> str:
        gas_kws = ['fogón', 'fogones', 'placa de gas', 'vitrocerámica', 'vitrocermica',
                   'cocina completa', 'cocina equipada', 'cocina americana con']
        cooktop_kws = ['microondas', 'sin cocina', 'kitchenette', 'cocina americana sin']
        for kw in cooktop_kws:
            if kw in description:
                return "cooktop_only"
        for kw in gas_kws:
            if kw in description:
                return "gas_or_full"
        # A API Idealista tem campo hasKitchen
        if item.get("hasKitchen") is False:
            return "cooktop_only"
        return "unknown"


TARGET_CITY_NAMES = {
    "granada": "Granada",
    "alicante": "Alicante",
    "nerja": "Nerja",
}
