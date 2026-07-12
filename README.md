# 🏠 SET_UP — Spain Rental Live

Pipeline diário de scraping de aluguéis + preços de mercado + análise de proximidade, com sync automático para o hub Notion **Spain Digital Nomad**.

## O que faz

1. **Scraping de aluguéis** em Habitaclia, Pisos.com, Idealista (com fallback)
2. **Preços Mercadona** dos produtos essenciais da dieta real
3. **Análise de proximidade** via OpenStreetMap (Overpass API):
   - Supermercados (Mercadona, Lidl, Dia, Covirán)
   - Academias (Basic-Fit, Synergym, McFit)
   - Farmácias, transporte, áreas verdes
4. **Scoring composto** (0-100): preço + proximidade + marcas prioritárias
5. **Sync Notion** — cria/atualiza databases "🏠 Aluguéis Live" e "🛒 Preços Live" filhas do hub (não deleta nada)
6. **Dashboard GitHub Pages** com HTML estático
7. **GitHub Actions** rodando 2×/dia (8h e 20h Salvador)

## Setup

```powershell
# 1. Clone
git clone https://github.com/Mauricio1806/SET_UP.git
cd SET_UP

# 2. Instale deps
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Configure
copy .env.example .env
# Edite .env com NOTION_TOKEN

# 4. Rode local
python -m src.main
```

## Configuração no GitHub

**Settings → Secrets and variables → Actions → New repository secret:**

- `NOTION_TOKEN` → token da sua integração Notion
- `NOTION_HUB_ID` → `3736d7bcf70c81c09c0ff224c550e309`

**Settings → Pages → Source: GitHub Actions (docs folder)**

## Estrutura

```
src/
├── config.py              # Cidades-alvo, POIs, pesos
├── scrapers/              # Habitaclia, Pisos, Idealista, Mercadona
├── proximity/             # Geocoder + Overpass POIs
├── ranking/               # Score composto 0-100
├── notion_sync/           # Notion API (evolutivo, não destrutivo)
├── dashboard/             # HTML estático → GitHub Pages
└── main.py                # Orquestrador
```

## O que aparece no Notion

- **🏠 Aluguéis Live — Últimas 24h** — database com top 30 aluguéis rankeados
- **🛒 Preços Mercadona Live** — database com preços dos essenciais

Ambas são filhas do hub existente e **não substituem nada**.
