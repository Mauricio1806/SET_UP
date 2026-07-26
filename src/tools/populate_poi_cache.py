"""
Script para popular o cache de POIs das 3 cidades de uma vez.
Roda UMA VEZ — depois o pipeline usa o cache sem chamar Overpass.

Uso: python -m src.tools.populate_poi_cache
"""
import sys, os, json, time, requests
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATA_DIR  = Path(__file__).resolve().parent.parent.parent / "data"
CACHE_FILE = DATA_DIR / "overpass_cache.json"

CITY_CENTERS = {
    "granada_zaidan":   (37.1580, -3.5980, "Zaidín, Granada"),
    "granada_centro":   (37.1773, -3.5986, "Centro, Granada"),
    "granada_ronda":    (37.1700, -3.6050, "Camino de Ronda, Granada"),
    "alicante_benalua": (38.3390, -0.4850, "Benalúa, Alicante"),
    "alicante_centro":  (38.3452, -0.4810, "Centro, Alicante"),
    "nerja_centro":     (36.7503, -3.8747, "Centro, Nerja"),
}

POI_QUERIES = {
    "supermarket": '["shop"="supermarket"]',
    "gym":         '["leisure"="fitness_centre"]',
    "pharmacy":    '["amenity"="pharmacy"]',
    "bus_stop":    '["highway"="bus_stop"]',
    "park":        '["leisure"="park"]',
}

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = radians(lat1), radians(lat2)
    a = sin(radians(lat2-lat1)/2)**2 + cos(p1)*cos(p2)*sin(radians(lon2-lon1)/2)**2
    return 2*R*atan2(sqrt(a), sqrt(1-a))

def fetch(lat, lon, tag, radius=2000):
    q = f"[out:json][timeout:25];(node{tag}(around:{radius},{lat},{lon});way{tag}(around:{radius},{lat},{lon}););out center;"
    for ep in ENDPOINTS:
        try:
            time.sleep(2)
            r = requests.post(ep, data={"data": q}, timeout=20)
            if r.status_code == 200:
                els = r.json().get("elements", [])
                print(f"    ✓ {ep.split('/')[2]} → {len(els)} elementos")
                return els
            print(f"    ✗ {ep.split('/')[2]} → {r.status_code}")
        except Exception as e:
            print(f"    ✗ {ep.split('/')[2]} → {e.__class__.__name__}")
    return []

def main():
    print("=" * 55)
    print("SET_UP — Populando cache de POIs por bairro")
    print("Isso roda UMA VEZ e salva tudo localmente.")
    print("=" * 55)

    cache = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            print(f"\nCache existente: {len(cache)} entradas")
        except Exception:
            pass

    total_new = 0
    for zone_key, (lat, lon, label) in CITY_CENTERS.items():
        print(f"\n[{label}]")
        for poi_name, poi_tag in POI_QUERIES.items():
            cache_key = f"{lat:.3f}|{lon:.3f}|{poi_tag}|2000"
            if cache_key in cache and cache[cache_key]:
                print(f"  {poi_name}: cache ({len(cache[cache_key])} POIs) ✓")
                continue
            print(f"  {poi_name}:")
            els = fetch(lat, lon, poi_tag)
            pois = []
            for el in els:
                elat = el.get("lat") or el.get("center", {}).get("lat")
                elon = el.get("lon") or el.get("center", {}).get("lon")
                if not elat or not elon: continue
                tags = el.get("tags", {})
                dist = haversine(lat, lon, elat, elon)
                pois.append({
                    "name": tags.get("name", "Sem nome"),
                    "brand": tags.get("brand", ""),
                    "lat": elat, "lon": elon,
                    "distance_meters": round(dist),
                    "walk_minutes": round(dist/80, 1),
                    "address": f"{tags.get('addr:street','')} {tags.get('addr:housenumber','')}".strip(),
                })
            pois.sort(key=lambda p: p["distance_meters"])
            cache[cache_key] = pois
            total_new += 1
            if pois:
                print(f"    {len(pois)} POIs | mais próximo: {pois[0]['name']} ({pois[0]['distance_meters']}m)")
            else:
                print(f"    0 POIs")
            CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*55}")
    print(f"Cache populado: {total_new} novas entradas (total: {len(cache)})")
    print(f"Agora rode: python -m src.main")

if __name__ == "__main__":
    main()
