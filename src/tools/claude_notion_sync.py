"""
claude_notion_sync.py v2 — SET_UP Notion sync via Claude API (Haiku 4.5)

Melhorias v2:
  1. Remove blocos LIVE antigos antes de inserir novo (resolve acúmulo)
  2. Inclui dados FIN-TRADER (patrimônio BR) na análise fiscal da cidade
  3. Custo dieta real com mix multi-mercado (Mercadona + Lidl + DIA + Consum + Amazon.es)
  4. Análise dividendos BR vs ES integrada (ponto 5 do backlog)

Roda como step final no GitHub Actions após src.main.
Custo: ~$0.01/execução com Haiku 4.5 → ~$0.60/mês (2x/dia × 30 dias).
"""

import sys
import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

CITY_PAGES = {
    "granada":  "3736d7bcf70c81fa99b6f425e9585326",
    "alicante": "3736d7bcf70c81cf80c9e70f08b9c264",
    "nerja":    "3736d7bcf70c816cbb7ac922c2c0138e",
}

HUB_PAGE_ID  = "3736d7bcf70c81c09c0ff224c550e309"
FIN_TRADER_URL = "https://raw.githubusercontent.com/Mauricio1806/FIN-TRADER/main/data/portfolio.json"

# IDs databases Notion
DB_ALUGUEIS = "ddb22b4db5394ae18d8e4abaa74093b8"
DB_PRECOS   = "380f34f8196d49818dcf15e9de9fbc88"


# ──────────────────────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────────────────────

def load_latest() -> dict:
    f = DATA_DIR / "latest.json"
    if not f.exists():
        print("[erro] latest.json não encontrado")
        sys.exit(1)
    return json.loads(f.read_text(encoding="utf-8"))


def load_multi_market() -> dict:
    """Carrega consolidado multi-mercado se disponível."""
    f = DATA_DIR / "multi_market.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def fetch_fintrader_portfolio() -> dict:
    """
    Busca dados do FIN-TRADER: patrimônio BR (Inter CDB) + Wise EUR/USD.
    Faz parse da carteira.html para extrair valores hardcoded dos inputs.
    Retorna dict com os dados financeiros reais.
    """
    try:
        # Tentar primeiro o JSON de portfolio se existir
        r = requests.get(FIN_TRADER_URL, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass

    # Fallback: parsear carteira.html extraindo valores dos inputs
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/Mauricio1806/FIN-TRADER/main/carteira.html",
            timeout=15,
        )
        if r.status_code != 200:
            return {}

        import re
        html = r.text

        def extract_input(id_name: str) -> str:
            pattern = rf'id="{id_name}"[^>]*value="([^"]+)"'
            m = re.search(pattern, html)
            return m.group(1) if m else ""

        def parse_br_num(s: str) -> float:
            """Converte '103.021,21' → 103021.21"""
            if not s:
                return 0.0
            return float(s.replace(".", "").replace(",", "."))

        portfolio = {
            "inter_brl":         parse_br_num(extract_input("interSaldo")),
            "inter_principal":   parse_br_num(extract_input("interPrincipal")),
            "inter_taxa":        parse_br_num(extract_input("interTaxa")),
            "inter_ir":          parse_br_num(extract_input("interIR")),
            "wise_usd_saldo":    parse_br_num(extract_input("wiseUsdSaldo")),
            "wise_usd_rendeu":   parse_br_num(extract_input("wiseUsdRendeu")),
            "wise_usd_taxa":     parse_br_num(extract_input("wiseUsdTaxa")),
            "wise_usd_rate":     parse_br_num(extract_input("wiseUsdRate")),
            "wise_eur_saldo":    parse_br_num(extract_input("wiseEurSaldo")),
            "wise_eur_rendeu":   parse_br_num(extract_input("wiseEurRendeu")),
            "wise_eur_taxa":     parse_br_num(extract_input("wiseEurTaxa")),
            "wise_eur_rate":     parse_br_num(extract_input("wiseEurRate")),
            "inter_usd_saldo":   parse_br_num(extract_input("interUsdSaldo")),
            "inter_usd_taxa":    parse_br_num(extract_input("interUsdTaxa")),
            "inter_usd_rate":    parse_br_num(extract_input("interUsdRate")),
        }

        # Calcular totais
        usd_brl = (portfolio["wise_usd_saldo"] + portfolio["inter_usd_saldo"]) * portfolio["wise_usd_rate"]
        eur_brl = portfolio["wise_eur_saldo"] * portfolio["wise_eur_rate"]
        total_brl = portfolio["inter_brl"] + usd_brl + eur_brl

        # Renda mensal líquida estimada
        ir_fator = 1 - portfolio["inter_ir"] / 100
        inter_mensal_liq = portfolio["inter_brl"] * (portfolio["inter_taxa"] / 100 / 12) * ir_fator
        wise_usd_mensal  = portfolio["wise_usd_saldo"] * (portfolio["wise_usd_taxa"] / 100 / 12) * portfolio["wise_usd_rate"]
        wise_eur_mensal  = portfolio["wise_eur_saldo"] * (portfolio["wise_eur_taxa"] / 100 / 12) * portfolio["wise_eur_rate"]
        renda_mensal_liq = inter_mensal_liq + wise_usd_mensal + wise_eur_mensal

        portfolio.update({
            "total_brl":          round(total_brl, 2),
            "usd_brl_total":      round(usd_brl, 2),
            "eur_brl_total":      round(eur_brl, 2),
            "renda_mensal_liq_brl": round(renda_mensal_liq, 2),
            "source":             "carteira.html_parsed",
        })
        return portfolio

    except Exception as e:
        print(f"  [FIN-TRADER] erro ao buscar portfolio: {e}")
        return {}


