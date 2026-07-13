"""
Dashboard Generator v2 — cards com minutos a pé, alertas, filtros de cidade,
tabela de preços com tracking quinzenal e variação de preços.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

from ..config import DOCS_DIR, TARGET_CITIES, DASHBOARD_TITLE


def generate_dashboard(listings: List[Dict], prices: List[Dict]):
    DOCS_DIR.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    (DOCS_DIR / "data.json").write_text(
        json.dumps({
            "generated_at": now,
            "listings": listings[:100],
            "prices": prices,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    listings_by_city = {c: [] for c in TARGET_CITIES}
    for l in listings:
        c = l.get("city", "granada")
        if c in listings_by_city:
            listings_by_city[c].append(l)

    html = _build_html(listings_by_city, prices, now)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ Dashboard v2 gerado em {DOCS_DIR}")


def _build_html(listings_by_city, prices, generated_at):
    total = sum(len(v) for v in listings_by_city.values())
    geocoded = sum(1 for v in listings_by_city.values()
                   for l in v if l.get("_geocoded"))

    city_sections = ""
    for city_key, items in listings_by_city.items():
        city_name = TARGET_CITIES[city_key]["name"]
        city_sections += _city_section(city_key, city_name, items)

    price_section = _prices_section(prices)

    return f"""<!doctype html>
