"""
SET_UP main orchestrator v4.
"""

import sys
import os
# Windows UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Carrega .env ANTES de qualquer outro import — garante que os valores
# estão em os.environ quando config.py e outros módulos forem importados
from pathlib import Path
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_path, override=True)

import json, time
from datetime import datetime, timezone

from .config import TARGET_CITIES, NOTION_TOKEN, NOTION_HUB_ID, DATA_DIR, SCRAPER_SETTINGS
from .scrapers import (HabitacliaScraper, PisosScraper, IdealistaScraper,
                       FotocasaScraper, MercadonaScraper, build_shopping_consolidado)
from .proximity import ProximityAnalyzer
from .ranking import rank_listings
from .notion_sync import NotionSync
from .notion_sync.diet_sync import DietSyncNotion
from .notion_sync.city_sync import CitySyncNotion
from .dashboard import generate_dashboard


def main():
    print("=" * 60)
    print("SET_UP v4 — Spain Rental & Price Intelligence")
    print(f"Rodando: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # --------------------------------------------------
    # 1. SCRAPING
    # --------------------------------------------------
    print("\n[1/5] Scraping aluguéis...")
    all_listings = []
    scrapers = [
        IdealistaScraper(),
        FotocasaScraper(),
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
    analyzed = []
    max_an = 80
    consecutive_slow = 0

    for i, listing in enumerate(all_listings[:max_an]):
        print(f"  {i+1}/{min(len(all_listings), max_an)}: "
              f"{listing.get('city','')} | {listing.get('title','')[:50]}")
        t0 = time.time()
        try:
            analyzed.append(analyzer.analyze_listing(listing))
        except Exception as e:
            print(f"    [ERRO] {e}")
            analyzed.append(listing)

        elapsed = time.time() - t0
        # Só conta como lento se demorou E não tem cache
        if elapsed > 25 and not listing.get("_geocoded"):
            consecutive_slow += 1
            if consecutive_slow >= 5:
                print(f"  [Overpass instável] parando proximidade — {len(analyzed)} analisados")
                analyzed.extend(all_listings[len(analyzed):max_an])
                break
        else:
            consecutive_slow = 0  # reset quando funciona

    geocoded_ok = sum(1 for l in analyzed if l.get("_geocoded"))
    print(f"\n  Geocodificados: {geocoded_ok}/{len(analyzed)}")

    # --------------------------------------------------
    # 3. SCORING
    # --------------------------------------------------
    print("\n[3/5] Scoring...")
    ranked = rank_listings(analyzed)

    print("\nTop 5 aluguéis:")
    for i, l in enumerate(ranked[:5]):
        sm = l.get("nearest_supermarket_m")
        gm = l.get("nearest_gym_m")
        sm_txt = f"{sm}m" if sm else "?"
        gm_txt = f"{gm}m" if gm else "?"
        print(f"  #{i+1} [{l['scores']['total']:.0f}pt] {l.get('city')} "
              f"€{l.get('price')} 🛒{sm_txt} 💪{gm_txt} "
              f"{'✓geo' if l.get('_geocoded') else '~est'} "
              f"{' '.join(l.get('alerts', []))}")

    # --------------------------------------------------
    # 4. MERCADONA + CONSOLIDADO
    # --------------------------------------------------
    print("\n[4/5] Preços Mercadona...")
    all_prices, consolidados = [], []
    mercadona = MercadonaScraper()
    for city_key in TARGET_CITIES:
        try:
            prices = mercadona.scrape_city(city_key)
            all_prices.extend(prices)
            c = build_shopping_consolidado(prices, city_key)
            consolidados.append(c)
            print(f"    {city_key}: Mercadona €{c['total_mercadona']:.2f} "
                  f"→ otimizado €{c['total_otimizado']:.2f} "
                  f"(economia €{c['total_economy']:.2f})")
        except Exception as e:
            print(f"  [ERRO] {city_key}: {e}")

    # --------------------------------------------------
    # 5. SAVE + NOTION + DASHBOARD
    # --------------------------------------------------
    print("\n[5/5] Salvando + Notion + Dashboard...")
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_scraped": len(all_listings),
            "total_ranked": len(ranked),
            "geocoded_ok": geocoded_ok,
            "total_prices": len(all_prices),
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
    notion_token = os.getenv("NOTION_TOKEN", "").strip()
    if not notion_token:
        print("  [skip] NOTION_TOKEN não configurado no .env")
    else:
        try:
            # Calcula custo real da dieta por cidade
            diet_sync = DietSyncNotion(notion_token, NOTION_HUB_ID)
            diet_costs = {}
            for city_key in TARGET_CITIES:
                city_prices = [p for p in all_prices if p.get("city") == city_key]
                if city_prices:
                    dc = diet_sync.calculate_diet_cost(city_prices, city_key)
                    diet_costs[city_key] = dc
                    print(f"  ✓ Dieta {city_key}: €{dc['total']:.2f}/mês")

            # Atualiza páginas de cidade com bloco LIVE
            city_sync = CitySyncNotion(notion_token)
            city_sync.update_all_cities(ranked, all_prices, diet_costs)
            print("  ✓ Páginas de cidade atualizadas no Notion")
        except Exception as e:
            print(f"  [ERRO Notion] {e}")

    # Dashboard
    try:
        generate_dashboard(ranked, all_prices, consolidados)
    except Exception as e:
        print(f"  [ERRO dashboard] {e}")

    print("\n" + "=" * 60)
    print(f"✅ SET_UP v4 concluído")
    print(f"   Aluguéis rankeados : {len(ranked)}")
    print(f"   Geocodificados     : {geocoded_ok}/{len(analyzed)}")
    print(f"   Preços Mercadona   : {len(all_prices)}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
