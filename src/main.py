"""
SET_UP main orchestrator v3.
"""

import json, os, sys
from datetime import datetime, timezone
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

from .config import TARGET_CITIES, NOTION_TOKEN, NOTION_HUB_ID, DATA_DIR, SCRAPER_SETTINGS
from .scrapers import (HabitacliaScraper, PisosScraper, IdealistaScraper,
                       FotocasaScraper, MercadonaScraper, build_shopping_consolidado)
from .proximity import ProximityAnalyzer
from .ranking import rank_listings
from .notion_sync import NotionSync
from .dashboard import generate_dashboard
from .dashboard.generate import _shopping_section


def main():
    print("=" * 60)
    print("SET_UP v3 — Spain Rental & Price Intelligence")
    print(f"Rodando: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # --------------------------------------------------
    # 1. SCRAPING ALUGUÉIS
    # --------------------------------------------------
    print("\n[1/5] Scraping aluguéis...")
    all_listings = []

    # Ordem de prioridade: Idealista (API) > Fotocasa > Habitaclia > Pisos
    scrapers = [
        IdealistaScraper(),
        FotocasaScraper(delay_range=(3.0, 6.0)),
        HabitacliaScraper(delay_range=(SCRAPER_SETTINGS["delay_min"], SCRAPER_SETTINGS["delay_max"])),
        PisosScraper(delay_range=(SCRAPER_SETTINGS["delay_min"], SCRAPER_SETTINGS["delay_max"])),
    ]

    for city_key, city_config in TARGET_CITIES.items():
        max_price = city_config["max_rent_eur"]
        print(f"\n[{city_key.upper()}] teto €{max_price}")
        for scraper in scrapers:
            try:
                listings = scraper.scrape_city(city_key, max_price=max_price,
                                               max_pages=SCRAPER_SETTINGS["max_pages_per_source"])
                all_listings.extend(listings)
            except Exception as e:
                print(f"  [ERRO] {scraper.__class__.__name__}: {e}")

    # Deduplicação global por URL
    seen, unique = set(), []
    for l in all_listings:
        u = l.get("url", "")
        if u and u not in seen:
            seen.add(u); unique.append(l)
    all_listings = unique

    by_source = {}
    for l in all_listings:
        s = l.get("source", "?")
        by_source[s] = by_source.get(s, 0) + 1
    print(f"\n  Total único: {len(all_listings)}")
    for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"    {src}: {cnt}")

    if not all_listings:
        print("  [warn] Nenhum aluguel coletado.")
        return 1

    # --------------------------------------------------
    # 2. PROXIMIDADE
    # --------------------------------------------------
    print("\n[2/5] Análise de proximidade...")
    analyzer = ProximityAnalyzer()
    analyzed, max_an = [], 15
    for i, listing in enumerate(all_listings[:max_an]):
        print(f"  {i+1}/{min(len(all_listings), max_an)}: "
              f"{listing.get('city','')} | {listing.get('title','')[:50]}")
        try:
            analyzed.append(analyzer.analyze_listing(listing))
        except Exception as e:
            print(f"    [ERRO] {e}"); analyzed.append(listing)

    geocoded_ok = sum(1 for l in analyzed if l.get("_geocoded"))
    print(f"\n  Geocodificados: {geocoded_ok}/{len(analyzed)}")

    # --------------------------------------------------
    # 3. SCORING
    # --------------------------------------------------
    print("\n[3/5] Scoring...")
    ranked = rank_listings(analyzed)
    for i, l in enumerate(ranked[:5]):
        sm = l.get("nearest_supermarket_m")
        gm = l.get("nearest_gym_m")
        print(f"  #{i+1} [{l['scores']['total']:.0f}pt] "
              f"{l.get('city')} €{l.get('price')} "
              f"🛒{sm}m 💪{gm}m "
              f"{'✓geo' if l.get('_geocoded') else '~est'} "
              f"{' '.join(l.get('alerts',[]))}")

    # --------------------------------------------------
    # 4. MERCADONA + CONSOLIDADO
    # --------------------------------------------------
    print("\n[4/5] Preços Mercadona + consolidado de compras...")
    all_prices = []
    consolidados = []
    mercadona = MercadonaScraper()

    for city_key in TARGET_CITIES:
        try:
            prices = mercadona.scrape_city(city_key)
            all_prices.extend(prices)
            # Monta consolidado com mix de mercados
            consolidado = build_shopping_consolidado(prices, city_key)
            consolidados.append(consolidado)
            print(f"    {city_key}: total Mercadona €{consolidado['total_mercadona']:.2f} "
                  f"→ otimizado €{consolidado['total_otimizado']:.2f} "
                  f"(economia €{consolidado['total_economy']:.2f})")
        except Exception as e:
            print(f"  [ERRO] Mercadona {city_key}: {e}")

    # --------------------------------------------------
    # 5. SAVE + NOTION + DASHBOARD
    # --------------------------------------------------
    print("\n[5/5] Salvando + Notion + Dashboard...")
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_scraped": len(all_listings), "total_ranked": len(ranked),
            "geocoded_ok": geocoded_ok, "total_prices": len(all_prices),
            "by_source": by_source,
        },
        "listings": ranked,
        "prices": all_prices,
        "consolidados": consolidados,
    }

    (DATA_DIR / f"snapshot_{now_str}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ snapshot_{now_str}.json")

    # Notion
    notion_token = os.getenv("NOTION_TOKEN", NOTION_TOKEN)
    if notion_token:
        try:
            NotionSync(notion_token, NOTION_HUB_ID).sync_all(ranked, all_prices)
            print("  ✓ Notion sincronizado")
        except Exception as e:
            print(f"  [ERRO Notion] {e}")
    else:
        print("  [skip] NOTION_TOKEN não configurado")

    # Dashboard
    try:
        generate_dashboard(ranked, all_prices, consolidados)
    except Exception as e:
        print(f"  [ERRO dashboard] {e}")

    print("\n" + "=" * 60)
    print(f"✅ SET_UP v3 concluído")
    print(f"   Aluguéis rankeados : {len(ranked)}")
    print(f"   Preços Mercadona   : {len(all_prices)}")
    print(f"   Consolidados       : {len(consolidados)} cidades")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
