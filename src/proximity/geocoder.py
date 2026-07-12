"""
Geocoder — usa Nominatim (OpenStreetMap) para transformar
endereços em coordenadas. Gratuito, sem chave.
"""

import time
from typing import Optional, Tuple, Dict
import requests


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class Geocoder:
    def __init__(self, user_agent="SET_UP-Mauricio1806/1.0"):
        self.user_agent = user_agent
        self._cache: Dict[str, Tuple[float, float]] = {}

    def geocode(self, address: str, city: str, country: str = "España") -> Optional[Tuple[float, float]]:
        """Geocodifica endereço em (lat, lon)."""
        key = f"{address}|{city}"
        if key in self._cache:
            return self._cache[key]

        # Rate limit Nominatim: 1 request/sec
        time.sleep(1.1)

        query = f"{address}, {city}, {country}"
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "es"},
                headers={"User-Agent": self.user_agent},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    lat = float(data[0]["lat"])
                    lon = float(data[0]["lon"])
                    self._cache[key] = (lat, lon)
                    return (lat, lon)
        except Exception as e:
            print(f"    [geocode erro] {e.__class__.__name__} em {query[:60]}")
        return None
