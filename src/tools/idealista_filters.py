"""
Gera URLs de filtro precisas para o Idealista baseado nos
bairros-alvo e critérios do perfil Mauricio.

Uso: python -m src.tools.idealista_filters
Gera um arquivo docs/idealista_filters.html com links clicáveis.
"""

import sys, os, json
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
DOCS_DIR.mkdir(exist_ok=True)

# Perfil Mauricio — filtros base
PROFILE = {
    "max_price":   900,    # teto coleta (scorer penaliza acima de 750)
    "ideal_price": 750,    # ideal Granada
    "min_size":    35,     # m² mínimo
    "furnished":   True,
    "min_rooms":   1,
}

# Bairros por cidade com coordenadas e raio de busca
# Baseado no mapeamento do hub Notion
NEIGHBORHOODS = {
    "granada": [
        {
            "name": "Zaidín (MELHOR — Score 9.5)",
            "lat": 37.1580, "lon": -3.5980, "radius": 800,
            "slug": "zaidin-granada",
            "notes": "6+ supermercados <5min · Synergym · Sano · Tapas grátis",
            "url_path": "alquiler-viviendas/zaidin-granada-granada/",
        },
        {
            "name": "Arabial / Pajaritos (4 academias na mesma rua)",
            "lat": 37.1700, "lon": -3.6050, "radius": 600,
            "slug": "arabial-pajaritos-granada",
            "notes": "Basic-Fit + McFit + VivaGym + Brooklyn em <500m",
            "url_path": "alquiler-viviendas/arabial-granada-granada/",
        },
        {
            "name": "Camino de Ronda",
            "lat": 37.1720, "lon": -3.6020, "radius": 700,
            "slug": "camino-ronda-granada",
            "notes": "Eixo comercial principal · Basic-Fit · BeOne",
            "url_path": "alquiler-viviendas/camino-de-ronda-granada-granada/",
        },
        {
            "name": "Chana (mais barato)",
            "lat": 37.1820, "lon": -3.6150, "radius": 800,
            "slug": "chana-granada",
            "notes": "€470-610 · Mercadona próximo",
            "url_path": "alquiler-viviendas/chana-granada-granada/",
        },
        {
            "name": "Beiro",
            "lat": 37.1870, "lon": -3.6100, "radius": 700,
            "slug": "beiro-granada",
            "notes": "Residencial tranquilo",
            "url_path": "alquiler-viviendas/beiro-granada-granada/",
        },
    ],
    "alicante": [
        {
            "name": "Benalúa (MELHOR — Score 9.2)",
            "lat": 38.3390, "lon": -0.4850, "radius": 700,
            "slug": "benalua-alicante",
            "notes": "5+ supermercados · Basic-Fit próximo",
            "url_path": "alquiler-viviendas/benalua-alicante-alacant/",
        },
        {
            "name": "Carolinas Bajas",
            "lat": 38.3550, "lon": -0.4750, "radius": 700,
            "slug": "carolinas-alicante",
            "notes": "4 supermercados · 4 academias",
            "url_path": "alquiler-viviendas/carolinas-alicante-alacant/",
        },
        {
            "name": "Centro Alicante",
            "lat": 38.3452, "lon": -0.4810, "radius": 600,
            "slug": "centro-alicante",
            "notes": "Central · mais caro",
            "url_path": "alquiler-viviendas/centro-alicante-alacant/",
        },
    ],
    "nerja": [
        {
            "name": "Centro Nerja",
            "lat": 36.7503, "lon": -3.8747, "radius": 600,
            "slug": "centro-nerja",
            "notes": "Centro histórico · praia próxima",
            "url_path": "alquiler-viviendas/nerja-malaga/",
        },
        {
            "name": "Capistrano",
            "lat": 36.7540, "lon": -3.8700, "radius": 500,
            "slug": "capistrano-nerja",
            "notes": "Urbanização tranquila",
            "url_path": "alquiler-viviendas/capistrano-nerja-malaga/",
        },
    ],
}


def build_idealista_url(neighborhood: dict, max_price: int = 900,
                         furnished: bool = True, min_rooms: int = 1) -> str:
    """Gera URL de busca precisa do Idealista para o bairro."""
    base = "https://www.idealista.com"
    path = neighborhood["url_path"]

    # Filtros na URL
    filters = []
    filters.append(f"con-precio-hasta_{max_price}")
    if min_rooms == 1:
        filters.append("de-un-dormitorio")
    if furnished:
        filters.append("amueblado")

    filter_str = ",".join(filters)
    return f"{base}/{path}{filter_str}/?ordenado-por=precios-asc"


def build_fotocasa_url(neighborhood: dict, max_price: int = 900) -> str:
    """URL alternativa do Fotocasa."""
    city_map = {
        "granada": "granada-capital",
        "alicante": "alicante-alacant",
        "nerja": "nerja",
    }
    # Fotocasa não suporta filtro por bairro na URL facilmente
    # Gera busca geral com preço máximo
    city = next((c for c, nbs in NEIGHBORHOODS.items()
                  if neighborhood in nbs), "granada")
    city_slug = city_map.get(city, "granada-capital")
    return (f"https://www.fotocasa.es/es/alquiler/viviendas/"
            f"{city_slug}/todas-las-zonas/l"
            f"?maxPrice={max_price}&bedrooms=1")


