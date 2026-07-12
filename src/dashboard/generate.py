"""
Dashboard Generator — gera HTML estático em docs/ para GitHub Pages.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

from ..config import DOCS_DIR, TARGET_CITIES, DASHBOARD_TITLE, DASHBOARD_SUBTITLE


def generate_dashboard(listings: List[Dict], prices: List[Dict]):
    """Gera index.html + data.json em docs/"""
    DOCS_DIR.mkdir(exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Salva JSON pra debug/download
    (DOCS_DIR / "data.json").write_text(
        json.dumps({
            "generated_at": now,
            "listings": listings[:100],
            "prices": prices,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Gera HTML
    listings_by_city = {city: [] for city in TARGET_CITIES.keys()}
    for l in listings:
        c = l.get("city", "granada")
        if c in listings_by_city:
            listings_by_city[c].append(l)

    html = _build_html(listings_by_city, prices, now)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ Dashboard gerado em {DOCS_DIR}")


def _build_html(listings_by_city, prices, generated_at):
    total_listings = sum(len(v) for v in listings_by_city.values())
    price_count = len(prices)

    cards_html = ""
    for city_key, items in listings_by_city.items():
        city_name = TARGET_CITIES[city_key]["name"]
        cards_html += f"""
        <section class='city-section' id='{city_key}'>
          <h2>🏘️ {city_name} <span class='count'>{len(items)}</span></h2>
          <div class='cards'>
        """
        for item in items[:20]:
            cards_html += _card_html(item)
        cards_html += "</div></section>"

    prices_html = ""
    if prices:
        prices_html = "<section class='price-section'><h2>🛒 Preços Mercadona</h2><table><thead><tr>"
        prices_html += "<th>Produto</th><th>Marca</th><th>Cidade</th><th>Preço</th></tr></thead><tbody>"
        for p in prices[:50]:
            price_str = f"€{p.get('price_eur', '-')}"
            prices_html += (
                f"<tr><td>{_esc(p.get('product_name', '-'))}</td>"
                f"<td>{_esc(p.get('brand', '-'))}</td>"
                f"<td>{p.get('city', '-').capitalize()}</td>"
                f"<td class='price'>{price_str}</td></tr>"
            )
        prices_html += "</tbody></table></section>"

    return f"""<!doctype html>
