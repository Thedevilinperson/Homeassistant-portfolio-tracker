# Plaatsing 1.8.15

Deze zip bevat de negen punten uit je lijst: dividendkalender, handmatige AI-kosten,
uitschieterfilter op de koersdoelen, 30-daags AI-koersdoel op portefeuille en
dashboard, 200-daags gemiddelde, dividend overnemen, alleen nog gedetailleerde
dividendinvoer, voorbije dividenddatums op de statuspagina, en het bezoekblok dat
niet meer van je filterselectie afhangt.

## Wat er in dit pakket zit

| Bestand | Waarom |
|---|---|
| `portfolio_tracker/database.py` | `robust_average()` (uitschieters), tabellen `dividend_calendar` en `ai_manual_costs` met hun functies, `get_ai_target_averages()`, `dividend_booked_near()` |
| `portfolio_tracker/market_data.py` | Dividendkalender met bronketen Yahoo + optioneel FMP, `get_moving_average()` en `moving_average_map()` |
| `portfolio_tracker/ai_advisor.py` | Gemiddeld koersdoel per periode; 200-daags gemiddelde als invoer voor het dagelijkse advies |
| `portfolio_tracker/scheduler.py` | Nieuwe dagelijkse job 23:40: dividendkalender verversen |
| `portfolio_tracker/views/common.py` | Gedeelde kalenderafleidingen: positie per rekening op de ex-datum, boekingsstatus, achterstallige uitkeringen |
| `portfolio_tracker/views/dividends.py` | Tab Kalender, boeken met één klik, dividend overnemen, eenvoudige invoerwijze verwijderd |
| `portfolio_tracker/views/dashboard.py` | Kolommen AI 30d, ex-dividendwaarschuwing, bezoekblok losgekoppeld van de filter |
| `portfolio_tracker/views/portfolio.py` | Kolommen AI 30d en Pot. 30d |
| `portfolio_tracker/views/evolution.py` | Sectie 200-daags voortschrijdend gemiddelde |
| `portfolio_tracker/views/status.py` | Tabbladen + tab Voorbije dividenddatums |
| `portfolio_tracker/views/ai.py` | Gemiddeld koersdoel per periode, handmatige AI-kosten |
| `portfolio_tracker/views/settings.py` | Nieuwe sectie Gegevensbronnen (FMP-sleutel) |
| `portfolio_tracker/config.yaml` | Versie -> 1.8.15 |
| `portfolio_tracker/CHANGELOG.md` | Rubriek 1.8.15 |

## Plaatsen

1. Kopieer de bestanden over de bestaande, met behoud van de mappen. Let op de acht
   bestanden in `views/`.
2. Commit en push naar `main` en `master`.
3. In Home Assistant: Instellingen -> Add-ons -> Portfolio Tracker -> **Herbouwen**.

De twee nieuwe tabellen worden bij de eerste start automatisch aangemaakt. Er wordt
niets aan bestaande gegevens gewijzigd.

## Eerste keer: de kalender vullen

Ga naar `Dividenden -> Kalender` en klik op **Kalender ophalen**. Dat haalt de
uitkeringen op voor je open posities en voor de aandelen die de AI de laatste 30
dagen voorstelde. Daarna doet de planner het elke nacht om 23:40.

Wat je mag verwachten van de gratis bron (Yahoo):

- **Voorbije uitkeringen**: ex-datum en bedrag, maar GEEN betaaldatum. De kalender
  toont dan de ex-datum met "(ex)" erbij, als benadering.
- **De eerstvolgende uitkering**: ex-datum en betaaldatum, en meestal ook het bedrag.
- **Interimdividenden** staan als aparte lijnen, met hun eigen datums en bedrag —
  een acompte en een saldo zijn dus twee lijnen, niet één.
- Kapitaliserende trackers en aandelen die niet uitkeren leveren niets op. Dat is
  geen fout; ze verschijnen in de melding "geen dividendgegevens gevonden".

