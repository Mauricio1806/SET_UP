"""
Scorer v2 — penaliza cooktop, anúncios sem geocoding, sazonais.
Filtros: ativo, longa duração, fogão real (preferível).
"""

from typing import Dict, List
from ..config import POI_CATEGORIES, TARGET_CITIES


class ListingScorer:
    """
    Score composto (0-100):
    - Preço vs teto da cidade       (30 pts)
    - Supermercado próximo          (25 pts)
    - Academia próxima              (20 pts)
    - Outros POIs                   (15 pts)
    - Marcas prioritárias           (10 pts)
    Penalizações:
    - Cooktop apenas               (-15 pts)
    - Geocoding falhou             (-10 pts)
    - Anúncio sazonal              (-20 pts)
    """

    def score(self, listing: Dict) -> Dict:
        city_key = listing.get("city", "granada")
        city = TARGET_CITIES.get(city_key, {})
        max_rent = city.get("max_rent_eur", 1000)

        # Componentes positivos
        price_score      = self._score_price(listing.get("price"), max_rent)
        supermarket_score = self._score_proximity(listing.get("nearest_supermarket_m"), 500, 25)
        gym_score         = self._score_proximity(listing.get("nearest_gym_m"), 800, 20)
        other_score = (
            self._score_proximity(listing.get("nearest_pharmacy_m"), 500, 5) +
            self._score_proximity(listing.get("nearest_public_transport_m"), 400, 5) +
            self._score_proximity(listing.get("nearest_green_space_m"), 800, 5)
        )
        brand_score = self._score_priority_brands(listing.get("pois", {}))

        # Penalizações
        penalty = 0
        if listing.get("has_cooktop_only"):
            penalty += 15
        if not listing.get("_geocoded"):
            penalty += 10  # distâncias não são confiáveis
        if listing.get("is_seasonal"):
            penalty += 20

        total = max(0, round(price_score + supermarket_score + gym_score +
                             other_score + brand_score - penalty, 1))

        listing["scores"] = {
            "price":           round(price_score, 1),
            "supermarket":     round(supermarket_score, 1),
            "gym":             round(gym_score, 1),
            "other_pois":      round(other_score, 1),
            "priority_brands": round(brand_score, 1),
            "penalty":         -penalty,
            "total":           total,
        }

        # Grade
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

        # Tags de alerta
        listing["alerts"] = []
        if listing.get("has_cooktop_only"):
            listing["alerts"].append("🍳 Só cooktop")
        if not listing.get("_geocoded"):
            listing["alerts"].append("📍 Localização imprecisa")
        if listing.get("is_seasonal"):
            listing["alerts"].append("🏖️ Sazonal")
        if listing.get("kitchen_type") == "gas_or_full":
            listing["alerts"].append("✅ Fogão real")

        return listing

    def _score_price(self, price, max_rent):
        if not price or price >= max_rent:
            return 0
        return 30 * (1 - price / max_rent)

    def _score_proximity(self, dist_m, ideal_m, weight):
        if dist_m is None:
            return 0
        if dist_m <= ideal_m * 0.4:
            return weight          # <40% do ideal = perfeito
        if dist_m <= ideal_m:
            return weight * 0.75
        if dist_m <= ideal_m * 1.5:
            return weight * 0.5
        if dist_m <= ideal_m * 2.5:
            return weight * 0.25
        return 0

    def _score_priority_brands(self, pois: Dict) -> float:
        matched = set()
        for cat_key, poi_list in pois.items():
            for poi in poi_list:
                if poi.get("priority_brand"):
                    matched.add(f"{cat_key}:{poi['priority_brand']}")
        return min(10, len(matched) * 2.5)


def rank_listings(listings: List[Dict]) -> List[Dict]:
    """Filtra inativos/sazonais, scoring, ordena."""
    scorer = ListingScorer()
    valid = [l for l in listings if l.get("price") and not l.get("is_seasonal", False)]
    scored = [scorer.score(l) for l in valid]
    return sorted(scored, key=lambda x: x["scores"]["total"], reverse=True)
