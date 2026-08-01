# Waar hoort welk bestand? — versie 1.6.0

Pak `portfolio-tracker-1.6.0.zip` uit **in de wortel van je repository** (de map waar
`repository.yaml` staat). De paden in de zip komen overeen met je repostructuur.

```
<jouw-repo>/
└── portfolio_tracker/
    ├── belgian_tax.py          ← VERVANGEN  (deblokkeringskalender, aangifteregels,
    │                                         correctie meerwaardebelasting vóór 2026)
    ├── app.py                  ← VERVANGEN  (nieuwe pagina in het menu)
    ├── config.yaml             ← VERVANGEN  (versie 1.6.0)
    ├── CHANGELOG.md            ← VERVANGEN
    ├── HANDLEIDING.md          ← VERVANGEN
    ├── PLAATSING-1.6.0.md      ← dit bestand (mag je nadien weggooien)
    └── views/
        ├── declaration.py      ← NIEUW      (pagina 📋 Aangifte)
        └── portfolio.py        ← VERVANGEN  (deblokkeringskalender erbij)
```

Deze levering veronderstelt dat 1.5.0 geplaatst is: de map `views/` moet al bestaan met
de veertien andere bestanden erin. Is dat niet zo, plaats dan eerst
`portfolio-tracker-1.5.0.zip`.

## Wat blijft staan

`database.py`, `market_data.py`, `ai_advisor.py`, `scheduler.py`, `bulk_import.py`, de
overige veertien bestanden in `views/`, `Dockerfile`, `run.sh`, `config.toml`,
`.streamlit/`, `DOCS.md`, `README.md` en de map `windows/` zijn ongewijzigd.

## Daarna

Home Assistant → add-on → **Herbouwen**. Kijk daarna twee dingen na:

1. De zijbalk toont **veertien** menu-items, met **📋 Aangifte** tussen Belgische
   Belasting en AI Advisor.
2. Op **💼 Portefeuille** staat onder de open posities de **🔓 Deblokkeringskalender**.
   Heb je nergens een *vrij vanaf*-datum ingevuld, dan staat daar een uitleg in plaats
   van een tijdlijn — dat is correct.

## Let op bij de aangiftehulp

Bekeek je eerder een boekjaar **vóór 2026** op de pagina Belgische Belasting en zag je
daar een verschuldigd bedrag staan, dan was dat cijfer fout: het regime bestond toen nog
niet. Het staat nu op nul. Zie de changelog voor de uitleg.
