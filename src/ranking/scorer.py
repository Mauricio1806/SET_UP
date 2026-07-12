"""
Scorer — ranking composto por preço + proximidade + bairro.
Score de 0 a 100 (mais alto = melhor).
"""

from typing import Dict, List
from ..config import POI_CATEGORIES, TARGET_CITIES


class ListingScorer:
    """
    Score composto (0-100):
    - Preço vs teto do cenário (30 pontos)
    - Proximidade a supermercado (25 pontos)
    - Proximidade a academia (20 pontos)
    - Outros POIs (15 pontos)
    - Marcas prioritárias encontradas (10 pontos)
    """

    def score(self, listing: Dict) -> Dict:
        city_key = listing.get("city")
        city = TARGET_CITIES.get(city_key, {})
        max_rent = city.get("max_rent_eur", 1000)

        price_score = self._score_price(listing.get("price"), max_rent)
        supermarket_score = self._score_proximity(listing.get("nearest_supermarket_m"), 500, weight=25)
        gym_score = self._score_proximity(listing.get("nearest_gym_m"), 800, weight=20)
        other_score = (
            self._score_proximity(listing.get("nearest_pharmacy_m"), 500, weight=5) +
            self._score_proximity(listing.get("nearest_public_transport_m"), 400, weight=5) +
            self._score_proximity(listing.get("nearest_green_space_m"), 800, weight=5)
        )
        brand_score = self._score_priority_brands(listing.get("pois", {}))

        total = round(price_score + supermarket_score + gym_score + other_score + brand_score, 1)

        listing["scores"] = {
            "price": round(price_score, 1),
            "supermarket": round(supermarket_score, 1),
            "gym": round(gym_score, 1),
            "other_pois": round(other_score, 1),
            "priority_brands": round(brand_score, 1),
            "total": total,
        }

        # Grade humana
        if total >= 80:
            listing["grade"] = "S — Excelente"
        elif total >= 65:
            listing["grade"] = "A — Muito bom"
        elif total >= 50:
            listing["grade"] = "B — Bom"
        elif total >= 35:
            listing["grade"] = "C — OK"
        else:
            listing["grade"] = "D — Fraco"

        return listing

    def _score_price(self, price, max_rent):
        if not price:
            return 0
        if price >= max_rent:
            return 0
        # Score linear: quanto mais barato, mais pontos, até 30
        ratio = 1 - (price / max_rent)
        return 30 * ratio

    def _score_proximity(self, distance_meters, ideal_meters, weight):
        if not distance_meters:
            return 0
        if distance_meters <= ideal_meters * 0.5:
            return weight
        if distance_meters <= ideal_meters:
            return weight * 0.75
        if distance_meters <= ideal_meters * 1.5:
            return weight * 0.5
        if distance_meters <= ideal_meters * 2:
            return weight * 0.25
        return 0

    def _score_priority_brands(self, pois: Dict) -> float:
        """+2 pontos por marca prioritária encontrada, max 10."""
        matched = set()
        for cat_key, poi_list in pois.items():
            for poi in poi_list:
                if poi.get("priority_brand"):
                    matched.add(f"{cat_key}:{poi['priority_brand']}")
        return min(10, len(matched) * 2)


def rank_listings(listings: List[Dict]) -> List[Dict]:
    """Ordena por score total desc."""
    scorer = ListingScorer()
    scored = [scorer.score(l) for l in listings]
    return sorted(scored, key=lambda x: x["scores"]["total"], reverse=True)
