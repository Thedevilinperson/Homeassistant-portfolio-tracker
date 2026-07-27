# Home Assistant add-on repository — Portfolio Tracker

Deze repository bevat één Home Assistant add-on: **Portfolio Tracker**, een
zelfgehoste portefeuillebeheerder voor de Belgische particuliere belegger.

## Toevoegen aan Home Assistant

1. Ga naar **Instellingen → Add-ons → Add-on store**.
2. Klik rechtsboven op **⋮ → Repositories**.
3. Plak deze URL en klik op **TOEVOEGEN**:

   ```
   https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker
   ```

4. **Portfolio Tracker** verschijnt onderaan de store. Installeren, starten,
   **OPEN WEB UI**.

De database komt in `/share/portfolio_tracker/portfolio.db` en blijft dus bewaard bij
een herinstallatie van de add-on.

## Wat de add-on doet

- **Transacties** met FIFO-kostbasis per rekening, in euro, met de wisselkoers van de
  transactiedatum voorgoed bewaard.
- **Belgische fiscaliteit**: beurstaks (TOB), roerende voorheffing, buitenlandse
  bronbelasting met FBB, en de meerwaardebelasting met fotomoment op 31/12/2025.
- **Dividenden** met de volledige keten van bruto tot netto, per rekening, met de
  mogelijkheid om de wisselkoers van je broker te gebruiken.
- **Cash** afgeleid uit je transacties, stortingen en opnames.
- **Koersen** elke vijf minuten, via Yahoo Finance, onvista, Euronext, Tradegate en
  Deutsche Börse, met de ISIN als sleutel.
- **AI-advies** over je eigen posities en over kansen in de bredere markt (optioneel,
  vereist een eigen OpenAI-sleutel).

De app draait ook als **zelfstandige toepassing op Windows**, los van Home Assistant.
Dezelfde codebase, alleen een andere opstartlaag.

## Documentatie

De volledige handleiding zit **in de app zelf**: linkermenu → **📖 Handleiding**. Ze
is doorzoekbaar en hoort altijd bij de versie die je draait.

| Document | Inhoud |
|---|---|
| [HANDLEIDING.md](https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker/blob/HEAD/portfolio_tracker/HANDLEIDING.md) | Volledige handleiding in twaalf hoofdstukken |
| [DOCS.md](https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker/blob/HEAD/portfolio_tracker/DOCS.md) | Korte versie, ook getoond in het tabblad Documentatie van de add-on |
| [INSTALL_WINDOWS.md](https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker/blob/HEAD/portfolio_tracker/windows/INSTALL_WINDOWS.md) | Installatie en gebruik op Windows |
| [CHANGELOG.md](https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker/blob/HEAD/portfolio_tracker/CHANGELOG.md) | Wat er per versie gewijzigd is, en waarom |

## Mapindeling

```
repository.yaml          definitie van deze add-on-repository
README.md                dit bestand
portfolio_tracker/       de add-on zelf
  config.yaml            naam, versie, ingress, rechten
  Dockerfile, run.sh     de container en het startscript
  app.py, database.py    de applicatie
  HANDLEIDING.md         de volledige handleiding
  DOCS.md                de korte versie voor Home Assistant
  CHANGELOG.md           versiegeschiedenis
  windows/               opstartlaag voor de Windows-versie
```

## Bijwerken

Na een nieuwe versie: **Herbouwen** in Home Assistant, niet enkel herstarten. Door de
laagcaching van Docker pikt een gewone herstart de gewijzigde bestanden niet op.

## Voorbehoud

Deze app is een hulpmiddel voor je eigen administratie, geen aangiftesoftware en geen
beleggingsadvies. Controleer fiscale cijfers voor je ze gebruikt.
