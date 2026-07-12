"""
SET_UP main orchestrator.
Roda: scraping → proximity → scoring → notion sync → dashboard.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from .config import (
    TARGET_CITIES, NOTION_TOKEN, NOTION_HUB_ID, DATA_DIR,
    SCRAPER_SETTINGS,
)
from .scrapers import (
    HabitacliaScraper, PisosScraper, IdealistaScraper, MercadonaScraper,
)
from .proximity import ProximityAnalyzer
from .ranking import rank_listings
from .notion_sync import NotionSync
from .dashboard import generate_dashboard


def main():
    print("=" * 60)
    print("SET_UP — Spain Rental & Price Scraper")
    print(f"Iniciado em: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # ---------------------------------------------------------
    # 1. SCRAPING de aluguéis
    # ---------------------------------------------------------
    print("\n[1/5] Scraping aluguéis...")
    all_listings = []
    scrapers = [
        HabitacliaScraper(delay_range=(SCRAPER_SETTINGS["delay_min"], SCRAPER_SETTINGS["delay_max"])),
        PisosScraper(delay_range=(SCRAPER_SETTINGS["delay_min"], SCRAPER_SETTINGS["delay_max"])),
        IdealistaScraper(),
    ]

    for city_key, city_config in TARGET_CITIES.items():
        max_price = city_config["max_rent_eur"]
        print(f"\n[{city_key.upper()}] max €{max_price}")
        for scraper in scrapers:
            try:
                listings = scraper.scrape_city(
                    city_key, max_price=max_price,
                    max_pages=SCRAPER_SETTINGS["max_pages_per_source"],
                )
                all_listings.extend(listings)
            except Exception as e:
                print(f"  [ERRO] {scraper.__class__.__name__}: {e.__class__.__name__}")

    print(f"\n  Total: {len(all_listings)} aluguéis coletados")

    if not all_listings:
        print("\n[warn] Nenhum aluguel coletado. Encerrando.")
        return 1

    # ---------------------------------------------------------
    # 2. Análise de proximidade (POIs)
    # ---------------------------------------------------------
    print("\n[2/5] Análise de proximidade (Overpass API)...")
    analyzer = ProximityAnalyzer()
    analyzed = []
    max_to_analyze = 60  # limita para não estourar rate limit
    for i, listing in enumerate(all_listings[:max_to_analyze]):
        print(f"  {i+1}/{min(len(all_listings), max_to_analyze)}: {listing.get('title', '')[:60]}")
        try:
            analyzed.append(analyzer.analyze_listing(listing))
        except Exception as e:
            print(f"    [ERRO] {e}")
            analyzed.append(listing)

    # ---------------------------------------------------------
    # 3. Scoring / ranking
    # ---------------------------------------------------------
    print("\n[3/5] Scoring...")
    ranked = rank_listings(analyzed)
    for i, l in enumerate(ranked[:5]):
        print(f"  #{i+1} [{l.get('scores', {}).get('total', 0):.0f}pt] "
              f"{l.get('city')} €{l.get('price')} — {l.get('title', '')[:50]}")

    # ---------------------------------------------------------
    # 4. Scraping preços (Mercadona)
    # ---------------------------------------------------------
    print("\n[4/5] Scraping preços Mercadona...")
    all_prices = []
    mercadona = MercadonaScraper()
    for city_key in TARGET_CITIES.keys():
        try:
            prices = mercadona.scrape_city(city_key)
            all_prices.extend(prices)
        except Exception as e:
            print(f"  [ERRO] Mercadona {city_key}: {e}")

    print(f"  Total: {len(all_prices)} preços")

    # ---------------------------------------------------------
    # 5. Save data + Notion sync + Dashboard
    # ---------------------------------------------------------
    print("\n[5/5] Salvando + Notion + Dashboard...")

    snapshot_file = DATA_DIR / f"snapshot_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.json"
    latest_file = DATA_DIR / "latest.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_listings": len(ranked),
        "total_prices": len(all_prices),
        "listings": ranked,
        "prices": all_prices,
    }
    for f in [snapshot_file, latest_file]:
        f.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ Snapshot salvo em {snapshot_file.name}")

    # Notion sync (idempotente — só adiciona, não deleta)
    if NOTION_TOKEN:
        print("  → Sincronizando Notion...")
        try:
            sync = NotionSync(NOTION_TOKEN, NOTION_HUB_ID)
            sync.sync_all(ranked, all_prices)
        except Exception as e:
            print(f"  [ERRO Notion] {e}")
    else:
        print("  [skip] NOTION_TOKEN não configurado")

    # Dashboard HTML
    try:
        generate_dashboard(ranked, all_prices)
    except Exception as e:
        print(f"  [ERRO dashboard] {e}")

    print("\n" + "=" * 60)
    print("✓ SET_UP concluído com sucesso")
    print(f"  Aluguéis: {len(ranked)}")
    print(f"  Preços: {len(all_prices)}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
