"""
PATCH para src/main.py — adicionar multi-market scraping após o step de Mercadona.

INSTRUÇÕES DE INTEGRAÇÃO:
Copie os blocos marcados abaixo para o main.py existente nos pontos indicados.

─── BLOCO 1: imports adicionais (no topo após os imports existentes) ─────────

from .scrapers.lidl import LidlScraper
from .scrapers.dia import DiaScraper
from .scrapers.consum import ConsumScraper
from .scrapers.amazon_es import AmazonEsScraper
from .scrapers.multi_market import consolidate_multi_market, build_market_summary_text

─── BLOCO 2: após a seção [1/5] Scraping Mercadona (após mercadona_scraper.scrape_city) ─

    # --------------------------------------------------
    # 1b. SCRAPING MULTI-MARKET (Lidl + DIA + Consum + Amazon.es)
    # --------------------------------------------------
    print("\\n[1b/5] Scraping multi-market (Lidl + DIA + Consum + Amazon.es)...")
    all_market_prices = list(all_prices)  # começa com preços Mercadona

    lidl_scraper    = LidlScraper()
    dia_scraper     = DiaScraper()
    consum_scraper  = ConsumScraper()
    amazon_scraper  = AmazonEsScraper()

    for city_key in TARGET_CITIES:
        print(f"\\n  [{city_key.upper()}] outros mercados...")
        try:
            lidl_prices = lidl_scraper.scrape_city(city_key)
            all_market_prices.extend(lidl_prices)
        except Exception as e:
            print(f"  [Lidl/{city_key}] erro: {e}")

        try:
            dia_prices = dia_scraper.scrape_city(city_key)
            all_market_prices.extend(dia_prices)
        except Exception as e:
            print(f"  [DIA/{city_key}] erro: {e}")

        try:
            consum_prices = consum_scraper.scrape_city(city_key)
            all_market_prices.extend(consum_prices)
        except Exception as e:
            print(f"  [Consum/{city_key}] erro: {e}")

    # Amazon.es — suplementos (só 1x, mesmo preço para todas as cidades)
    print("\\n  [Amazon.es] suplementos...")
    try:
        amz_prices_base = amazon_scraper.scrape_city("granada")  # coleta 1x
        for city_key in TARGET_CITIES:
            for p in amz_prices_base:
                all_market_prices.append({**p, "city": city_key})
    except Exception as e:
        print(f"  [Amazon.es] erro: {e}")

    # Consolidado multi-market por cidade
    print("\\n  Calculando custo ótimo por cidade...")
    multi_market_data = {}
    for city_key in TARGET_CITIES:
        try:
            consolidado = consolidate_multi_market(all_market_prices, city_key)
            multi_market_data[city_key] = consolidado
            print(f"  [{city_key}] €{consolidado['total_mercadona']:.2f}/mês → "
                  f"€{consolidado['total_otimizado']:.2f}/mês "
                  f"(economia €{consolidado['total_economy']:.2f} = {consolidado['pct_saved']}%)")
        except Exception as e:
            print(f"  [{city_key}] erro consolidado: {e}")

    # Salvar multi_market.json para o claude_notion_sync
    multi_market_file = DATA_DIR / "multi_market.json"
    multi_market_file.write_text(
        json.dumps(multi_market_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"  ✓ multi_market.json salvo")

─── BLOCO 3: no latest.json snapshot (na seção de save), adicionar ──────────

    # Adicionar ao snapshot (após a seção existente de save):
    snapshot["multi_market"] = multi_market_data

─── BLOCO 4: no commit do GitHub Actions, adicionar data/multi_market.json ──

    # No step "Commit dashboard + data" do daily_scrape.yml:
    # git add docs/ data/latest.json data/multi_market.json
"""

# Este arquivo é documentação/guia — não executar diretamente.
# Os blocos acima devem ser integrados manualmente no main.py.

if __name__ == "__main__":
    print(__doc__)
