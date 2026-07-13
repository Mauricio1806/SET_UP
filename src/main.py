"""
SET_UP main orchestrator v2.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

from .config import (
    TARGET_CITIES, NOTION_TOKEN, NOTION_HUB_ID, DATA_DIR,
    SCRAPER_SETTINGS,
)
from .scrapers import HabitacliaScraper, PisosScraper, IdealistaScraper, MercadonaScraper
from .proximity import ProximityAnalyzer
from .ranking import rank_listings
from .notion_sync import NotionSync
from .dashboard import generate_dashboard


def main():
    print("=" * 60)
    print("SET_UP v2 — Spain Rental & Price Intelligence")
    print(f"Rodando: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # ---------------------------------------------------------
    # 1. SCRAPING ALUGUÉIS
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
        print(f"\n[{city_key.upper()}] teto €{max_price}")
        for scraper in scrapers:
            try:
                listings = scraper.scrape_city(
                    city_key, max_price=max_price,
                    max_pages=SCRAPER_SETTINGS["max_pages_per_source"],
                )
                all_listings.extend(listings)
            except Exception as e:
                print(f"  [ERRO] {scraper.__class__.__name__}: {e}")

    # Deduplicação global por URL
    seen = set()
    unique = []
    for l in all_listings:
        url = l.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(l)
    all_listings = unique

    seasonal = sum(1 for l in all_listings if l.get("is_seasonal"))
    print(f"\n  Total: {len(all_listings)} anúncios ({seasonal} sazonais filtrados no ranking)")

    if not all_listings:
        print("  [warn] Nenhum aluguel coletado.")
        return 1

    # ---------------------------------------------------------
    # 2. PROXIMIDADE
    # ---------------------------------------------------------
    print("\n[2/5] Análise de proximidade...")
    analyzer = ProximityAnalyzer()
    analyzed = []
    max_analyze = 80
    for i, listing in enumerate(all_listings[:max_analyze]):
        print(f"  {i+1}/{min(len(all_listings), max_analyze)}: "
              f"{listing.get('city','')} | {listing.get('title','')[:50]}")
        try:
            analyzed.append(analyzer.analyze_listing(listing))
        except Exception as e:
            print(f"    [ERRO] {e}")
            analyzed.append(listing)

    geocoded_ok = sum(1 for l in analyzed if l.get("_geocoded"))
    print(f"\n  Geocodificados: {geocoded_ok}/{len(analyzed)} ({geocoded_ok/max(len(analyzed),1)*100:.0f}%)")

    # ---------------------------------------------------------
    # 3. SCORING
    # ---------------------------------------------------------
    print("\n[3/5] Scoring e ranking...")
    ranked = rank_listings(analyzed)

    print("\nTop 5 aluguéis:")
    for i, l in enumerate(ranked[:5]):
        geo = "✓geo" if l.get("_geocoded") else "~est"
        sm = l.get("nearest_supermarket_m")
        gm = l.get("nearest_gym_m")
        sm_txt = f"🛒{sm}m" if sm else "🛒?"
        gm_txt = f"💪{gm}m" if gm else "💪?"
        alerts = " ".join(l.get("alerts", []))
        print(f"  #{i+1} [{l['scores']['total']:.0f}pt] {l.get('city')} "
              f"€{l.get('price')} {sm_txt} {gm_txt} {geo} {alerts}")

    # ---------------------------------------------------------
    # 4. MERCADONA
    # ---------------------------------------------------------
    print("\n[4/5] Scraping preços Mercadona (quinzenal)...")
    all_prices = []
    mercadona = MercadonaScraper()
    for city_key in TARGET_CITIES:
        try:
            prices = mercadona.scrape_city(city_key)
            all_prices.extend(prices)
        except Exception as e:
            print(f"  [ERRO] Mercadona {city_key}: {e}")

    cities_with_prices = len({p.get("city") for p in all_prices})
    print(f"  Total: {len(all_prices)} preços em {cities_with_prices} cidade(s)")

    # ---------------------------------------------------------
    # 5. SAVE + NOTION + DASHBOARD
    # ---------------------------------------------------------
    print("\n[5/5] Salvando + Notion + Dashboard...")

    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_scraped": len(all_listings),
            "total_seasonal_filtered": seasonal,
            "total_analyzed": len(analyzed),
            "geocoded_ok": geocoded_ok,
            "total_ranked": len(ranked),
            "total_prices": len(all_prices),
        },
        "listings": ranked,
        "prices": all_prices,
    }

    (DATA_DIR / f"snapshot_{now_str}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ snapshot_{now_str}.json salvo")

    # Notion
    notion_token = os.getenv("NOTION_TOKEN", NOTION_TOKEN)
    if notion_token:
        try:
            sync = NotionSync(notion_token, NOTION_HUB_ID)
            sync.sync_all(ranked, all_prices)
            print("  ✓ Notion sincronizado")
        except Exception as e:
            print(f"  [ERRO Notion] {e}")
    else:
        print("  [skip] NOTION_TOKEN não configurado")

    # Dashboard
    try:
        generate_dashboard(ranked, all_prices)
    except Exception as e:
        print(f"  [ERRO dashboard] {e}")

    print("\n" + "=" * 60)
    print(f"✅ SET_UP v2 concluído")
    print(f"   Aluguéis rankeados : {len(ranked)}")
    print(f"   Geocodificados     : {geocoded_ok}/{len(analyzed)}")
    print(f"   Preços Mercadona   : {len(all_prices)}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
