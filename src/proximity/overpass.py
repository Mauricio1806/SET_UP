"""
Overpass API — busca POIs (Points of Interest) próximos a um ponto.
Cache persistente em disco para economizar requests entre execuções.
"""

import json
import time
from pathlib import Path
from typing import List, Dict
from math import radians, sin, cos, sqrt, atan2
import requests

from ..config import DATA_DIR

# Múltiplos endpoints públicos — rotaciona quando um falha
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Cache persistente em disco — sobrevive entre execuções
CACHE_FILE = DATA_DIR / "overpass_cache.json"


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1) * cos(phi2) * sin(dlambda/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))


class OverpassClient:
    def __init__(self):
        self._cache: Dict[str, List[Dict]] = self._load_cache()
        self._endpoint_idx = 0     # rotação de endpoints
        self._consecutive_errors = 0

    def find_pois(self, lat: float, lon: float, query_tag: str, radius_meters: int = 1000) -> List[Dict]:
        # Chave de cache com coordenadas arredondadas (3 decimais ≈ 111m de precisão)
        cache_key = f"{lat:.3f}|{lon:.3f}|{query_tag}|{radius_meters}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Se muitos erros consecutivos, para de tentar
        if self._consecutive_errors >= 5:
            return []

        query = f"""
        [out:json][timeout:20];
        (
          node{query_tag}(around:{radius_meters},{lat},{lon});
          way{query_tag}(around:{radius_meters},{lat},{lon});
        );
        out center;
        """

        resp = None
        last_406 = False
        for attempt in range(len(OVERPASS_ENDPOINTS)):
            idx = (self._endpoint_idx + attempt) % len(OVERPASS_ENDPOINTS)
            endpoint = OVERPASS_ENDPOINTS[idx]
            try:
                time.sleep(1.5)
                r = requests.post(endpoint, data={"data": query}, timeout=15)
                if r.status_code == 200:
                    resp = r
                    self._endpoint_idx = idx
                    self._consecutive_errors = 0
                    last_406 = False
                    break
                elif r.status_code in (429, 503):
                    print(f"    [overpass] {endpoint.split('/')[2]} → {r.status_code} (rate limit), tentando próximo...")
                elif r.status_code == 406:
                    # 406 = endpoint sobrecarregado ou query syntax — tenta outro endpoint
                    print(f"    [overpass] {endpoint.split('/')[2]} → 406, tentando próximo...")
                    last_406 = True
                    # NÃO faz break — tenta os outros endpoints
                else:
                    print(f"    [overpass] {endpoint.split('/')[2]} → {r.status_code}")
            except requests.exceptions.Timeout:
                print(f"    [overpass] {endpoint.split('/')[2]} → timeout, tentando próximo...")
            except Exception as e:
                print(f"    [overpass] {endpoint.split('/')[2]} → {e.__class__.__name__}")

        if not resp:
            # Só conta como erro consecutivo se todos os endpoints falharam E não foi 406
            # 406 pode ser instabilidade temporária do servidor, não erro de código
            if not last_406:
                self._consecutive_errors += 1
            self._cache[cache_key] = []
            return []

        try:
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
                    "walk_minutes": round(distance / 80, 1),
                    "address": self._format_address(tags),
                })
            pois.sort(key=lambda p: p["distance_meters"])
            self._cache[cache_key] = pois
            self._save_cache()
            return pois
        except Exception as e:
            print(f"    [overpass parse] {e.__class__.__name__}: {str(e)[:60]}")
            return []

    def _format_address(self, tags: Dict) -> str:
        street = tags.get("addr:street", "")
        number = tags.get("addr:housenumber", "")
        return f"{street} {number}".strip() if street else ""

    def _load_cache(self) -> Dict:
        try:
            if CACHE_FILE.exists():
                return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_cache(self):
        try:
            CACHE_FILE.write_text(
                json.dumps(self._cache, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass
