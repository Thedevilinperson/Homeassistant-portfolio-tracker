# Waar hoort welk bestand? — versie 1.8.1

Pak `portfolio-tracker-1.8.1.zip` uit **in de wortel van je repository**.

```
<jouw-repo>/
└── portfolio_tracker/
    ├── fcpe_pricing.py     ← NIEUW/VERVANGEN  formule + kalibratie met vaste α
    ├── market_data.py      ← VERVANGEN        aansluiting + waarnemingen ophalen
    ├── database.py         ← VERVANGEN        waarnemingen, parameters, officiële NAV
    ├── scheduler.py        ← VERVANGEN        maandelijkse waarneming (23:10)
    ├── config.yaml         ← VERVANGEN        versie 1.8.1
    ├── CHANGELOG.md        ← VERVANGEN
    ├── HANDLEIDING.md      ← VERVANGEN
    ├── PLAATSING-1.8.1.md  ← dit bestand
    └── views/
        └── assets.py       ← VERVANGEN        paneel 📐 Fondsformule
```

Dit is de volledige 1.8.0-levering mét de correctie; heb je 1.8.0 nog niet geplaatst,
dan volstaat dit pakket. Ongewijzigd blijven `app.py`, `belgian_tax.py`, `ai_advisor.py`,
`bulk_import.py`, de overige vijftien bestanden in `views/`, `Dockerfile`, `run.sh`,
`config.toml`, `.streamlit/`, `DOCS.md`, `README.md` en `windows/`.

## Opnieuw kalibreren na het herbouwen

`🏢 Activa → 📋 Overzicht → 📐 Fondsformule → 🎯 Parameters kalibreren`

α blijft nu staan op wat je bovenaan invulde (16). Laat de twee vinkjes uit tenzij je
de inschrijvingsprijs evenmin kent. Blijft de afwijking groot, dan ligt de oorzaak
waarschijnlijk niet bij de referentieprijs maar bij de waarnemingen, de aanvangsdatum
of de inschrijvingsprijs — de app zegt dat er nu ook bij.
