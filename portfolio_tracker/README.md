# Portfolio Tracker

Zelfgehoste portefeuillebeheerder voor de Belgische particuliere belegger. Houdt
transacties, dividenden en cash bij, rekent de Belgische fiscaliteit mee (TOB,
roerende voorheffing, buitenlandse bronbelasting, meerwaardebelasting met fotomoment)
en geeft AI-gestuurd advies over de portefeuille en de bredere markt.

Draait als **Home Assistant add-on** of als **zelfstandige toepassing op Windows**.
Dezelfde codebase, alleen een andere opstartlaag.

## Documentatie

| Document | Inhoud |
|---|---|
| [HANDLEIDING.md](HANDLEIDING.md) | Volledige handleiding: basiswerking, uitleg per pagina, fiscale motor, AI, ontwerpkeuzes |
| [windows/INSTALL_WINDOWS.md](windows/INSTALL_WINDOWS.md) | Installatie en gebruik op Windows |
| [CHANGELOG.md](CHANGELOG.md) | Wat er per versie gewijzigd is, en waarom |

## Snel starten

**Home Assistant.** Voeg deze repository toe als add-on-repository, installeer de
add-on en start ze. De data komt in `/share/portfolio_tracker`.

**Windows.** Clone of download de repo, draai `windows\setup.bat` en daarna
`windows\start.bat`. Zie de installatiehandleiding voor de vereisten.

Voor het opzetten van een lege portefeuille: hoofdstuk 2 van de handleiding.

## Techniek

Python 3.11, Streamlit, SQLite, APScheduler, Plotly, OpenAI API. Koersen komen van
Yahoo Finance, onvista, Euronext, Tradegate en Deutsche Börse, met de ISIN als sleutel.

## Voorbehoud

Deze app is een hulpmiddel voor je eigen administratie, geen aangiftesoftware en geen
beleggingsadvies. Controleer fiscale cijfers voor je ze gebruikt.