# ──────────────────────────────────────────────────────────────
# BUILD PROMPT
# ──────────────────────────────────────────────────────────────

def build_city_summary(data: dict, city: str, multi_market: dict, portfolio: dict) -> str:
    """Monta resumo completo da cidade para o prompt do Claude."""
    listings = [l for l in data.get("listings", []) if l.get("city") == city]
    prices   = [p for p in data.get("prices",   []) if p.get("city") == city]
    now      = data.get("generated_at", "")[:10]
    city_name = city.capitalize()

    # Custo dieta — multi-mercado se disponível, senão Mercadona only
    city_mm  = multi_market.get(city, {})
    diet_merc = city_mm.get("total_mercadona", 0)
    diet_opt  = city_mm.get("total_otimizado", 0)
    diet_econ = city_mm.get("total_economy",   0)
    pct_saved = city_mm.get("pct_saved",       0)

    # Se não temos multi-market, calcular só Mercadona
    if not diet_merc:
        SIMPLE_DIET = {
            "pechuga pollo congelada": 9.0, "huevos medianos": 8.0,
            "claras huevo pasteurizadas": 6.0, "arroz integral": 3.0,
            "patatas": 6.0, "mantequilla sin sal": 3.0,
            "cacahuete natural": 0.5, "aceite oliva virgen extra": 1.0,
            "miel flores": 0.5, "cafe molido natural": 1.2,
            "leche entera": 6.0, "leche en polvo entera": 3.0,
        }
        price_idx = {p["query"]: p for p in prices if p.get("price_eur")}
        diet_merc = sum(
            price_idx.get(q, {}).get("price_eur", 0) * qty
            for q, qty in SIMPLE_DIET.items()
        )
        diet_opt = diet_merc

    # FIN-TRADER — resumo financeiro BR
    fin_lines = []
    if portfolio:
        fin_lines = [
            "",
            "PATRIMÔNIO BR (FIN-TRADER carteira.html):",
            f"  Inter CDB: R$ {portfolio.get('inter_brl', 0):,.2f} @ {portfolio.get('inter_taxa', 0)}% a.a.",
            f"  Wise USD:  $ {portfolio.get('wise_usd_saldo', 0):,.2f} (≈ R$ {portfolio.get('usd_brl_total', 0):,.2f})",
            f"  Wise EUR:  € {portfolio.get('wise_eur_saldo', 0):,.2f} (≈ R$ {portfolio.get('eur_brl_total', 0):,.2f})",
            f"  TOTAL BRL: R$ {portfolio.get('total_brl', 0):,.2f}",
            f"  Renda passiva/mês (est. líq.): R$ {portfolio.get('renda_mensal_liq_brl', 0):,.2f}",
            f"  EUR disponível para aluguel ES: € {portfolio.get('wise_eur_saldo', 0):,.2f}",
        ]

    # Bairros Idealista
    IDEALISTA_LINKS = {
        "granada": [
            ("Zaidín",          "https://www.idealista.com/alquiler-viviendas/zaidin-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
            ("Arabial",         "https://www.idealista.com/alquiler-viviendas/arabial-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
            ("Camino de Ronda", "https://www.idealista.com/alquiler-viviendas/camino-de-ronda-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
            ("Chana",           "https://www.idealista.com/alquiler-viviendas/chana-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
            ("Beiro",           "https://www.idealista.com/alquiler-viviendas/beiro-granada-granada/con-precio-hasta_750,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ],
        "alicante": [
            ("Benalúa",    "https://www.idealista.com/alquiler-viviendas/benalua-alicante-alicante/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
            ("Carolinas",  "https://www.idealista.com/alquiler-viviendas/carolinas-alicante-alicante/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
            ("Centro",     "https://www.idealista.com/alquiler-viviendas/centro-alicante-alicante/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
            ("San Blas",   "https://www.idealista.com/alquiler-viviendas/san-blas-alicante-alicante/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ],
        "nerja": [
            ("Centro",      "https://www.idealista.com/alquiler-viviendas/nerja/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
            ("Capistrano",  "https://www.idealista.com/alquiler-viviendas/nerja/con-precio-hasta_950,de-un-dormitorio,amueblado/?ordenado-por=precios-asc"),
        ],
    }

    idealista_lines = ["", "LINKS IDEALISTA POR BAIRRO (mobilhado, 1q, preço crescente):"]
    for bairro, url in IDEALISTA_LINKS.get(city, []):
        idealista_lines.append(f"  {bairro}: {url}")

    # Montar linhas
    lines = [
        f"Data: {now}",
        f"Cidade: {city_name}",
        "",
        "CUSTO DIETA REAL:",
        f"  Mercadona only: €{diet_merc:.2f}/mês",
    ]

    if diet_opt < diet_merc and diet_econ > 0:
        lines += [
            f"  Mix otimizado:  €{diet_opt:.2f}/mês",
            f"  Economia:       €{diet_econ:.2f}/mês ({pct_saved}%) = €{diet_econ*12:.0f}/ano",
        ]
        by_market = city_mm.get("by_market", {})
        if by_market:
            lines.append("  Distribuição: " + " | ".join(
                f"{m}:€{v:.0f}" for m, v in sorted(by_market.items(), key=lambda x: -x[1])
            ))

    lines += [
        "",
        f"Total anúncios: {len(listings)}",
        "",
        "ALUGUÉIS (top 8 por score):",
    ]

    for l in listings[:8]:
        sm_m = l.get("nearest_supermarket_m")
        gm_m = l.get("nearest_gym_m")
        sm_t = f"{sm_m}m {(l.get('nearest_supermarket_name') or '')[:15]}" if sm_m else "?"
        gm_t = f"{gm_m}m {(l.get('nearest_gym_name') or '')[:12]}" if gm_m else "?"
        kit  = " ✅fogão" if l.get("kitchen_type") == "gas_or_full" else (
               " 🍳cooktop" if l.get("kitchen_type") == "cooktop_only" else "")
        loc  = (l.get("location") or "")[:25]
        url  = l.get("url", "")
        lines.append(f"€{l['price']}/mês{kit} | {loc} | 🛒{sm_t} | 💪{gm_t} | {url}")

    lines += ["", "PREÇOS MERCADONA (top 8):"]
    for p in prices[:8]:
        lines.append(f"{p.get('product_name','')[:35]} | €{p.get('price_eur')} | {p.get('unit','')}")

    lines += fin_lines + idealista_lines
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# NOTION — REMOVER BLOCOS LIVE ANTIGOS
# ──────────────────────────────────────────────────────────────

def remove_old_live_blocks_prompt(page_id: str, city_name: str, notion_token: str) -> str:
    """
    Gera prompt para o Claude remover blocos LIVE antigos via Notion API REST.
    A remoção é feita via DELETE /v1/blocks/{block_id}.
    """
    return f"""Você é um assistente que gerencia blocos do Notion via API REST.

TAREFA: Remover blocos LIVE antigos da página {city_name} (ID: {page_id}) antes de inserir o novo.

PASSOS:
1. GET https://api.notion.com/v1/blocks/{page_id}/children?page_size=50
   Headers: Authorization: Bearer {notion_token} | Notion-Version: 2022-06-28

2. Para cada bloco encontrado:
   - Se for callout com texto começando em "🔴 LIVE SET_UP" → DELETE https://api.notion.com/v1/blocks/{{block_id}}
   - Se for heading_3 com texto começando em "🏠 Melhores aluguéis" ou "🔴" → DELETE
   - Se for heading_3 com texto começando em "💰 Mix ótimo" ou "🛒 Preços" → DELETE
   - Se for bulleted_list_item e os 3 blocos anteriores eram LIVE → DELETE
   - PARAR quando encontrar bloco que NÃO é parte do LIVE (ex: heading_1, heading_2 sem 🔴, toggle, etc.)

3. Responda com: "REMOVIDOS: N blocos" ou "NENHUM LIVE ENCONTRADO" ou "ERRO: <motivo>"

Execute TODOS os DELETEs necessários agora."""


def build_insert_live_prompt(
    page_id: str,
    city_name: str,
    summary: str,
    notion_token: str,
    now: str,
) -> str:
    """Prompt para inserir o novo bloco LIVE no topo da página."""
    return f"""Você é um assistente que atualiza páginas do Notion via API REST.

TAREFA: Inserir bloco LIVE atualizado no topo da página {city_name} (ID: {page_id}).

Use: PATCH https://api.notion.com/v1/blocks/{page_id}/children
Headers: Authorization: Bearer {notion_token} | Notion-Version: 2022-06-28 | Content-Type: application/json

Estrutura do payload (children array):
[
  {{
    "object": "block",
    "type": "callout",
    "callout": {{
      "rich_text": [{{"type": "text", "text": {{"content": "🔴 LIVE SET_UP — {now}  |  dados abaixo atualizados agora"}}}}],
      "icon": {{"emoji": "🔴"}},
      "color": "red_background"
    }}
  }},
  {{
    "object": "block",
    "type": "heading_3",
    "heading_3": {{"rich_text": [{{"type": "text", "text": {{"content": "🏠 Melhores aluguéis disponíveis agora — {city_name}"}}}}]}}
  }}
  // ... continuar com os aluguéis como bulleted_list_item
]

DADOS PARA INSERIR:
{summary}

Gere o payload JSON completo e faça o PATCH agora.
Responda apenas com: "OK: {city_name} atualizada — N blocos inseridos" ou "ERRO: <motivo>"."""


# ──────────────────────────────────────────────────────────────
# CLAUDE API CALL
# ──────────────────────────────────────────────────────────────

def call_claude(prompt: str, api_key: str, mcp_url: str | None = None) -> str:
    """Chama Claude Haiku 4.5 com ou sem MCP Notion."""
    body: dict = {
        "model":      "claude-haiku-4-5-20251001",
        "max_tokens": 2048,
        "messages":   [{"role": "user", "content": prompt}],
    }

    if mcp_url:
        body["mcp_servers"] = [
            {"type": "url", "url": mcp_url, "name": "notion-mcp"}
        ]

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":          api_key,
                "anthropic-version":  "2023-06-01",
                "content-type":       "application/json",
                "anthropic-beta":     "mcp-client-2025-04-04",
            },
            json=body,
            timeout=120,
        )
        if resp.status_code == 200:
            content = resp.json().get("content", [])
            return " ".join(
                block.get("text", "")
                for block in content
                if block.get("type") == "text"
            ).strip()
        else:
            return f"ERRO HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return f"ERRO: {e}"


# ──────────────────────────────────────────────────────────────
# ANÁLISE DIVIDENDOS BR vs ES (ponto 5 do backlog)
# ──────────────────────────────────────────────────────────────

def build_dividend_analysis(portfolio: dict) -> str:
    """
    Análise fiscal dividendos/renda fixa BR vs ES.
    Contexto: ~R$100k em RF BR, expatriação Out/2026, Modelo 149 Beckham Jan-Abr/2027.
    """
    inter_brl   = portfolio.get("inter_brl",           103_021.21)
    inter_taxa  = portfolio.get("inter_taxa",           14.25)
    inter_ir    = portfolio.get("inter_ir",             15.0)
    wise_eur    = portfolio.get("wise_eur_saldo",       3_014.87)
    eur_rate    = portfolio.get("wise_eur_rate",        5.7971)

    # Renda anual bruta Inter
    renda_anual_bruta = inter_brl * (inter_taxa / 100)
    renda_anual_liq_br = renda_anual_bruta * (1 - inter_ir / 100)

    # Se declarar no BR (residente até Out/2026):
    # IR 15% após 720 dias → já está aplicado em inter_ir
    ir_br_anual = renda_anual_bruta * (inter_ir / 100)

    # Se declarar na ES via Beckham (Modelo 149):
    # Beckham: rendas estrangeiras isentas nos primeiros 6 anos
    # Mas CDB Inter = renda fixa BR = rendimento de fonte estrangeira
    # → ISENTO em ES se aplicar Beckham corretamente
    # Risco: AEAT pode questionar se é "rendimento de capital mobiliário"
    ir_es_beckham = 0.0  # isento estimado

    # Se NÃO aplicar Beckham (regime geral ES):
    # IRPF escala: até €6k = 19%, €6-50k = 21%, >€50k = 23%
    renda_eur = renda_anual_bruta / eur_rate
    if renda_eur <= 6_000:
        ir_es_geral = renda_eur * 0.19
    elif renda_eur <= 50_000:
        ir_es_geral = 6_000 * 0.19 + (renda_eur - 6_000) * 0.21
    else:
        ir_es_geral = 6_000 * 0.19 + 44_000 * 0.21 + (renda_eur - 50_000) * 0.23
    ir_es_geral_brl = ir_es_geral * eur_rate

    lines = [
        "",
        "═══ ANÁLISE FISCAL DIVIDENDOS BR vs ES ═══",
        f"Base: R$ {inter_brl:,.2f} em CDB Inter @ {inter_taxa}% a.a.",
        f"Renda anual bruta:  R$ {renda_anual_bruta:,.2f} (≈ €{renda_anual_bruta/eur_rate:,.2f})",
        f"",
        f"📌 CENÁRIO A — Declarar no BR (residente até Out/2026):",
        f"  IR 15% após 720 dias: R$ {ir_br_anual:,.2f}/ano",
        f"  Renda líquida:         R$ {renda_anual_liq_br:,.2f}/ano",
        f"  Timing: IR pago na fonte → nada a declarar adicionalmente",
        f"",
        f"📌 CENÁRIO B — Beckham (Modelo 149, Jan-Abr/2027):",
        f"  Rendas de fonte estrangeira: ISENTAS (estimado)",
        f"  IR ES = €{ir_es_beckham:.2f} → economia vs BR: R$ {ir_br_anual:,.2f}/ano",
        f"  ⚠️  Risco: AEAT pode tratar CDB como capital mobiliário ES",
        f"  ⚠️  Prazo: Modelo 149 deve ser protocolado até 6 meses após chegada (≤ Abr/2027)",
        f"",
        f"📌 CENÁRIO C — Regime geral ES (sem Beckham):",
        f"  IRPF ES: €{ir_es_geral:,.2f} (≈ R$ {ir_es_geral_brl:,.2f})",
        f"  Pior cenário — pagar IR ES + perder isenção Beckham",
        f"",
        f"✅ RECOMENDAÇÃO: Manter CDB no BR, pagar IR 15% (Cenário A) até Out/2026.",
        f"   Protocolar Modelo 149 imediatamente na chegada a ES.",
        f"   Consultar gestor fiscal ES antes de declarar rendimentos BR no IRPF ES.",
        f"",
        f"📅 TIMELINE CRÍTICO:",
        f"  Out/2026: Chegada ES → início residência fiscal ES",
        f"  Jan-Abr/2027: Protocolar Modelo 149 Beckham",
        f"  Jan/2027: Fim contrato Capco/TCS → reavaliação estratégia",
        f"  2027: Primeira declaração IRPF ES (renda 2026 parcial)",
        f"  Wise EUR € {wise_eur:,.2f} disponível: reserva primeiros meses ES",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

def update_notion_via_claude(data: dict, multi_market: dict, portfolio: dict):
    api_key      = os.getenv("ANTHROPIC_API_KEY", "")
    notion_token = os.getenv("NOTION_TOKEN", "")

    if not api_key:
        print("[skip] ANTHROPIC_API_KEY não configurada")
        return

    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    # Análise fiscal (só uma vez, não por cidade)
    dividend_analysis = build_dividend_analysis(portfolio)

    for city, page_id in CITY_PAGES.items():
        city_name = city.capitalize()
        print(f"\n  → {city_name}")

        summary = build_city_summary(data, city, multi_market, portfolio)
        summary += dividend_analysis  # injeta análise fiscal em cada cidade

        # PASSO 1: Remover blocos LIVE antigos
        print(f"    [1/2] Removendo blocos LIVE antigos...")
        remove_prompt = remove_old_live_blocks_prompt(page_id, city_name, notion_token)
        remove_result = call_claude(remove_prompt, api_key)
        print(f"    Remove: {remove_result[:120]}")

        # PASSO 2: Inserir bloco LIVE novo
        print(f"    [2/2] Inserindo LIVE atualizado...")
        insert_prompt = build_insert_live_prompt(page_id, city_name, summary, notion_token, now)
        insert_result = call_claude(insert_prompt, api_key)
        print(f"    Insert: {insert_result[:120]}")

        if "OK" in insert_result:
            print(f"    ✓ {city_name} atualizada")
        else:
            print(f"    [AVISO] {city_name}: {insert_result[:200]}")

    print("\n✓ Concluído")


def main():
    print("=" * 55)
    print("SET_UP claude_notion_sync v2")
    print(f"Rodando: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    data         = load_latest()
    multi_market = load_multi_market()
    portfolio    = fetch_fintrader_portfolio()

    if portfolio:
        print(f"\n[FIN-TRADER] Patrimônio: R$ {portfolio.get('total_brl', 0):,.2f}")
        print(f"  EUR disponível: € {portfolio.get('wise_eur_saldo', 0):,.2f}")
    else:
        print("[FIN-TRADER] Portfolio não disponível — usando fallback")

    if multi_market:
        for city in ["granada", "alicante", "nerja"]:
            mm = multi_market.get(city, {})
            if mm:
                print(f"  [{city}] Dieta ótima: €{mm.get('total_otimizado', 0):.2f}/mês "
                      f"(economia: €{mm.get('total_economy', 0):.2f}/mês)")

    update_notion_via_claude(data, multi_market, portfolio)


if __name__ == "__main__":
    main()
