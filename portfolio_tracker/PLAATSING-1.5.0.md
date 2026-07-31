# Waar hoort welk bestand? — versie 1.5.0

Pak `portfolio-tracker-1.5.0.zip` uit **in de wortel van je repository** (de map waar
`repository.yaml` staat). De paden in de zip komen exact overeen met je repostructuur,
dus alles belandt vanzelf op de juiste plek en overschrijft de oude versie.

```
<jouw-repo>/
└── portfolio_tracker/
    ├── app.py                  ← VERVANGEN (6414 → 141 regels)
    ├── database.py             ← VERVANGEN (dividendberekening samengevoegd)
    ├── config.yaml             ← VERVANGEN (versie 1.5.0)
    ├── CHANGELOG.md            ← VERVANGEN
    ├── HANDLEIDING.md          ← VERVANGEN
    ├── PLAATSING-1.5.0.md      ← dit bestand (mag je nadien weggooien)
    └── views/                  ← NIEUWE MAP, zestien nieuwe bestanden
        ├── __init__.py
        ├── common.py           gedeeld fundament (geen pagina)
        ├── dashboard.py        📊 Dashboard
        ├── portfolio.py        💼 Portefeuille
        ├── cash.py             💶 Cash
        ├── evolution.py        📈 Evolutie
        ├── assets.py           🏢 Activa
        ├── transactions.py     ➕ Transacties
        ├── dividends.py        💰 Dividenden
        ├── simulation.py       🧮 Simulatie
        ├── tax.py              🧾 Belgische Belasting
        ├── ai.py               🤖 AI Advisor
        ├── status.py           🩺 Status
        ├── settings.py         ⚙️ Instellingen
        └── docs.py             📖 Handleiding
```

## Handmatig plaatsen

Zonder zip: maak in `portfolio_tracker/` een map `views` aan, zet daar de zestien
`views/`-bestanden in, en vervang in `portfolio_tracker/` zelf de vijf bestanden
hierboven.

## Wat blijft staan

`belgian_tax.py`, `market_data.py`, `ai_advisor.py`, `scheduler.py`, `bulk_import.py`,
`Dockerfile`, `run.sh`, `requirements.txt`, `DOCS.md`, `README.md`, `.streamlit/` en de
map `windows/` zijn ongewijzigd. Er hoeft niets verwijderd te worden.

## Daarna

Home Assistant → add-on → **Herbouwen** (niet enkel herstarten). Controleer bij de
eerste start twee dingen:

1. De pagina **📖 Handleiding** laadt haar tekst — dan klopt de padwijziging.
2. De zijbalk toont precies dertien menu-items — dan heeft Streamlit geen eigen
   navigatie toegevoegd naast de jouwe.
