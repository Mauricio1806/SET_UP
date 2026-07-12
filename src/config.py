"""
SET_UP — Configurações centrais
Cidades-alvo, categorias de POI, pesos de scoring.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
DATA_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)

load_dotenv(PROJECT_ROOT / ".env")

# Câmbio de referência (atualizado pelo scraper de câmbio se disponível)
EUR_BRL_RATE = float(os.getenv("EUR_BRL_RATE", "5.90"))

# ============================================================
# CIDADES-ALVO
# ============================================================

TARGET_CITIES = {
    "granada": {
        "name": "Granada",
        "lat": 37.1773,
        "lon": -3.5986,
        "target_neighborhoods": [
            "Zaidín", "Camino de Ronda", "Beiro",
            "Centro", "Ronda", "Pajaritos"
        ],
        "max_rent_eur": 750,
        "min_rooms": 1,
        "notion_page_id": "3736d7bcf70c81fa99b6f425e9585326",
    },
    "alicante": {
        "name": "Alicante",
        "lat": 38.3452,
        "lon": -0.4810,
        "target_neighborhoods": [
            "Benalúa", "Carolinas Bajas", "Centro",
            "San Blas", "Ensanche Diputación"
        ],
        "max_rent_eur": 950,
        "min_rooms": 1,
        "notion_page_id": "3736d7bcf70c81cf80c9e70f08b9c264",
    },
    "nerja": {
        "name": "Nerja",
        "lat": 36.7503,
        "lon": -3.8747,
        "target_neighborhoods": [
            "Centro", "Balcón de Europa", "Parador",
            "Capistrano"
        ],
        "max_rent_eur": 950,
        "min_rooms": 1,
        "notion_page_id": "3736d7bcf70c816cbb7ac922c2c0138e",
    },
}

# ============================================================
# CATEGORIAS DE POI (Points of Interest)
# ============================================================

POI_CATEGORIES = {
    "supermarket": {
        "label": "Supermercado",
        "overpass_query": '["shop"="supermarket"]',
        "priority_brands": ["Mercadona", "Lidl", "Dia", "Carrefour", "Aldi", "Covirán"],
        "weight": 30,
        "max_walk_meters": 500,
    },
    "gym": {
        "label": "Academia",
        "overpass_query": '["leisure"="fitness_centre"]',
        "priority_brands": ["Basic-Fit", "Synergym", "McFit", "Anytime Fitness", "VivaGym"],
        "weight": 25,
        "max_walk_meters": 800,
    },
    "pharmacy": {
        "label": "Farmácia",
        "overpass_query": '["amenity"="pharmacy"]',
        "priority_brands": [],
        "weight": 10,
        "max_walk_meters": 500,
    },
    "public_transport": {
        "label": "Transporte público",
        "overpass_query": '["highway"="bus_stop"]',
        "priority_brands": [],
        "weight": 15,
        "max_walk_meters": 400,
    },
    "green_space": {
        "label": "Área verde",
        "overpass_query": '["leisure"="park"]',
        "priority_brands": [],
        "weight": 10,
        "max_walk_meters": 800,
    },
    "restaurant": {
        "label": "Restaurante",
        "overpass_query": '["amenity"="restaurant"]',
        "priority_brands": [],
        "weight": 10,
        "max_walk_meters": 500,
    },
}

# ============================================================
# THRESHOLDS DE PROXIMIDADE (metros a pé)
# ============================================================

PROXIMITY_THRESHOLDS = {
    "excellent": 300,   # <5 min a pé
    "good": 600,        # <10 min a pé
    "acceptable": 1000, # <15 min a pé
}

# ============================================================
# SCRAPER SETTINGS
# ============================================================

SCRAPER_SETTINGS = {
    "delay_min": 2.0,
    "delay_max": 5.0,
    "timeout": 20,
    "max_pages_per_source": 3,
    "max_retries": 2,
}

# ============================================================
# NOTION SYNC
# ============================================================

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_HUB_ID = os.getenv("NOTION_HUB_ID", "3736d7bcf70c81c09c0ff224c550e309")

# ============================================================
# DASHBOARD
# ============================================================

DASHBOARD_TITLE = "🏠 SET_UP — Aluguel Live Espanha"
DASHBOARD_SUBTITLE = "Scoring de apartamentos por proximidade + preço + bairro"
DASHBOARD_UPDATE_URL = "https://mauricio1806.github.io/SET_UP/"
