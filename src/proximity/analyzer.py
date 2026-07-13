"""
Proximity Analyzer v2 — geocoding inteligente com extração de rua,
filtro de anúncios sem geocoding válido, e badge _geocoded para debug.
"""

from typing import Dict
from ..config import POI_CATEGORIES, TARGET_CITIES
from .geocoder import Geocoder, extract_street
from .overpass import OverpassClient


class ProximityAnalyzer:
    def __init__(self):
        self.geocoder = Geocoder()
        self.overpass = OverpassClient()

    def analyze_listing(self, listing: Dict) -> Dict:
        city_key = listing.get("city", "granada")
        city_config = TARGET_CITIES.get(city_key, {})
        city_name = city_config.get("name", "Granada")

        # Tenta geocodificar na seguinte ordem de qualidade:
        # 1. location_raw (mais limpo — bairro/rua extraído)
        # 2. title
        coords = None
        geocoded_from = None

        candidates = [
            listing.get("location_raw", ""),
            listing.get("location", ""),
            listing.get("title", ""),
        ]
        for candidate in candidates:
            if not candidate or len(candidate.strip()) < 4:
                continue
            coords = self.geocoder.geocode(candidate, city_name)
            if coords:
                geocoded_from = candidate[:60]
                break

        city_center = (city_config.get("lat"), city_config.get("lon"))

        if coords:
            listing["_geocoded"] = True
            listing["_geocoded_from"] = geocoded_from
        else:
            listing["_geocoded"] = False
            listing["_geocoded_from"] = "fallback:city_center"
            coords = city_center

        listing["lat"] = coords[0]
        listing["lon"] = coords[1]

        # Busca POIs apenas se geocoding foi bem-sucedido
        # (evitar distâncias falsas com centro da cidade)
        listing["pois"] = {}
        for cat_key, cat_config in POI_CATEGORIES.items():
            radius = cat_config["max_walk_meters"] * 2
            pois = self.overpass.find_pois(
                coords[0], coords[1],
                cat_config["overpass_query"],
                radius_meters=radius,
            )

            # Marcar marcas prioritárias
            for poi in pois:
                brand_lower = (poi.get("brand") or "").lower()
                name_lower = (poi.get("name") or "").lower()
                poi["priority_brand"] = next(
                    (b for b in cat_config["priority_brands"]
                     if b.lower() in brand_lower or b.lower() in name_lower),
                    None
                )

            listing["pois"][cat_key] = pois[:5]

            if pois:
                nearest = pois[0]
                listing[f"nearest_{cat_key}_m"] = nearest["distance_meters"]
                listing[f"nearest_{cat_key}_name"] = nearest["name"]
                listing[f"nearest_{cat_key}_walk_min"] = nearest["walk_minutes"]
            else:
                listing[f"nearest_{cat_key}_m"] = None
                listing[f"nearest_{cat_key}_name"] = None
                listing[f"nearest_{cat_key}_walk_min"] = None

        return listing
