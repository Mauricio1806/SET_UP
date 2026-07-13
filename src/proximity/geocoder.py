"""
Geocoder v2 — extrai rua do título antes de geocodificar,
com estratégias de fallback progressivas.
"""

import re
import time
from typing import Optional, Tuple, Dict
import requests


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def extract_street(text: str) -> str:
    """
    Extrai rua de títulos como:
    - 'Apartamento en calle Curro Cuchares'       → 'Curro Cuchares'
    - 'Piso en calle Ángel, 21'                   → 'calle Ángel 21'
    - 'Apartamento en Centro-Catedral'            → 'Centro Catedral'
    - 'Apartamento en calle de la Castañeda'      → 'calle de la Castañeda'
    - 'Apartamento en Beiro'                      → 'Beiro'
    - '3 hab | Granada capital | Zaidín | 590€'   → 'Zaidín'
    """
    if not text:
        return text

    # Remove prefixos de tipo de imóvel
    clean = re.sub(
        r'^(apartamento|piso|estudio|ático|dúplex|loft|casa|chalet|'
        r'habitación|local|oficina)\s+(en\s+)?',
        '', text.lower().strip()
    )

    # Padrão: "calle ..." ou "avenida ..." ou "plaza ..."
    match = re.search(
        r'(calle|c/|avda?\.?|avenida|plaza|paseo|camino|barrio|urb\.?|'
        r'urbanización|carretera|ronda|vía)\s+(.{3,50}?)(?:\s*[,|\|]|$)',
        clean, re.IGNORECASE
    )
    if match:
        street = match.group(0).strip().rstrip(',|').strip()
        return street[:80]

    # Bairros conhecidos
    neighborhoods = [
        'zaidín', 'ronda', 'beiro', 'realejo', 'albaicín', 'albayzín',
        'centro', 'catedral', 'genil', 'chana', 'figares', 'arabial',
        'pajaritos', 'hipercor', 'benalúa', 'carolinas', 'playa',
    ]
    for nb in neighborhoods:
        if nb in clean:
            return nb.capitalize()

    # Fallback: usa o texto original até o primeiro separador
    parts = re.split(r'[,|\|]', text)
    if parts:
        candidate = parts[0].strip()
        # Remove prefixos de tipo
        candidate = re.sub(
            r'^(apartamento|piso|estudio|ático|dúplex|loft)\s+en\s+',
            '', candidate, flags=re.IGNORECASE
        ).strip()
        if len(candidate) > 3:
            return candidate[:80]

    return text[:80]


class Geocoder:
    def __init__(self, user_agent="SET_UP-Mauricio1806/2.0"):
        self.user_agent = user_agent
        self._cache: Dict[str, Optional[Tuple[float, float]]] = {}

    def geocode(self, address: str, city: str, country: str = "España") -> Optional[Tuple[float, float]]:
        """
        Geocodifica endereço com 3 tentativas progressivas:
        1. Rua extraída + cidade
        2. Texto original + cidade
        3. Só a cidade (fallback explícito)
        """
        street = extract_street(address)
        attempts = [
            (street, city),
            (address[:80], city),
        ]

        for query_address, query_city in attempts:
            key = f"{query_address}|{query_city}"
            if key in self._cache:
                result = self._cache[key]
                if result:
                    return result
                continue

            result = self._nominatim_search(query_address, query_city, country)
            self._cache[key] = result
            if result:
                return result

        return None  # Deixa o analyzer usar fallback explícito

    def _nominatim_search(self, address: str, city: str, country: str) -> Optional[Tuple[float, float]]:
        time.sleep(1.2)  # Rate limit Nominatim
        query = f"{address}, {city}, {country}"
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "es"},
                headers={"User-Agent": self.user_agent},
                timeout=12,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    return (float(data[0]["lat"]), float(data[0]["lon"]))
        except Exception as e:
            print(f"    [geocode] {e.__class__.__name__} — {address[:50]}")
        return None
