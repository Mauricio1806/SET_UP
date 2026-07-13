"""
Overpass API — busca POIs (Points of Interest) próximos a um ponto.
API pública do OpenStreetMap. Grátis.
"""

import time
from typing import List, Dict
from math import radians, sin, cos, sqrt, atan2
import requests


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em metros entre 2 pontos (fórmula haversine)."""
    R = 6371000  # raio da Terra em metros
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1) * cos(phi2) * sin(dlambda/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))


class OverpassClient:
    def __init__(self, cache_size=500):
        self._cache: Dict[str, List[Dict]] = {}

    def find_pois(self, lat: float, lon: float, query_tag: str, radius_meters: int = 1000) -> List[Dict]:
        """
        Busca POIs num raio. query_tag exemplo: '["shop"="supermarket"]'
        """
        cache_key = f"{lat:.5f}|{lon:.5f}|{query_tag}|{radius_meters}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        query = f"""
        [out:json][timeout:10];
        (
          node{query_tag}(around:{radius_meters},{lat},{lon});
          way{query_tag}(around:{radius_meters},{lat},{lon});
        );
        out center;
        """

        try:
            time.sleep(1.5)  # Overpass rate limit
            headers = {"User-Agent": "SET_UP-RentalScraper/1.0 (script pessoal de busca de aluguel)"}
            resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=12)
            if resp.status_code != 200:
                print(f"    [overpass] status {resp.status_code}")
                return []
            data = resp.json()

            pois = []
            for element in data.get("elements", []):
                elem_lat = element.get("lat") or element.get("center", {}).get("lat")
                elem_lon = element.get("lon") or element.get("center", {}).get("lon")
                if not elem_lat or not elem_lon:
                    continue
                tags = element.get("tags", {})
                distance = haversine_meters(lat, lon, elem_lat, elem_lon)
                pois.append({
                    "name": tags.get("name", "Sem nome"),
                    "brand": tags.get("brand", ""),
                    "lat": elem_lat,
                    "lon": elem_lon,
                    "distance_meters": round(distance),
                    "walk_minutes": round(distance / 80, 1),  # velocidade a pé ~80m/min
                    "address": self._format_address(tags),
                })
            pois.sort(key=lambda p: p["distance_meters"])
            self._cache[cache_key] = pois
            return pois

        except Exception as e:
            print(f"    [overpass erro] {e.__class__.__name__}: {str(e)[:80]}")
            return []

    def _format_address(self, tags: Dict) -> str:
        street = tags.get("addr:street", "")
        housenumber = tags.get("addr:housenumber", "")
        if street and housenumber:
            return f"{street} {housenumber}"
        return street
