"""
Chama a API do Claude com o latest.json e pede para atualizar
as páginas Granada/Alicante/Nerja no Notion via MCP.

Roda após o pipeline principal no GitHub Actions.
"""

import sys
import os
import json
import requests
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

CITY_PAGES = {
    "granada":  "3736d7bcf70c81fa99b6f425e9585326",
    "alicante": "3736d7bcf70c81cf80c9e70f08b9c264",
    "nerja":    "3736d7bcf70c816cbb7ac922c2c0138e",
}


def load_latest() -> dict:
    f = DATA_DIR / "latest.json"
    if not f.exists():
        print("[erro] latest.json não encontrado")
        sys.exit(1)
    return json.loads(f.read_text(encoding="utf-8"))


def build_city_summary(data: dict, city: str) -> str:
    listings = [l for l in data["listings"] if l.get("city") == city]
    prices   = [p for p in data["prices"] if p.get("city") == city]
    now      = data["generated_at"][:10]

    # Custo dieta
    DIET = {
        "pechuga pollo": 9.0, "huevos xl": 8.0,
        "claras huevo pasteurizadas": 6.0, "arroz integral": 3.0,
        "patatas": 6.0, "mantequilla sin sal": 3.0,
        "cacahuete tostado": 1.0, "aceite oliva virgen extra": 1.0,
        "miel": 0.5, "cafe molido": 1.2,
        "leche entera": 6.0, "leche en polvo": 3.0,
    }
    price_idx = {p["query"]: p for p in prices if p.get("price_eur")}
    diet_total = sum(
        price_idx.get(q, {}).get("price_eur", 0) * qty
        for q, qty in DIET.items()
    )

    lines = [f"Data: {now}", f"Cidade: {city}", f"Custo dieta: €{diet_total:.2f}/mês",
             f"Total anúncios: {len(listings)}", "", "ALUGUÉIS:"]

    for l in listings[:8]:
        sm   = l.get("nearest_supermarket_m")
        gm   = l.get("nearest_gym_m")
        smn  = (l.get("nearest_supermarket_name") or "")[:15]
        gmn  = (l.get("nearest_gym_name") or "")[:12]
        sm_t = f"{sm}m {smn}" if sm else "?"
        gm_t = f"{gm}m {gmn}" if gm else "?"
        url  = l.get("url", "")
        loc  = (l.get("location") or "")[:25]
        kit  = " ✅fogão" if l.get("kitchen_type") == "gas_or_full" else \
               " 🍳cooktop" if l.get("kitchen_type") == "cooktop_only" else ""
        lines.append(f"€{l['price']}/mês{kit} | {loc} | 🛒{sm_t} | 💪{gm_t} | {url}")

    lines += ["", "PREÇOS MERCADONA (top 8):"]
    for p in prices[:8]:
        lines.append(f"{p.get('product_name','')[:35]} | €{p.get('price_eur')} | {p.get('unit','')}")

    return "\n".join(lines)


def update_notion_via_claude(data: dict):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    notion_token = os.getenv("NOTION_TOKEN", "")
    if not api_key:
        print("[skip] ANTHROPIC_API_KEY não configurada")
        return

    for city, page_id in CITY_PAGES.items():
        summary = build_city_summary(data, city)
        city_name = city.capitalize()
        now = data["generated_at"][:10]

        prompt = f"""Você é um assistente que atualiza páginas do Notion via API REST.

Atualize a página do Notion com ID `{page_id}` (página {city_name} do hub Spain Digital Nomad).

Use a API do Notion com o token: {notion_token}

Faça um PATCH em https://api.notion.com/v1/blocks/{page_id}/children com os seguintes dados de aluguéis e preços do dia:

{summary}

Insira um callout "🔴 LIVE SET_UP — {now}" seguido de lista com os aluguéis e tabela de preços.
Use Notion-Version: 2022-06-28.
Responda apenas com "OK: {city_name} atualizada" ou "ERRO: <motivo>"."""

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            if resp.status_code == 200:
                result = resp.json()["content"][0]["text"]
                print(f"  {city_name}: {result}")
            else:
                print(f"  [ERRO] {city_name}: {resp.status_code}")
        except Exception as e:
            print(f"  [ERRO] {city_name}: {e}")


def main():
    print("=" * 50)
    print("SET_UP — Claude Notion Sync")
    print("=" * 50)
    data = load_latest()
    print(f"Dados: {data['generated_at'][:16]}")
    print(f"Anúncios: {data['stats']['total_ranked']} | Preços: {data['stats']['total_prices']}")
    update_notion_via_claude(data)
    print("✓ Concluído")


if __name__ == "__main__":
    main()
