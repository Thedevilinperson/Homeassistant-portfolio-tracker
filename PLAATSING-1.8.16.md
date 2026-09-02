# Plaatsing 1.8.16

Golden cross / death cross: een nieuwe tab op de statuspagina die het 50-daags
gemiddelde (MA50) naast het bestaande 200-daags gemiddelde (MA200) zet, elke
kruising tussen de twee bijhoudt in een logboek, en dat automatisch laat meelopen
met de dagelijkse statuscontrole.

## Wat er in dit pakket zit

| Bestand | Waarom |
|---|---|
| `portfolio_tracker/database.py` | Nieuwe tabel `ma_cross_events`; functies `detect_ma_crosses()`, `record_ma_cross_event()`, `get_ma_cross_events()`; detectie geïntegreerd in `run_status_checks()` |
| `portfolio_tracker/views/status.py` | Nieuwe tab **📈 Golden/Death Cross**: actuele MA50/MA200 per open positie, grafiek met kruispunten, logboek |
| `portfolio_tracker/config.yaml` | Versie → 1.8.16 |
| `portfolio_tracker/CHANGELOG.md` | Rubriek 1.8.16 |

Geen wijzigingen aan `market_data.py`: de nieuwe functionaliteit hergebruikt gewoon
de bestaande `get_price_series()` en `moving_average_map()`.

## Plaatsen

1. Kopieer `database.py` en `config.yaml`/`CHANGELOG.md` naar de hoofdmap van
   `portfolio_tracker/`, en `status.py` naar `portfolio_tracker/views/`.
2. Commit en push naar `main` en `master`.
3. In Home Assistant: Instellingen → Add-ons → Portfolio Tracker → **Herbouwen**
   (niet enkel herstarten, wegens Docker-laagcaching).

De nieuwe tabel `ma_cross_events` wordt bij de eerste start automatisch aangemaakt.
Er wordt niets aan bestaande gegevens gewijzigd.

## Eerste gebruik

Ga naar **Status → 📈 Golden/Death Cross** en klik op **Nu controleren op
kruisingen**. Dat haalt voor elke open positie ongeveer 2,5 jaar koershistoriek op
en rekent MA50/MA200 uit — reken bij veel posities op een paar seconden per activum.
Daarna doet de dagelijkse statuscontrole (22:45) het vanzelf mee.

**Wat je meteen ziet:**

- Een tabel met MA50, MA200, koers en actuele stand ("🟢 Golden" of "🔴 Death") per
  open positie.
- Onder elke controle een selectievak om de koersgrafiek van een specifiek activum
  te bekijken, met MA50, MA200 en gele/zwarte driehoekjes op elk gedetecteerd
  kruispunt.
- Een logboek met alle gedetecteerde kruisingen, nieuwste eerst.

**Waarom de eerste run trager is:** elke ticker vraagt een koersreeks van bijna drie
jaar op (nodig om MA200 zelf al 200 slotkoersen te kunnen laten opbouwen, plus ruim
anderhalf jaar erna om kruisingen in te herkennen). Die reeks zit al voor het gewone
MA200-overzicht op 📈 Evolutie een uur in de cache, dus een run kort na elkaar is
sneller.

**Een kruising die je niet ziet verschijnen:** heeft een positie minder dan 200
slotkoersen historiek (bv. een recente notering), dan wordt ze overgeslagen — net
zoals bij het bestaande MA200-overzicht. Voor een gekoppeld fonds (bv. het
ENGIE-FCPE-fonds) wordt de koersreeks automatisch via de fondsformule gerekend, dus
die krijgt gewoon een MA50/MA200 zoals elk ander activum.

## Een kanttekening

Golden en death cross zijn achterlopende indicatoren — ze bevestigen een
trendwissel pas nadat die al een tijd bezig is, en geven in een zijwaartse markt
makkelijk valse signalen. De tab zegt dat ook met zoveel woorden in de toelichting
bovenaan. Het is een trendmaatstaf om te volgen, geen instap- of uitstapsignaal op
zich.