Ontbrekende betaaldatums vul je zelf aan onder **Zelf een uitkering toevoegen of
corrigeren**. Wat je daar invoert, wordt door een automatische ophaling nooit
overschreven.

## Optioneel: betaaldatums van voorbije uitkeringen

Wil je die niet handmatig aanvullen, dan kan een sleutel van Financial Modeling Prep
ze automatisch invullen: `Instellingen -> Gegevensbronnen`. FMP geeft per uitkering
de betaaldatum en de frequentie; de bedragen van Yahoo blijven leidend.

**Lees dit eerst.** Op het gratis plan van FMP zitten enkel Amerikaanse noteringen.
Voor Euronext Brussel, Parijs en Amsterdam — dus voor het grootste deel van jouw
portefeuille — heb je een betalend plan nodig. Zonder sleutel blijft alles gewoon
werken.

En één eerlijke kanttekening: die FMP-koppeling is getest tegen een nagebootst
antwoord, niet tegen de echte API — de ontwikkelomgeving kan die website niet
bereiken. De samenvoeging klopt (Yahoo blijft leidend voor de bedragen, FMP vult
alleen lege betaaldatums, de bron wordt dan "Yahoo + FMP"), maar of hun veldnamen
vandaag exact `date`, `paymentDate`, `dividend` en `frequency` heten, weet je pas bij
de eerste echte oproep. Mislukt ze, dan valt de kalender stil terug op Yahoo alleen
en zie je in het add-on-logboek een regel `_divcal_fmp(...)`.

## Een uitkering boeken

In de kalender kies je onder **Een uitkering boeken** de lijn en de rekening, en klik
je op **Boek dit dividend**. Er wordt niets rechtstreeks weggeschreven: het gewone
dividendformulier wordt ingevuld met het activum, de rekening, de betaaldatum en het
geschatte bruto (aantal x bedrag per aandeel). Bij een buitenlands aandeel komt dat
als (1) bruto voor bronbelasting, bij een Belgisch als (3) — de keten klopt dus
meteen. Jij kijkt na wat je broker effectief afrekende, en slaat op.

Een uitkering die nog moet komen, kan je niet boeken: het geld staat nog niet op je
rekening, en een dividend met een datum in de toekomst zou je cashsaldo en je
aangifte vooruitlopen op de feiten.

Had je hetzelfde aandeel op meerdere rekeningen op de ex-datum, boek dan een lijn per
rekening — de app toont per rekening het juiste aantal.

## Waar je de rest terugvindt

| Punt | Waar |
|---|---|
| Gemiddeld koersdoel per periode | AI Advisor -> Marktopportuniteiten -> Opvolging |
| AI-kosten handmatig ingeven | AI Advisor -> AI-kosten handmatig ingeven |
| AI 30d / Pot. 30d | Portefeuille -> Open posities; Dashboard -> Dagresultaat |
| 200-daags gemiddelde | Evolutie, onderaan |
| Voorbije dividenddatums | Status -> Voorbije dividenddatums |
| Dividend overnemen | Dividenden -> Dividend toevoegen -> Overnemen van een eerder dividend |

## Twee dingen die je zal merken

**Je koersdoelen kunnen licht verschuiven.** Het gemiddelde van de AI-bepalingen
weert nu uitschieters. Stond er in je reeks een wilde waarde, dan schuift het
koersdoel naar een realistischer cijfer. Dat is de bedoeling, maar het verklaart
waarom een getal dat je gisteren zag vandaag anders staat.

**De Evolutie-pagina laadt de eerste keer trager.** Het 200-daags gemiddelde vraagt
per open positie een koersreeks van ongeveer anderhalf jaar. Die zit daarna een half
uur in de cache. Dezelfde reeksen voeden ook het dagelijkse AI-advies, dus de eerste
generatie na deze update kan iets langer duren.
