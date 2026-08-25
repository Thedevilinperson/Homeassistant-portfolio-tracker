# Waar hoort welk bestand? — versie 1.8.0

Pak `portfolio-tracker-1.8.0.zip` uit **in de wortel van je repository** (de map waar
`repository.yaml` staat).

```
<jouw-repo>/
└── portfolio_tracker/
    ├── fcpe_pricing.py     ← NIEUW      de formule uit het fondsreglement
    ├── market_data.py      ← VERVANGEN  aansluiting + automatisch ophalen waarnemingen
    ├── database.py         ← VERVANGEN  waarnemingen, parameters, officiële NAV
    ├── scheduler.py        ← VERVANGEN  maandelijkse waarneming vastleggen (23:10)
    ├── config.yaml         ← VERVANGEN  versie 1.8.0
    ├── CHANGELOG.md        ← VERVANGEN
    ├── HANDLEIDING.md      ← VERVANGEN
    ├── PLAATSING-1.8.0.md  ← dit bestand (mag je nadien weggooien)
    └── views/
        └── assets.py       ← VERVANGEN  het paneel 📐 Fondsformule
```

Ongewijzigd: `app.py`, `belgian_tax.py`, `ai_advisor.py`, `bulk_import.py`, de overige
vijftien bestanden in `views/`, `Dockerfile`, `run.sh`, `config.toml`, `.streamlit/`,
`DOCS.md`, `README.md` en de map `windows/`.

## Na het herbouwen: zo zet je Link Multiple BEL 2022 op

`🏢 Activa → 📋 Overzicht → 📐 Fondsformule`

1. Kies het fonds, en als onderliggende waarde het **ENGIE-aandeel**.
2. De parameters staan al voorgevuld op de jaargang 2022: α = 16, 60 waarnemingen,
   waarnemingsdag 15, eerste waarnemingsmaand januari 2023, aanvang 22 december 2022,
   vervaldag 15 december 2027, rendement 1,5% per jaar en 7,73% op vervaldag.
3. Vul **referentieprijs** en **inschrijvingsprijs** in uit je reglement. Heb je die niet
   bij de hand, sla dan eerst op, haal de waarnemingen op, en gebruik daarna
   *🎯 Parameters kalibreren* met de NAV-export van Amundi — dan leidt de app ze af.
4. **Opslaan en activeren**, dan **Waarnemingen ophalen**. De app haalt de slotkoers van
   ENGIE op voor alle 44 voorbije waarnemingsdata sinds 13 januari 2023. Vanaf dan
   gebeurt dat maandelijks vanzelf.
5. Controleer via *🎯 Kalibreren* de tabel berekend-tegenover-officieel. Ligt de
   gemiddelde afwijking dicht bij nul, dan kloppen je parameters.

Klopt het niet meteen: de gepubliceerde NAV is de waarheid, niet de berekening. Pas de
referentie- en inschrijvingsprijs aan tot de afwijking klein is, of laat de kalibratie
het doen.

De Classic- en Liberty-fondsen laat je op de bestaande lineaire methode staan
(🧮 Afgeleide koers): daar is één deelbewijs exact één aandeel, en dat klopt al.
