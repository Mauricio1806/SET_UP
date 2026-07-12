"""
Proximity Analyzer — para cada apartamento, calcula distância aos
POIs relevantes (supermercados, academias, farmácias, transporte).
"""

from typing import List, Dict
from ..config import POI_CATEGORIES, TARGET_CITIES
from .geocoder import Geocoder
from .overpass import OverpassClient


class ProximityAnalyzer:
    def __init__(self):
        self.geocoder = Geocoder()
        self.overpass = OverpassClient()

    def analyze_listing(self, listing: Dict) -> Dict:
        """
        Recebe um listing e adiciona:
        - coordenadas
        - POIs próximos por categoria
        - matched priority brands (Mercadona, Basic-Fit, etc)
        """
        city_key = listing.get("city")
        location_str = listing.get("location") or listing.get("title", "")
        city_config = TARGET_CITIES.get(city_key, {})

        coords = self.geocoder.geocode(location_str, city_config.get("name", ""))
        if not coords:
            # Fallback: usar coordenadas centrais da cidade
            coords = (city_config.get("lat"), city_config.get("lon"))
            listing["_geocoded"] = False
        else:
            listing["_geocoded"] = True

        listing["lat"] = coords[0]
        listing["lon"] = coords[1]

        listing["pois"] = {}
        for cat_key, cat_config in POI_CATEGORIES.items():
            pois = self.overpass.find_pois(
                coords[0], coords[1],
                cat_config["overpass_query"],
                radius_meters=cat_config["max_walk_meters"] * 2,
            )
            # Destacar marcas prioritárias
            for poi in pois:
                priority_match = None
                brand_lower = (poi["brand"] or "").lower()
                name_lower = (poi["name"] or "").lower()
                for brand in cat_config["priority_brands"]:
                    if brand.lower() in brand_lower or brand.lower() in name_lower:
                        priority_match = brand
                        break
                poi["priority_brand"] = priority_match

            listing["pois"][cat_key] = pois[:5]  # top 5 mais próximos

            # Métrica: distância ao mais próximo
            listing[f"nearest_{cat_key}_m"] = pois[0]["distance_meters"] if pois else None
            listing[f"nearest_{cat_key}_name"] = pois[0]["name"] if pois else None

        return listing
