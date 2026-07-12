"""
Notion Sync — EVOLUI as páginas existentes do hub Spain Digital Nomad.
Não deleta nada. Apenas adiciona/atualiza um bloco "🔴 LIVE" com os
melhores anúncios encontrados no dia.

Estratégia:
1. Cria (idempotente) uma database "🏠 Aluguéis Live" filha do hub
2. Cria (idempotente) uma database "🛒 Preços Mercadona Live" filha do hub
3. Atualiza um callout de status no topo de cada página de cidade
"""

import os
from datetime import datetime, timezone
from typing import List, Dict
import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def get(self, path):
        r = requests.get(f"{NOTION_API_BASE}{path}", headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def post(self, path, payload):
        r = requests.post(f"{NOTION_API_BASE}{path}", headers=self.headers,
                          json=payload, timeout=30)
        if r.status_code >= 400:
            print(f"  [notion erro] {r.status_code} — {r.text[:200]}")
        r.raise_for_status()
        return r.json()

    def patch(self, path, payload):
        r = requests.patch(f"{NOTION_API_BASE}{path}", headers=self.headers,
                           json=payload, timeout=30)
        if r.status_code >= 400:
            print(f"  [notion erro] {r.status_code} — {r.text[:200]}")
        r.raise_for_status()
        return r.json()


class NotionSync:
    """Sincroniza resultados de scraping para o Notion sem destruir conteúdo."""

    LIVE_RENT_DB_TITLE = "🏠 Aluguéis Live — Últimas 24h"
    LIVE_PRICE_DB_TITLE = "🛒 Preços Mercadona Live"

    def __init__(self, token: str, hub_id: str):
        self.client = NotionClient(token)
        self.hub_id = hub_id

    def sync_all(self, listings: List[Dict], prices: List[Dict]):
        """Sync completo — cria dbs se necessário e insere linhas."""
        if not self.client.token:
            print("  [warn] NOTION_TOKEN vazio — skip Notion sync")
            return

        try:
            rent_db_id = self._find_or_create_rent_db()
            self._insert_top_listings(rent_db_id, listings, top_n=30)
        except Exception as e:
            print(f"  [erro] sync alugueis: {e}")

        try:
            price_db_id = self._find_or_create_price_db()
            self._insert_prices(price_db_id, prices)
        except Exception as e:
            print(f"  [erro] sync precos: {e}")

    # --------------------------------------------------------
    # DATABASES: cria se não existir
    # --------------------------------------------------------

    def _find_or_create_rent_db(self) -> str:
        existing = self._find_child_database(self.LIVE_RENT_DB_TITLE)
        if existing:
            return existing

        print(f"  → Criando database '{self.LIVE_RENT_DB_TITLE}'")
        payload = {
            "parent": {"type": "page_id", "page_id": self.hub_id},
            "icon": {"type": "emoji", "emoji": "🏠"},
            "title": [{"type": "text", "text": {"content": self.LIVE_RENT_DB_TITLE}}],
            "properties": {
                "Anúncio": {"title": {}},
                "Cidade": {"select": {"options": [
                    {"name": "Granada", "color": "green"},
                    {"name": "Alicante", "color": "blue"},
                    {"name": "Nerja", "color": "yellow"},
                ]}},
                "Preço €": {"number": {"format": "euro"}},
                "Score": {"number": {"format": "number"}},
                "Grade": {"select": {"options": [
                    {"name": "S — Excelente", "color": "green"},
                    {"name": "A — Muito bom", "color": "blue"},
                    {"name": "B — Bom", "color": "yellow"},
                    {"name": "C — OK", "color": "orange"},
                    {"name": "D — Fraco", "color": "red"},
                ]}},
                "Quartos": {"number": {}},
                "m²": {"number": {}},
                "Supermercado (m)": {"number": {}},
                "Academia (m)": {"number": {}},
                "Marcas prioritárias": {"rich_text": {}},
                "Fonte": {"select": {"options": [
                    {"name": "idealista"},
                    {"name": "habitaclia"},
                    {"name": "pisos.com"},
                ]}},
                "URL": {"url": {}},
                "Coletado em": {"date": {}},
            },
        }
        result = self.client.post("/databases", payload)
        return result["id"]

    def _find_or_create_price_db(self) -> str:
        existing = self._find_child_database(self.LIVE_PRICE_DB_TITLE)
        if existing:
            return existing

        print(f"  → Criando database '{self.LIVE_PRICE_DB_TITLE}'")
        payload = {
            "parent": {"type": "page_id", "page_id": self.hub_id},
            "icon": {"type": "emoji", "emoji": "🛒"},
            "title": [{"type": "text", "text": {"content": self.LIVE_PRICE_DB_TITLE}}],
            "properties": {
                "Produto": {"title": {}},
                "Categoria": {"select": {"options": [
                    {"name": "proteína"}, {"name": "carboidrato"}, {"name": "gordura"},
                    {"name": "bebida"}, {"name": "higiene"}, {"name": "gato"},
                ]}},
                "Cidade": {"select": {"options": [
                    {"name": "Granada"}, {"name": "Alicante"}, {"name": "Nerja"},
                ]}},
                "Marca": {"rich_text": {}},
                "Preço €": {"number": {"format": "euro"}},
                "Unidade": {"rich_text": {}},
                "URL": {"url": {}},
                "Coletado em": {"date": {}},
            },
        }
        result = self.client.post("/databases", payload)
        return result["id"]

    def _find_child_database(self, title: str) -> str:
        """Procura database filha do hub pelo título."""
        try:
            children = self.client.get(f"/blocks/{self.hub_id}/children?page_size=100")
            for block in children.get("results", []):
                if block.get("type") == "child_database":
                    if block["child_database"]["title"] == title:
                        return block["id"]
        except Exception as e:
            print(f"  [warn] erro procurando db existente: {e}")
        return ""

    # --------------------------------------------------------
    # INSERE LINHAS
    # --------------------------------------------------------

    def _insert_top_listings(self, db_id: str, listings: List[Dict], top_n: int = 30):
        top = listings[:top_n]
        print(f"  → Inserindo {len(top)} top aluguéis no Notion...")
        now_iso = datetime.now(timezone.utc).isoformat()

        for listing in top:
            city = listing.get("city", "granada").capitalize()
            title = (listing.get("title") or "Sem título")[:100]
            price = listing.get("price")
            score = listing.get("scores", {}).get("total", 0)
            grade = listing.get("grade", "D — Fraco")
            brands = ", ".join(sorted({
                p.get("priority_brand")
                for pois in listing.get("pois", {}).values()
                for p in pois
                if p.get("priority_brand")
            }))

            props = {
                "Anúncio": {"title": [{"text": {"content": title}}]},
                "Cidade": {"select": {"name": city}},
                "Grade": {"select": {"name": grade}},
                "Coletado em": {"date": {"start": now_iso}},
            }
            if price:
                props["Preço €"] = {"number": price}
            if score:
                props["Score"] = {"number": score}
            if listing.get("rooms"):
                props["Quartos"] = {"number": listing["rooms"]}
            if listing.get("m2"):
                props["m²"] = {"number": listing["m2"]}
            if listing.get("nearest_supermarket_m"):
                props["Supermercado (m)"] = {"number": listing["nearest_supermarket_m"]}
            if listing.get("nearest_gym_m"):
                props["Academia (m)"] = {"number": listing["nearest_gym_m"]}
            if brands:
                props["Marcas prioritárias"] = {"rich_text": [{"text": {"content": brands[:200]}}]}
            if listing.get("source"):
                props["Fonte"] = {"select": {"name": listing["source"]}}
            if listing.get("url"):
                props["URL"] = {"url": listing["url"]}

            try:
                self.client.post("/pages", {
                    "parent": {"database_id": db_id},
                    "properties": props,
                })
            except Exception as e:
                print(f"    [erro insert] {e}")

    def _insert_prices(self, db_id: str, prices: List[Dict]):
        print(f"  → Inserindo {len(prices)} preços no Notion...")
        now_iso = datetime.now(timezone.utc).isoformat()

        for item in prices:
            title = (item.get("product_name") or item.get("query") or "Produto")[:100]
            props = {
                "Produto": {"title": [{"text": {"content": title}}]},
                "Categoria": {"select": {"name": item.get("category", "proteína")}},
                "Cidade": {"select": {"name": item.get("city", "granada").capitalize()}},
                "Coletado em": {"date": {"start": now_iso}},
            }
            if item.get("brand"):
                props["Marca"] = {"rich_text": [{"text": {"content": item["brand"][:200]}}]}
            if item.get("price_eur"):
                props["Preço €"] = {"number": item["price_eur"]}
            if item.get("unit"):
                props["Unidade"] = {"rich_text": [{"text": {"content": str(item["unit"])[:100]}}]}
            if item.get("url"):
                props["URL"] = {"url": item["url"]}

            try:
                self.client.post("/pages", {
                    "parent": {"database_id": db_id},
                    "properties": props,
                })
            except Exception as e:
                print(f"    [erro insert preço] {e}")