<html lang='pt-BR'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width,initial-scale=1'>
  <title>{DASHBOARD_TITLE}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#080d20;color:#e2e8f0;padding:20px}}
    .wrap{{max-width:1280px;margin:0 auto}}
    header{{background:linear-gradient(135deg,#1e40af,#6d28d9);
            padding:28px;border-radius:14px;margin-bottom:24px}}
    h1{{font-size:1.8rem;margin-bottom:6px}}
    header p{{opacity:.85;margin-bottom:14px}}
    .stats{{display:flex;gap:16px;flex-wrap:wrap}}
    .stat{{background:rgba(255,255,255,.12);padding:12px 18px;border-radius:10px;min-width:130px}}
    .stat strong{{font-size:1.4rem;display:block}}
    .stat small{{opacity:.8;font-size:.8rem}}
    nav{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}}
    nav a{{color:#a5b4fc;text-decoration:none;padding:8px 16px;
           border-radius:8px;background:#1e293b;font-size:.9rem}}
    nav a:hover{{background:#334155}}
    .city-section{{margin-bottom:40px}}
    h2{{font-size:1.35rem;margin:28px 0 14px;color:#a5b4fc;
        display:flex;align-items:center;gap:10px}}
    .cnt{{background:#6d28d9;color:#fff;padding:2px 10px;
          border-radius:12px;font-size:.85rem}}
    .cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
    .card{{background:#1e293b;border-radius:12px;padding:18px;
           border-left:4px solid #475569;transition:border-color .2s}}
    .card.S{{border-left-color:#10b981}}
    .card.A{{border-left-color:#3b82f6}}
    .card.B{{border-left-color:#eab308}}
    .card.C{{border-left-color:#f97316}}
    .card.D{{border-left-color:#ef4444}}
    .card-title{{font-size:.95rem;font-weight:600;margin-bottom:8px;line-height:1.3}}
    .card-title a{{color:#f1f5f9;text-decoration:none}}
    .card-title a:hover{{color:#a5b4fc}}
    .price{{font-size:1.5rem;font-weight:700;color:#10b981;margin:6px 0}}
    .price small{{font-size:.65em;opacity:.7}}
    .meta{{display:flex;gap:10px;font-size:.8rem;opacity:.75;flex-wrap:wrap;margin:6px 0}}
    .badges{{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}}
    .badge{{padding:3px 9px;border-radius:10px;font-size:.75rem;background:#334155}}
    .badge.green{{background:#065f46;color:#6ee7b7}}
    .badge.orange{{background:#7c2d12;color:#fdba74}}
    .badge.blue{{background:#1e3a8a;color:#93c5fd}}
    .badge.purple{{background:#4c1d95;color:#c4b5fd}}
    .badge.red{{background:#7f1d1d;color:#fca5a5}}
    .no-geocode{{opacity:.6;font-size:.75rem;color:#fb923c}}
    /* Preços */
    .price-section{{margin-top:40px}}
    .city-tabs{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}}
    .city-tab{{padding:6px 14px;border-radius:8px;background:#1e293b;
               border:1px solid #334155;cursor:pointer;font-size:.85rem}}
    .city-tab.active,.city-tab:hover{{background:#6d28d9;border-color:#6d28d9}}
    .price-table{{background:#1e293b;border-radius:12px;overflow:auto;width:100%}}
    table{{width:100%;border-collapse:collapse;font-size:.88rem}}
    th{{background:#0f172a;padding:10px 14px;text-align:left;
        color:#94a3b8;font-weight:600;white-space:nowrap}}
    td{{padding:10px 14px;border-bottom:1px solid #334155}}
    tr:last-child td{{border-bottom:none}}
    .p-price{{font-weight:700;color:#10b981}}
    .trend-up{{color:#ef4444}}
    .trend-down{{color:#10b981}}
    .trend-stable{{color:#94a3b8}}
    footer{{text-align:center;padding:24px;opacity:.5;font-size:.82rem;margin-top:40px}}
  </style>
</head>
<body>
<div class='wrap'>
  <header>
    <h1>{DASHBOARD_TITLE}</h1>
    <p>Scraping diário · Scoring por preço + distância real a pé + marcas</p>
    <div class='stats'>
      <div class='stat'><strong>{total}</strong><small>Aluguéis</small></div>
      <div class='stat'><strong>{geocoded}</strong><small>Com distância real</small></div>
      <div class='stat'><strong>{len(prices)}</strong><small>Preços Mercadona</small></div>
      <div class='stat'><strong>{generated_at}</strong><small>Atualizado</small></div>
    </div>
  </header>
  <nav>
    <a href='#granada'>🏘️ Granada</a>
    <a href='#alicante'>🏙️ Alicante</a>
    <a href='#nerja'>🏖️ Nerja</a>
    <a href='#prices'>🛒 Preços</a>
    <a href='data.json' target='_blank'>📥 JSON</a>
  </nav>
  {city_sections}
  {price_section}
  <footer>
    SET_UP · Dados: OpenStreetMap, Habitaclia, Pisos.com, Idealista, Mercadona
    · <a href='https://github.com/Mauricio1806/SET_UP' style='color:#a5b4fc'>GitHub</a>
  </footer>
</div>
</body></html>"""


def _city_section(city_key, city_name, items):
    s_count = len(items)
    cards = "".join(_card(l) for l in items[:24])
    empty = "<p style='opacity:.5'>Nenhum anúncio coletado ainda.</p>" if not cards else ""
    return f"""
    <section class='city-section' id='{city_key}'>
      <h2>{'🏘️' if city_key=='granada' else '🏙️' if city_key=='alicante' else '🏖️'} {city_name}
        <span class='cnt'>{s_count}</span>
      </h2>
      <div class='cards'>{cards}{empty}</div>
    </section>"""


def _card(l):
    grade = (l.get("grade") or "D")[0]
    scores = l.get("scores", {})
    total_score = scores.get("total", 0)

    # Badges de POI
    badges = ""
    sm = l.get("nearest_supermarket_m")
    sm_min = l.get("nearest_supermarket_walk_min")
    gm = l.get("nearest_gym_m")
    gm_min = l.get("nearest_gym_walk_min")
    sm_name = l.get("nearest_supermarket_name", "")
    gm_name = l.get("nearest_gym_name", "")

    if sm is not None:
        txt = f"🛒 {sm}m · {sm_min}min" + (f" · {_esc(sm_name)}" if sm_name else "")
        badges += f"<span class='badge blue'>{txt}</span>"
    if gm is not None:
        txt = f"💪 {gm}m · {gm_min}min" + (f" · {_esc(gm_name)}" if gm_name else "")
        badges += f"<span class='badge purple'>{txt}</span>"

    # Marcas prioritárias
    brands = sorted({
        p.get("priority_brand")
        for pois in l.get("pois", {}).values()
        for p in pois if p.get("priority_brand")
    })
    for b in brands[:3]:
        badges += f"<span class='badge green'>{_esc(b)}</span>"

    # Alertas
    for alert in l.get("alerts", []):
        color = "red" if "Só cooktop" in alert or "Sazonal" in alert else "orange"
        badges += f"<span class='badge {color}'>{_esc(alert)}</span>"

    # Geocoding warning
    geocode_warn = ""
    if not l.get("_geocoded"):
        geocode_warn = "<div class='no-geocode'>⚠️ Distâncias estimadas (endereço não geocodificado)</div>"

    # Localização
    loc = _esc(l.get("location") or l.get("location_raw") or "")

    url = l.get("url", "#")
    title = _esc((l.get("title") or "Sem título")[:70])
    price = l.get("price", "?")

    meta = ""
    if l.get("rooms"):
        meta += f"<span>🛏️ {l['rooms']}q</span>"
    if l.get("m2"):
        meta += f"<span>📐 {l['m2']}m²</span>"
    meta += f"<span>⭐ {total_score:.0f}pt</span>"
    meta += f"<span>{_esc(l.get('grade',''))}</span>"
    if l.get("source"):
        meta += f"<span>🔗 {l['source']}</span>"

    return f"""
    <div class='card {grade}'>
      <div class='card-title'><a href='{url}' target='_blank' rel='noopener'>{title}</a></div>
      {f"<div style='font-size:.78rem;opacity:.6;margin-bottom:4px'>📍 {loc}</div>" if loc else ""}
      <div class='price'>€{price}<small>/mês</small></div>
      <div class='meta'>{meta}</div>
      {geocode_warn}
      <div class='badges'>{badges}</div>
    </div>"""


def _prices_section(prices):
    if not prices:
        return ""

    # Agrupa por cidade
    cities = sorted({p.get("city", "granada") for p in prices})

    # Tabelas por cidade
    tables = ""
    for city in cities:
        city_prices = [p for p in prices if p.get("city") == city]
        city_name = TARGET_CITIES.get(city, {}).get("name", city.capitalize())
        tables += f"<h3 style='margin:20px 0 10px;color:#a5b4fc'>🏷️ {city_name}</h3>"
        tables += "<div class='price-table'><table>"
        tables += "<thead><tr><th>Produto</th><th>Marca</th><th>Preço</th><th>Unidade</th><th>Variação 15d</th></tr></thead><tbody>"

        for p in city_prices:
            trend_html = ""
            change = p.get("price_change_pct")
            trend = p.get("price_trend", "")
            if change is not None:
                cls = "trend-up" if change > 0 else "trend-down" if change < 0 else "trend-stable"
                sign = "+" if change > 0 else ""
                trend_html = f"<span class='{cls}'>{trend} {sign}{change}%</span>"
                if p.get("prev_price"):
                    trend_html += f" <small style='opacity:.6'>era €{p['prev_price']}</small>"
            else:
                trend_html = "<span class='trend-stable'>—</span>"

            tables += (
                f"<tr>"
                f"<td>{_esc(p.get('product_name',''))}</td>"
                f"<td>{_esc(p.get('brand',''))}</td>"
                f"<td class='p-price'>€{p.get('price_eur','-')}</td>"
                f"<td style='opacity:.7'>{_esc(p.get('unit',''))}</td>"
                f"<td>{trend_html}</td>"
                f"</tr>"
            )
        tables += "</tbody></table></div>"

    return f"<section class='price-section' id='prices'><h2>🛒 Preços Mercadona</h2>{tables}</section>"


def _esc(t):
    if t is None: return ""
    return (str(t).replace("&","&amp;").replace("<","&lt;")
            .replace(">","&gt;").replace('"',"&quot;"))
