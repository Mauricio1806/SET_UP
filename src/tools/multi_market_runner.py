"""
multi_market_runner.py — scraper standalone para Lidl + DIA + Consum + Amazon.es.

Roda após src.main (que já coletou Mercadona).
Lê data/latest.json para pegar preços Mercadona base.
Escreve data/multi_market.json com consolidado.

Uso:
  python -m src.tools.multi_market_runner
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Resolve path sem depender de src.config
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data"

# Imports relativos
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from src.scrapers.lidl        import LidlScraper
from src.scrapers.dia         import DiaScraper
from src.scrapers.consum      import ConsumScraper
from src.scrapers.amazon_es   import AmazonEsScraper
from src.scrapers.multi_market import consolidate_multi_market, build_market_summary_text

TARGET_CITIES = ["granada", "alicante", "nerja"]


def load_mercadona_prices() -> list:
    """Pega preços Mercadona do último snapshot."""
    f = DATA_DIR / "latest.json"
    if not f.exists():
        print("[warn] latest.json não encontrado — multi-market sem base Mercadona")
        return []
    data = json.loads(f.read_text(encoding="utf-8"))
    prices = data.get("prices", [])
    # Garantir market=Mercadona nos preços existentes
    for p in prices:
        if "market" not in p:
            p["market"] = "Mercadona"
    return prices


def main():
    print("=" * 55)
    print("SET_UP Multi-Market Runner")
    print(f"Rodando: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    all_prices = load_mercadona_prices()
    print(f"\nBase Mercadona: {len(all_prices)} preços carregados")

    lidl_scraper   = LidlScraper()
    dia_scraper    = DiaScraper()
    consum_scraper = ConsumScraper()
    amazon_scraper = AmazonEsScraper()

    # Scraping Lidl + DIA + Consum por cidade
    for city_key in TARGET_CITIES:
        print(f"\n[{city_key.upper()}]")

        try:
            print("  Lidl...")
            lidl_prices = lidl_scraper.scrape_city(city_key)
            all_prices.extend(lidl_prices)
            time.sleep(2)
        except Exception as e:
            print(f"  [Lidl/{city_key}] erro: {e}")

        try:
            print("  DIA...")
            dia_prices = dia_scraper.scrape_city(city_key)
            all_prices.extend(dia_prices)
            time.sleep(2)
        except Exception as e:
            print(f"  [DIA/{city_key}] erro: {e}")

        try:
            print("  Consum...")
            consum_prices = consum_scraper.scrape_city(city_key)
            all_prices.extend(consum_prices)
            time.sleep(2)
        except Exception as e:
            print(f"  [Consum/{city_key}] erro: {e}")

    # Amazon.es — suplementos (1x, replicar para todas as cidades)
    print("\n[AMAZON.ES] suplementos...")
    try:
        amz_base = amazon_scraper.scrape_city("granada")
        for city_key in TARGET_CITIES:
            if city_key != "granada":
                for p in amz_base:
                    all_prices.append({**p, "city": city_key})
            else:
                all_prices.extend(amz_base)
        print(f"  Amazon.es: {len(amz_base)} produtos coletados")
    except Exception as e:
        print(f"  [Amazon.es] erro: {e}")

    # Consolidado por cidade
    print("\n[CONSOLIDADO]")
    multi_market_data = {}
    for city_key in TARGET_CITIES:
        try:
            consolidado = consolidate_multi_market(all_prices, city_key)
            multi_market_data[city_key] = consolidado
            print(f"  {city_key}: Mercadona €{consolidado['total_mercadona']:.2f} "
                  f"→ Mix €{consolidado['total_otimizado']:.2f} "
                  f"(economia €{consolidado['total_economy']:.2f}/mês, {consolidado['pct_saved']}%)")
            print(f"    Por mercado: " + " | ".join(
                f"{m}:€{v:.0f}" for m, v in
                sorted(consolidado["by_market"].items(), key=lambda x: -x[1])
            ))
        except Exception as e:
            print(f"  [{city_key}] erro consolidado: {e}")

    # Salvar
    out_file = DATA_DIR / "multi_market.json"
    out_file.write_text(
        json.dumps(multi_market_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n✓ multi_market.json salvo → {out_file}")


if __name__ == "__main__":
    main()
