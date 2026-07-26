"""
City Sync — atualiza as páginas de cidade existentes no hub
com um bloco LIVE no topo: aluguéis reais + preços do dia.
"""

import os
import requests
from datetime import datetime, timezone
from typing import List, Dict

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION  = "2022-06-28"

# IDs das páginas de cidade já existentes
CITY_PAGE_IDS = {
    "granada":  "3736d7bcf70c81fa99b6f425e9585326",
    "alicante": "3736d7bcf70c81cf80c9e70f08b9c264",
    "nerja":    "3736d7bcf70c816cbb7ac922c2c0138e",
}

CITY_NAMES = {
    "granada":  "Granada",
    "alicante": "Alicante",
    "nerja":    "Nerja",
}

# Bairros prioritários por cidade (do hub)
PRIORITY_NEIGHBORHOODS = {
    "granada":  ["Zaidín", "Arabial", "Camino de Ronda", "Chana", "Beiro"],
    "alicante": ["Benalúa", "Carolinas", "Centro", "San Blas"],
    "nerja":    ["Centro", "Capistrano", "Parador"],
}


class CitySyncNotion:
    def __init__(self, token: str):
        self.token = token.strip()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _get(self, path):
        r = requests.get(f"{NOTION_API_BASE}{path}", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def _patch(self, path, payload):
        r = requests.patch(f"{NOTION_API_BASE}{path}",
                           headers=self.headers, json=payload, timeout=30)
        if r.status_code >= 400:
            print(f"    [notion erro] {r.status_code}: {r.text[:150]}")
        r.raise_for_status()
        return r.json()

    def _delete(self, block_id):
        requests.delete(f"{NOTION_API_BASE}/blocks/{block_id}",
                        headers=self.headers, timeout=10)

    def update_all_cities(self, ranked_listings: List[Dict],
                          mercadona_prices: List[Dict],
                          diet_costs: Dict):
        """Atualiza o bloco LIVE em cada página de cidade."""
        for city_key, page_id in CITY_PAGE_IDS.items():
            try:
                print(f"  → Atualizando página {CITY_NAMES[city_key]}...")
                self._update_city_page(city_key, page_id, ranked_listings,
                                       mercadona_prices, diet_costs)
                print(f"    ✓ {CITY_NAMES[city_key]} atualizada")
            except Exception as e:
                print(f"    [ERRO] {city_key}: {e}")

    def _update_city_page(self, city_key: str, page_id: str,
                          all_listings: List[Dict],
                          all_prices: List[Dict],
                          diet_costs: Dict):
        """Insere bloco LIVE diretamente no topo da página."""
        city_listings = [l for l in all_listings if l.get("city") == city_key]
        city_prices   = [p for p in all_prices if p.get("city") == city_key]
        diet_cost     = diet_costs.get(city_key, {})
        now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        new_blocks = self._build_live_blocks(city_key, now, city_listings,
                                             city_prices, diet_cost)

        # Insere no topo sem precisar ler filhos existentes
        self._patch(f"/blocks/{page_id}/children", {
            "children": new_blocks,
        })

    def _build_live_blocks(self, city_key: str, now: str,
                           listings: List[Dict],
                           prices: List[Dict],
                           diet_cost: Dict) -> List[Dict]:
        """Monta os blocos Notion para o LIVE."""
        blocks = []
        city_name = CITY_NAMES[city_key]
        total_diet = diet_cost.get("total", 0)

        # Callout principal
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {
                    "content": f"🔴 LIVE SET_UP — {now}  |  {len(listings)} anúncios  |  Dieta real: €{total_diet:.2f}/mês"
                }}],
                "icon": {"emoji": "🔴"},
                "color": "red_background",
            }
        })

        # Seção aluguéis
        if listings:
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {
                    "content": f"🏠 Melhores aluguéis disponíveis agora — {city_name}"
                }}]}
            })

            # Top 5 por bairro prioritário primeiro
            priority = PRIORITY_NEIGHBORHOODS.get(city_key, [])
            priority_listings = sorted(
                listings,
                key=lambda l: (
                    not any(nb.lower() in (l.get("location","") or "").lower()
                            for nb in priority),
                    -l.get("scores", {}).get("total", 0)
                )
            )[:8]

            for l in priority_listings:
                price   = l.get("price", "?")
                loc     = (l.get("location") or "")[:30]
                score   = l.get("scores", {}).get("total", 0)
                sm      = l.get("nearest_supermarket_m")
                sm_name = (l.get("nearest_supermarket_name") or "")[:15]
                gm      = l.get("nearest_gym_m")
                gm_name = (l.get("nearest_gym_name") or "")[:15]
                url     = l.get("url", "")
                title   = (l.get("title") or "")[:50]
                kitchen = l.get("kitchen_type","")
                fogao   = " ✅fogão" if kitchen == "gas_or_full" else " 🍳cooktop" if kitchen == "cooktop_only" else ""

                sm_txt = f"🛒 {sm}m {sm_name}" if sm else "🛒 ?"
                gm_txt = f"💪 {gm}m {gm_name}" if gm else "💪 ?"
                geo_txt = "📍" if l.get("_geocoded") else "📍~"

                line = f"€{price}/mês{fogao} · {loc} · {sm_txt} · {gm_txt} · {geo_txt} {score:.0f}pt"

                if url:
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [
                                {"type": "text", "text": {"content": f"{line} → "},
                                 "annotations": {}},
                                {"type": "text", "text": {
                                    "content": title,
                                    "link": {"url": url}
                                }, "annotations": {"color": "blue"}},
                            ]
                        }
                    })
                else:
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": line}}]
                        }
                    })

        # Seção preços Mercadona
        if prices and total_diet:
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {
                    "content": f"🛒 Preços Mercadona — Custo real da sua dieta: €{total_diet:.2f}/mês"
                }}]}
            })

            # Proteínas (mais caras — mais relevantes)
            protein_prices = [p for p in prices if p.get("category") == "proteína"][:4]
            for p in protein_prices:
                name  = (p.get("product_name") or p.get("query") or "")[:40]
                price = p.get("price_eur")
                unit  = p.get("unit") or ""
                trend = p.get("price_trend", "")
                trend_emoji = "↑" if "subiu" in trend else "↓" if "desceu" in trend else "→"
                if price:
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {
                                "content": f"{trend_emoji} {name} — €{price} {unit}"
                            }}]
                        }
                    })

        # Divisor
        blocks.append({"object": "block", "type": "divider", "divider": {}})

        return blocks
