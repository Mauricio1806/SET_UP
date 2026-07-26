"""
Multi-market consolidator — cruza preços reais de Mercadona + Lidl + DIA + Consum + Amazon.es.

Para cada item da dieta real:
  1. Compara preços reais coletados (quando disponíveis)
  2. Fallback: aplica fator de desconto estimado sobre preço Mercadona
  3. Escolhe mercado mais barato por categoria
  4. Calcula custo mensal total otimizado vs. custo tudo-Mercadona

Output:
  - consolidado por cidade: mercado_ótimo por item, economia/mês, economia/ano
  - dados para o bloco LIVE do Notion
  - dados para a página de dieta real do Notion
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone


# Fatores de fallback (quando scraping não retornou preço real)
MARKET_FACTORS = {
    "Mercadona": 1.00,
    "Lidl":      0.85,
    "DIA":       0.80,
    "Consum":    0.92,
    "Amazon.es": None,  # suplementos — preço próprio, não comparar
}

# Por categoria, qual mercado costuma ser mais barato
CATEGORY_MARKET_PREFERENCE = {
    "proteína":    ["DIA", "Lidl", "Consum", "Mercadona"],
    "carboidrato": ["DIA", "Lidl", "Mercadona"],
    "vegetal":     ["Lidl", "Mercadona", "DIA"],
    "gordura":     ["Lidl", "DIA", "Mercadona"],
    "bebida":      ["Consum", "DIA", "Lidl", "Mercadona"],
    "tempero":     ["DIA", "Mercadona", "Lidl"],
    "suplemento":  ["Amazon.es"],   # exclusivo
    "higiene":     ["DIA", "Lidl", "Mercadona"],
    "gato":        ["Lidl", "DIA", "Mercadona"],
}

# Quantidades mensais por item (mirror de diet_sync.py)
DIET_MONTHLY_QTY = {
    "pechuga pollo congelada":      9.0,
    "claras huevo pasteurizadas":   6.0,
    "huevos medianos":              8.0,
    "leche en polvo entera":        3.0,
    "queso manchego curado":        0.2,
    "queso mozzarella":             1.0,
    "arroz integral":               3.0,
    "patatas":                      6.0,
    "pan integral rebanado":        4.0,
    "verduras congeladas mix":      3.0,
    "arandanos congelados":         1.0,
    "moras congeladas":             1.0,
    "fresas congeladas":            2.0,
    "platano banana":               2.0,
    "mantequilla sin sal":          3.0,
    "cacahuete natural":            0.5,
    "aceite oliva virgen extra":    1.0,
    "miel flores":                  0.5,
    "cafe molido natural":          1.2,
    "leche entera":                 6.0,
    "ketchup heinz":                1.0,
    "salsa teriyaki kikkoman":      1.0,
    "creatina monohidrato":         0.5,   # 150g/mês, embalagem 300g
    "proteina whey":                1.0,   # 2kg/mês, embalagem 2kg
    "champu anticaspa hombre":      1.0,
    "pasta dientes blanqueadora":   1.0,
    "gel ducha":                    1.0,
    "desodorante roll on":          1.0,
    "pienso gato adulto":           1.0,   # ~3kg embalagem
    "arena gato aglomerante":       1.0,   # ~5L embalagem
}

# Categoria por item (para escolher mercado preferido)
DIET_ITEM_CATEGORY = {
    "pechuga pollo congelada":      "proteína",
    "claras huevo pasteurizadas":   "proteína",
    "huevos medianos":              "proteína",
    "leche en polvo entera":        "proteína",
    "queso manchego curado":        "proteína",
    "queso mozzarella":             "proteína",
    "arroz integral":               "carboidrato",
    "patatas":                      "carboidrato",
    "pan integral rebanado":        "carboidrato",
    "verduras congeladas mix":      "vegetal",
    "arandanos congelados":         "vegetal",
    "moras congeladas":             "vegetal",
    "fresas congeladas":            "vegetal",
    "platano banana":               "vegetal",
    "mantequilla sin sal":          "gordura",
    "cacahuete natural":            "gordura",
    "aceite oliva virgen extra":    "gordura",
    "miel flores":                  "gordura",
    "cafe molido natural":          "bebida",
    "leche entera":                 "bebida",
    "ketchup heinz":                "tempero",
    "salsa teriyaki kikkoman":      "tempero",
    "creatina monohidrato":         "suplemento",
    "proteina whey":                "suplemento",
    "champu anticaspa hombre":      "higiene",
    "pasta dientes blanqueadora":   "higiene",
    "gel ducha":                    "higiene",
    "desodorante roll on":          "higiene",
    "pienso gato adulto":           "gato",
    "arena gato aglomerante":       "gato",
}


def build_price_index(all_prices: List[Dict], city: str) -> Dict[str, Dict[str, float]]:
    """
    Monta índice: {query → {market → price_eur}}
    Inclui preços reais de todos os mercados para a cidade.
    """
    index: Dict[str, Dict[str, float]] = {}
    for p in all_prices:
        if p.get("city") != city:
            continue
        query  = p.get("query", "")
        market = p.get("market", "Mercadona")
        price  = p.get("price_eur")
        if not price:
            continue
        if query not in index:
            index[query] = {}
        # Manter menor preço se duplicatas
        if market not in index[query] or price < index[query][market]:
            index[query][market] = price
    return index


def get_best_price(
    query: str,
    price_index: Dict[str, Dict[str, float]],
    category: str,
) -> Tuple[Optional[float], str, Optional[float]]:
    """
    Retorna (melhor_preço, mercado, preço_mercadona).
    Prioriza preço real; fallback para fator sobre Mercadona.
    """
    item_prices = price_index.get(query, {})
    mercadona_price = item_prices.get("Mercadona")

    # Suplementos — só Amazon.es, sem comparação
    if category == "suplemento":
        amazon_price = item_prices.get("Amazon.es")
        return (amazon_price, "Amazon.es", None)

    # Sem preço Mercadona — sem base para comparar
    if not mercadona_price:
        # Tentar outro mercado com preço real
        for market in CATEGORY_MARKET_PREFERENCE.get(category, []):
            if market in item_prices:
                return (item_prices[market], market, None)
        return (None, "?", None)

    # Comparar preços reais + estimativas fator
    best_price  = mercadona_price
    best_market = "Mercadona"

    for market in CATEGORY_MARKET_PREFERENCE.get(category, []):
        if market == "Amazon.es":
            continue
        if market in item_prices:
            # Preço real disponível
            candidate = item_prices[market]
        elif market in MARKET_FACTORS and MARKET_FACTORS[market]:
            # Fallback: estimar pelo fator
            candidate = round(mercadona_price * MARKET_FACTORS[market], 2)
        else:
            continue

        if candidate < best_price:
            best_price  = candidate
            best_market = market

    return (round(best_price, 2), best_market, mercadona_price)


def consolidate_multi_market(all_prices: List[Dict], city: str) -> Dict:
    """
    Consolida preços de todos os mercados para a cidade.

    Retorna dict com:
      - items: lista de itens com preço ótimo + economias
      - total_mercadona: custo mensal tudo no Mercadona
      - total_otimizado: custo mensal com mix de mercados
      - total_economy: economia mensal
      - pct_saved: % de economia
      - by_market: distribuição de compras por mercado
      - updated: timestamp
    """
    price_index = build_price_index(all_prices, city)
    items       = []
    total_merc  = 0.0
    total_opt   = 0.0
    by_market: Dict[str, float] = {}

    for query, qty in DIET_MONTHLY_QTY.items():
        category = DIET_ITEM_CATEGORY.get(query, "outros")
        best_price, best_market, merc_price = get_best_price(
            query, price_index, category
        )

        # Custo mensal
        opt_cost  = round(best_price * qty, 2) if best_price else None
        merc_cost = round(merc_price * qty, 2) if merc_price else None
        savings   = round((merc_cost - opt_cost), 2) if (merc_cost and opt_cost) else None

        if merc_cost:
            total_merc += merc_cost
        if opt_cost:
            total_opt  += opt_cost
            by_market[best_market] = by_market.get(best_market, 0.0) + opt_cost

        items.append({
            "query":        query,
            "category":     category,
            "qty":          qty,
            "best_market":  best_market,
            "best_price":   best_price,
            "merc_price":   merc_price,
            "opt_monthly":  opt_cost,
            "merc_monthly": merc_cost,
            "savings_eur":  savings,
            "is_real_price": query in price_index and best_market in price_index[query],
        })

    total_merc  = round(total_merc, 2)
    total_opt   = round(total_opt, 2)
    economy     = round(total_merc - total_opt, 2) if total_merc > 0 else 0.0
    pct_saved   = round((economy / total_merc * 100), 1) if total_merc > 0 else 0.0

    return {
        "city":           city,
        "items":          items,
        "total_mercadona":total_merc,
        "total_otimizado":total_opt,
        "total_economy":  economy,
        "pct_saved":      pct_saved,
        "by_market":      by_market,
        "city_name":      {"granada": "Granada", "alicante": "Alicante", "nerja": "Nerja"}.get(city, city),
        "pct_total_saved":pct_saved,
        "updated":        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def build_market_summary_text(consolidado: Dict) -> str:
    """Gera texto resumo para o bloco LIVE do Notion."""
    city_name = consolidado["city_name"]
    lines = [
        f"💰 Mix ótimo de mercados — {city_name}",
        f"Mercadona: €{consolidado['total_mercadona']:.2f}/mês  →  Mix otimizado: €{consolidado['total_otimizado']:.2f}/mês",
        f"Economia: €{consolidado['total_economy']:.2f}/mês ({consolidado['pct_saved']}%) = €{consolidado['total_economy']*12:.0f}/ano",
        "",
        "Compras por mercado:",
    ]
    for market, total in sorted(consolidado["by_market"].items(), key=lambda x: -x[1]):
        pct = round(total / consolidado["total_otimizado"] * 100, 1) if consolidado["total_otimizado"] else 0
        lines.append(f"  {market}: €{total:.2f} ({pct}%)")

    return "\n".join(lines)
