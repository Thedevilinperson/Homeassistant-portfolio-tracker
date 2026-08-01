# Waar hoort welk bestand? — versie 1.7.0

Pak `portfolio-tracker-1.7.0.zip` uit **in de wortel van je repository** (de map waar
`repository.yaml` staat).

```
<jouw-repo>/
└── portfolio_tracker/
    ├── database.py             ← VERVANGEN  (prullenbak, werkgeversvlag)
    ├── belgian_tax.py          ← VERVANGEN  (blootstelling per onderliggende waarde)
    ├── config.yaml             ← VERVANGEN  (versie 1.7.0)
    ├── CHANGELOG.md            ← VERVANGEN
    ├── HANDLEIDING.md          ← VERVANGEN
    ├── DOCS.md                 ← VERVANGEN
    ├── PLAATSING-1.7.0.md      ← dit bestand (mag je nadien weggooien)
    └── views/
        ├── common.py           ← VERVANGEN  (undo-knop in de verwijderwidget)
        ├── dashboard.py        ← VERVANGEN  (sinds je vorige bezoek)
        ├── portfolio.py        ← VERVANGEN  (blootstelling + werkgeversrisico)
        ├── transactions.py     ← VERVANGEN  (transactie overnemen)
        ├── dividends.py        ← VERVANGEN  (undo bij verwijderen)
        └── settings.py         ← VERVANGEN  (prullenbak onder Data)
```

Deze levering veronderstelt dat 1.6.0 geplaatst is: `views/` moet al bestaan met alle
vijftien bestanden, inclusief `declaration.py`.

## Wat blijft staan

`app.py`, `market_data.py`, `ai_advisor.py`, `scheduler.py`, `bulk_import.py`, de negen
overige bestanden in `views/`, `Dockerfile`, `run.sh`, `config.toml`, `.streamlit/`,
`README.md` en de map `windows/` zijn ongewijzigd.

## Daarna

Home Assistant → add-on → **Herbouwen**. Drie dingen om na te kijken:

1. **💼 Portefeuille** → onder de deblokkeringskalender staat *🎯 Blootstelling per
   onderliggende waarde*. Klap *👔 Welke activa hangen aan je werkgever?* open en duid
   je Link-fondsen en het ENGIE-aandeel aan — pas daarna kan de app het werkgeversrisico
   tonen.
2. **➕ Transacties** → bovenaan het formulier staat *📄 Overnemen van een eerdere
   transactie*.
3. Verwijder eens iets onbelangrijks en klik op *↩️ Ongedaan maken*. De prullenbak zelf
   staat onder **⚙️ Instellingen → 🗃️ Data**.

Het blokje *Sinds je vorige bezoek* verschijnt pas bij je twééde bezoek, en enkel als er
meer dan een half uur tussen zit.
