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
        self.token = token.strip()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def validate(self) -> bool:
        """Testa se o token é válido antes de tentar qualquer sync."""
        import os
        hub_id = os.getenv("NOTION_HUB_ID", "3736d7bcf70c81c09c0ff224c550e309")
        try:
            # /users/me não funciona com tokens ntn_ — usa o hub diretamente
            r = requests.get(
                f"{NOTION_API_BASE}/pages/{hub_id}",
                headers=self.headers, timeout=10
            )
            if r.status_code == 200:
                title = r.json().get("properties", {}).get("title", {})
                print(f"    ✓ Notion autenticado — hub acessível")
                return True
            elif r.status_code == 401:
                print(f"  [Notion 401] Token rejeitado.")
                print(f"  → Confirme que a integração SET_UP está conectada ao hub:")
                print(f"     Hub → ... → Conexões → SET_UP deve aparecer como Conectado")
                return False
            elif r.status_code == 403:
                print(f"  [Notion 403] Token válido mas sem acesso ao hub.")
                print(f"  → No hub Spain Digital Nomad → ... → Conexões → Adicionar SET_UP")
                return False
            else:
                print(f"  [Notion {r.status_code}] {r.text[:150]}")
                return False
        except Exception as e:
            print(f"  [Notion erro] {e}")
            return False

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

    # IDs das databases criadas diretamente via MCP no hub
    RENT_DB_ID   = "ddb22b4db5394ae18d8e4abaa74093b8"
    PRICE_DB_ID  = "380f34f8196d49818dcf15e9de9fbc88"
    LIVE_RENT_DB_TITLE  = "🏠 Aluguéis Live — SET_UP"
    LIVE_PRICE_DB_TITLE = "🛒 Preços Mercadona Live — SET_UP"

    def __init__(self, token: str, hub_id: str):
        self.client = NotionClient(token)
        self.hub_id = hub_id

    def sync_all(self, listings: List[Dict], prices: List[Dict]):
        """Sync direto nas databases já criadas via MCP."""
        if not self.client.token:
            print("  [skip] NOTION_TOKEN não configurado")
            return
        try:
            self._insert_top_listings(self.RENT_DB_ID, listings, top_n=30)
            print(f"  ✓ {min(len(listings),30)} aluguéis inseridos no Notion")
        except Exception as e:
            print(f"  [ERRO] aluguéis: {e}")
        try:
            self._insert_prices(self.PRICE_DB_ID, prices)
            print(f"  ✓ {len(prices)} preços inseridos no Notion")
        except Exception as e:
            print(f"  [ERRO] preços: {e}")

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
        now_iso = datetime.now(timezone.utc).date().isoformat()
        for listing in top:
            city = listing.get("city", "granada").capitalize()
            title = (listing.get("title") or "Sem título")[:100]
            price = listing.get("price")
            score = listing.get("scores", {}).get("total", 0)
            grade = listing.get("grade", "D — Fraco")
            kitchen = listing.get("kitchen_type", "unknown")
            fogao = "Sim" if kitchen == "gas_or_full" else "Não" if kitchen == "cooktop_only" else "Desconhecido"
            brands = ", ".join(sorted({
                p.get("priority_brand")
                for pois in listing.get("pois", {}).values()
                for p in pois if p.get("priority_brand")
            }))

            props = {
                "Anúncio": title,
                "Cidade": city,
                "Grade": grade,
                "Fogão real": fogao,
                "date:Coletado em:start": now_iso,
                "date:Coletado em:is_datetime": 0,
            }
            if price: props["Preço €"] = price
            if score: props["Score"] = round(score, 1)
            if listing.get("rooms"): props["Quartos"] = listing["rooms"]
            if listing.get("m2"): props["m²"] = listing["m2"]
            if listing.get("nearest_supermarket_m"): props["Supermercado (m)"] = listing["nearest_supermarket_m"]
            if listing.get("nearest_supermarket_name"): props["Supermercado nome"] = listing["nearest_supermarket_name"][:100]
            if listing.get("nearest_gym_m"): props["Academia (m)"] = listing["nearest_gym_m"]
            if listing.get("nearest_gym_name"): props["Academia nome"] = listing["nearest_gym_name"][:100]
            if listing.get("location"): props["Bairro"] = listing["location"][:100]
            if listing.get("source"): props["Fonte"] = listing["source"]
            if listing.get("url"): props["userDefined:URL"] = listing["url"]

            try:
                self.client.post("/pages", {
                    "parent": {"database_id": db_id},
                    "properties": self._props_to_notion(props),
                })
            except Exception as e:
                print(f"    [erro insert aluguel] {e}")

    def _props_to_notion(self, props: dict) -> dict:
        """Converte dict simples para formato de propriedades da API Notion."""
        result = {}
        for key, value in props.items():
            if value is None:
                continue
            if key.startswith("date:") and key.endswith(":start"):
                prop_name = key[5:-6]
                if prop_name not in result:
                    result[prop_name] = {"date": {"start": value}}
                else:
                    result[prop_name]["date"]["start"] = value
            elif key.startswith("date:") and key.endswith(":is_datetime"):
                pass  # já tratado acima
            elif key == "Anúncio" or key == "Produto":
                result[key] = {"title": [{"text": {"content": str(value)}}]}
            elif isinstance(value, (int, float)):
                result[key] = {"number": value}
            elif key in ("Cidade", "Grade", "Fonte", "Categoria", "Fogão real", "Trend"):
                result[key] = {"select": {"name": str(value)}}
            elif key in ("userDefined:URL",):
                result[key] = {"url": str(value)}
            else:
                result[key] = {"rich_text": [{"text": {"content": str(value)[:200]}}]}
        return result

    def _insert_prices(self, db_id: str, prices: List[Dict]):
        now_iso = datetime.now(timezone.utc).date().isoformat()
        for item in prices:
            title = (item.get("product_name") or item.get("query") or "Produto")[:100]
            trend = item.get("price_trend", "→ estável")
            if "subiu" in trend: trend_select = "↑ subiu"
            elif "desceu" in trend: trend_select = "↓ desceu"
            elif trend == "novo": trend_select = "novo"
            else: trend_select = "→ estável"

            props = {
                "Produto": title,
                "Categoria": item.get("category", "proteína"),
                "Cidade": item.get("city", "granada").capitalize(),
                "Trend": trend_select,
                "date:Coletado em:start": now_iso,
                "date:Coletado em:is_datetime": 0,
            }
            if item.get("brand"): props["Marca"] = item["brand"][:100]
            if item.get("price_eur"): props["Preço €"] = item["price_eur"]
            if item.get("unit"): props["Unidade"] = str(item["unit"])[:50]
            if item.get("consumo_mensal"): props["Consumo mensal"] = item["consumo_mensal"][:100]
            if item.get("price_change_pct") is not None:
                props["Variação 15d"] = f"{item['price_change_pct']:+.1f}%"
            if item.get("url"): props["userDefined:URL"] = item["url"]

            try:
                self.client.post("/pages", {
                    "parent": {"database_id": db_id},
                    "properties": self._props_to_notion(props),
                })
            except Exception as e:
                print(f"    [erro insert preço] {e}")
