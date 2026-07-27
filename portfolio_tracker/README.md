# Portfolio Tracker

Zelfgehoste portefeuillebeheerder voor de Belgische particuliere belegger. Houdt
transacties, dividenden en cash bij, rekent de Belgische fiscaliteit mee (TOB,
roerende voorheffing, buitenlandse bronbelasting, meerwaardebelasting met fotomoment)
en geeft AI-gestuurd advies over de portefeuille en de bredere markt.

Draait als **Home Assistant add-on** of als **zelfstandige toepassing op Windows**.
Dezelfde codebase, alleen een andere opstartlaag.

## Documentatie

**De volledige handleiding zit in de app zelf**: start ze en kies in het linkermenu
**📖 Handleiding**. Daar staan alle hoofdstukken met een zoekveld, en ze hoort altijd
bij de versie die je draait — ook zonder internetverbinding.

<!-- ────────────────────────────────────────────────────────────────────────────
     Deze links zijn ABSOLUUT en niet relatief, om twee redenen:
       1. Home Assistant rendert dit bestand in zijn eigen scherm, waar een
          relatief pad nergens naartoe wijst en een klik dus niets doet.
       2. Dit bestand staat in portfolio_tracker/, maar wordt ook vanuit de
          repository-root bekeken; een relatief pad klopt dan in maar één van
          beide gevallen.
     '/blob/HEAD/' wijst altijd naar de standaardbranch, ook als die later
     hernoemd wordt.
     ──────────────────────────────────────────────────────────────────────── -->

| Document | Inhoud |
|---|---|
| [HANDLEIDING.md](https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker/blob/HEAD/portfolio_tracker/HANDLEIDING.md) | Volledige handleiding: basiswerking, uitleg per pagina, fiscale motor, AI, ontwerpkeuzes |
| [INSTALL_WINDOWS.md](https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker/blob/HEAD/portfolio_tracker/windows/INSTALL_WINDOWS.md) | Installatie en gebruik op Windows |
| [CHANGELOG.md](https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker/blob/HEAD/portfolio_tracker/CHANGELOG.md) | Wat er per versie gewijzigd is, en waarom |

`DOCS.md` is de korte versie die Home Assistant toont in het tabblad **Documentatie**
van de add-on.

## Snel starten

**Home Assistant.** Voeg `https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker`
toe als add-on-repository, installeer de add-on en start ze. De data komt in
`/share/portfolio_tracker`.

**Windows.** Clone of download de repo, draai `windows\setup.bat` en daarna
`windows\start.bat`. Zie de installatiehandleiding voor de vereisten.

Voor het opzetten van een lege portefeuille: hoofdstuk 2 van de handleiding.

## Techniek

Python 3.11, Streamlit, SQLite, APScheduler, Plotly, OpenAI API. Koersen komen van
Yahoo Finance, onvista, Euronext, Tradegate en Deutsche Börse, met de ISIN als sleutel.

## Voorbehoud

Deze app is een hulpmiddel voor je eigen administratie, geen aangiftesoftware en geen
beleggingsadvies. Controleer fiscale cijfers voor je ze gebruikt.