<html lang='pt-BR'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>{DASHBOARD_TITLE}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0a0e27; color: #e4e6f0; line-height: 1.5; padding: 20px;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    header {{
      background: linear-gradient(135deg, #1e3a8a, #7c3aed);
      padding: 30px; border-radius: 12px; margin-bottom: 24px;
    }}
    h1 {{ font-size: 2rem; margin-bottom: 8px; }}
    header p {{ opacity: 0.9; margin-bottom: 12px; }}
    .stats {{ display: flex; gap: 24px; flex-wrap: wrap; margin-top: 16px; }}
    .stat {{ background: rgba(255,255,255,0.1); padding: 12px 20px; border-radius: 8px; }}
    .stat strong {{ font-size: 1.5rem; display: block; }}
    nav {{ margin: 24px 0; }}
    nav a {{
      color: #a5b4fc; text-decoration: none; margin-right: 16px;
      padding: 8px 16px; border-radius: 6px; background: #1e293b;
    }}
    nav a:hover {{ background: #334155; }}
    h2 {{ font-size: 1.5rem; margin: 32px 0 16px 0; color: #a5b4fc; }}
    .count {{
      background: #7c3aed; color: white; padding: 2px 10px;
      border-radius: 12px; font-size: 0.9rem; margin-left: 8px;
    }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }}
    .card {{
      background: #1e293b; border-radius: 12px; padding: 20px;
      border-left: 4px solid #64748b;
    }}
    .card.grade-S {{ border-left-color: #10b981; }}
    .card.grade-A {{ border-left-color: #3b82f6; }}
    .card.grade-B {{ border-left-color: #eab308; }}
    .card.grade-C {{ border-left-color: #f97316; }}
    .card.grade-D {{ border-left-color: #ef4444; }}
    .card h3 {{ font-size: 1rem; margin-bottom: 8px; }}
    .card h3 a {{ color: #f0f0f8; text-decoration: none; }}
    .card h3 a:hover {{ color: #a5b4fc; }}
    .price {{ font-size: 1.5rem; font-weight: bold; color: #10b981; margin: 8px 0; }}
    .meta {{ display: flex; gap: 12px; font-size: 0.85rem; opacity: 0.75; flex-wrap: wrap; }}
    .badges {{ margin-top: 12px; display: flex; gap: 6px; flex-wrap: wrap; }}
    .badge {{
      background: #334155; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem;
    }}
    .badge.priority {{ background: #7c3aed; color: white; }}
    table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }}
    th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #334155; }}
    th {{ background: #0f172a; }}
    td.price {{ font-weight: bold; color: #10b981; }}
    footer {{ text-align: center; padding: 24px; opacity: 0.6; margin-top: 40px; font-size: 0.85rem; }}
  </style>
</head>
<body>
<div class='container'>
  <header>
    <h1>{DASHBOARD_TITLE}</h1>
    <p>{DASHBOARD_SUBTITLE}</p>
    <div class='stats'>
      <div class='stat'><strong>{total_listings}</strong>Aluguéis coletados</div>
      <div class='stat'><strong>{price_count}</strong>Preços mapeados</div>
      <div class='stat'><strong>{generated_at}</strong>Atualizado</div>
    </div>
  </header>
  <nav>
    <a href='#granada'>🏘️ Granada</a>
    <a href='#alicante'>🏙️ Alicante</a>
    <a href='#nerja'>🏖️ Nerja</a>
    <a href='#prices'>🛒 Preços</a>
  </nav>
  {cards_html}
  <div id='prices'>{prices_html}</div>
  <footer>
    Gerado por SET_UP · <a href='https://github.com/Mauricio1806/SET_UP' style='color:#a5b4fc'>GitHub</a>
    · Dados: OpenStreetMap, Habitaclia, Pisos.com, Mercadona
  </footer>
</div>
</body>
</html>
"""


def _card_html(item):
    grade_letter = (item.get("grade") or "D")[0]
    scores = item.get("scores", {})
    brands = sorted({
        p.get("priority_brand")
        for pois in item.get("pois", {}).values()
        for p in pois
        if p.get("priority_brand")
    })

    badges = ""
    if item.get("nearest_supermarket_m"):
        badges += f"<span class='badge'>🛒 {item['nearest_supermarket_m']}m</span>"
    if item.get("nearest_gym_m"):
        badges += f"<span class='badge'>💪 {item['nearest_gym_m']}m</span>"
    for b in brands[:3]:
        badges += f"<span class='badge priority'>{_esc(b)}</span>"

    meta = ""
    if item.get("rooms"):
        meta += f"<span>🛏️ {item['rooms']}q</span>"
    if item.get("m2"):
        meta += f"<span>📐 {item['m2']}m²</span>"
    if item.get("source"):
        meta += f"<span>🔗 {item['source']}</span>"

    url = item.get("url", "#")
    title = _esc(item.get("title", "Sem título")[:70])
    price = item.get("price", "?")
    total_score = scores.get("total", 0)

    return f"""
    <div class='card grade-{grade_letter}'>
      <h3><a href='{url}' target='_blank' rel='noopener'>{title}</a></h3>
      <div class='price'>€{price}<span style='font-size:0.6em;opacity:0.7'>/mês</span></div>
      <div class='meta'>{meta}<span>⭐ {total_score:.0f}pt · {_esc(item.get("grade", ""))}</span></div>
      <div class='badges'>{badges}</div>
    </div>
    """


def _esc(text):
    if text is None:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