def generate_html(neighborhoods_data: dict) -> str:
    """Gera página HTML com todos os filtros organizados."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    city_sections = ""
    for city, neighborhoods in neighborhoods_data.items():
        city_name = {"granada": "🏘️ Granada", "alicante": "🏙️ Alicante", "nerja": "🏖️ Nerja"}[city]
        ideal_price = {"granada": 750, "alicante": 950, "nerja": 950}[city]

        nb_cards = ""
        for nb in neighborhoods:
            idealista_url = build_idealista_url(nb, max_price=ideal_price)
            idealista_url_max = build_idealista_url(nb, max_price=ideal_price + 150)

            nb_cards += f"""
            <div class="nb-card">
              <h3>{nb['name']}</h3>
              <p class="notes">📍 {nb['notes']}</p>
              <div class="links">
                <a href="{idealista_url}" target="_blank" class="btn primary">
                  🏠 Idealista ≤€{ideal_price}
                </a>
                <a href="{idealista_url_max}" target="_blank" class="btn secondary">
                  🏠 Idealista ≤€{ideal_price + 150}
                </a>
                <a href="https://www.pisos.com/alquiler/pisos-{nb['slug'].replace('-','_')}/" 
                   target="_blank" class="btn alt">
                  📋 Pisos.com
                </a>
              </div>
              <details>
                <summary>Ver URLs completas</summary>
                <code>{idealista_url}</code>
              </details>
            </div>"""

        city_sections += f"""
        <section class="city">
          <h2>{city_name}</h2>
          <p class="budget">Orçamento ideal: <strong>≤€{ideal_price}/mês</strong></p>
          <div class="nb-grid">{nb_cards}</div>
        </section>"""

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>🏠 SET_UP — Filtros Idealista por Bairro</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0 }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0a0e27; color: #e2e8f0; padding: 20px }}
    .container {{ max-width: 1100px; margin: 0 auto }}
    header {{ background: linear-gradient(135deg, #1e40af, #6d28d9);
              padding: 24px; border-radius: 12px; margin-bottom: 24px }}
    h1 {{ font-size: 1.6rem; margin-bottom: 6px }}
    header p {{ opacity: .8; font-size: .9rem }}
    .city {{ margin-bottom: 36px }}
    h2 {{ font-size: 1.3rem; color: #a5b4fc; margin-bottom: 6px }}
    .budget {{ font-size: .85rem; opacity: .7; margin-bottom: 14px }}
    .nb-grid {{ display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 14px }}
    .nb-card {{ background: #1e293b; border-radius: 10px; padding: 16px;
                border-left: 4px solid #6d28d9 }}
    .nb-card h3 {{ font-size: .95rem; margin-bottom: 6px }}
    .notes {{ font-size: .8rem; opacity: .7; margin-bottom: 12px }}
    .links {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px }}
    .btn {{ padding: 7px 12px; border-radius: 7px; text-decoration: none;
            font-size: .8rem; font-weight: 600 }}
    .btn.primary {{ background: #6d28d9; color: #fff }}
    .btn.secondary {{ background: #1e40af; color: #fff }}
    .btn.alt {{ background: #334155; color: #e2e8f0 }}
    .btn:hover {{ opacity: .85 }}
    details {{ margin-top: 8px }}
    summary {{ font-size: .75rem; opacity: .6; cursor: pointer }}
    code {{ display: block; font-size: .7rem; word-break: break-all;
             background: #0f172a; padding: 8px; border-radius: 6px;
             margin-top: 6px; color: #86efac }}
    .tip {{ background: #1e293b; border-left: 4px solid #10b981;
            padding: 14px; border-radius: 8px; margin-bottom: 24px;
            font-size: .85rem; line-height: 1.6 }}
    footer {{ text-align: center; opacity: .4; font-size: .8rem; margin-top: 32px }}
  </style>
</head>
<body>
<div class="container">
  <header>
    <h1>🏠 SET_UP — Filtros Idealista por Bairro</h1>
    <p>Atualizado: {now} · Perfil: 1q mobiliado · preço crescente</p>
  </header>

  <div class="tip">
    💡 <strong>Como usar:</strong> Clique no botão do bairro que quer pesquisar.
    O link abre o Idealista já filtrado por bairro + preço máximo + 1 quarto + mobilhado.
    Os resultados já aparecem do mais barato para o mais caro.
    <br><br>
    ⏳ <strong>Enquanto a API oficial não chega:</strong> use estes filtros manualmente.
    Quando chegar a API key, o pipeline vai puxar automaticamente e você não precisará mais fazer isso.
  </div>

  {city_sections}

  <footer>SET_UP · Gerado automaticamente · GitHub Pages</footer>
</div>
</body>
</html>"""


def main():
    print("=" * 50)
    print("SET_UP — Gerando filtros Idealista por bairro")
    print("=" * 50)

    html = generate_html(NEIGHBORHOODS)
    out = DOCS_DIR / "idealista_filters.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n✓ Gerado: {out}")

    # Resume as URLs mais importantes no terminal
    print("\n📋 LINKS PRINCIPAIS (copie e cole no navegador):\n")
    for city, nbs in NEIGHBORHOODS.items():
        price = {"granada": 750, "alicante": 950, "nerja": 950}[city]
        print(f"  {city.upper()}")
        for nb in nbs[:2]:
            url = build_idealista_url(nb, max_price=price)
            print(f"  {nb['name'][:40]}")
            print(f"  → {url}\n")


if __name__ == "__main__":
    main()
