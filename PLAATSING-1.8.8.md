# Plaatsing 1.8.8

Deze zip vervangt de eerdere 1.8.8: dezelfde codewijzigingen, plus de handleiding.
Heb je de vorige versie al geplaatst, dan volstaat het de bestanden opnieuw over te
kopiëren — er is niets dubbel of tegenstrijdig.

## Wat er in dit pakket zit

Enkel de gewijzigde bestanden. Behoud de mappenstructuur — de paden hieronder zijn
relatief aan de wortel van de repo.

| Bestand | Waarom |
|---|---|
| `portfolio_tracker/market_data.py` | Een waarnemingsdatum telt pas mee na sluiting van de beurs; controlepas op eerder opgehaalde waarnemingen |
| `portfolio_tracker/views/assets.py` | Sync-knop draait de controlepas mee, meldingen blijven nu zichtbaar |
| `portfolio_tracker/fcpe_pricing.py` | Ongebruikte `monthly_reading_dates()` geschrapt |
| `portfolio_tracker/HANDLEIDING.md` | Nieuw hoofdstuk 3.10 over gekoppelde koersen; 3.11 voor stockdividend en blokkering |
| `HANDLEIDING.md` (root) | Stond nog op 1.5.0; nu identiek aan die van de add-on |
| `portfolio_tracker/config.yaml` | Versie 1.8.7 → 1.8.8 |
| `portfolio_tracker/CHANGELOG.md` | Rubriek 1.8.8 |

## Plaatsen

1. Kopieer de bestanden over de bestaande, met behoud van de mappen. Let op de twee
   `HANDLEIDING.md`: één in de root, één in `portfolio_tracker/`. Ze zijn identiek.
2. Commit en push naar `main` én `master`.
3. In Home Assistant: Instellingen → Add-ons → Portfolio Tracker → **Herbouwen**
   (niet enkel herstarten — Docker hergebruikt anders de oude laag).

## Daarna, éénmalig

Ga naar **🏢 Activa → 🔗 Koppelingen → 📐 Fondsformule** en klik op
**🔄 Waarnemingen ophalen**.

Die knop legt vanaf nu de al bewaarde waarnemingen opnieuw naast de definitieve
slotkoers. Verschijnt er een melding "🩺 … waarneming(en) … bijgewerkt", dan zat er
inderdaad een intraday-koers in de reeks. In dat geval:

- controleer de gecorrigeerde datum(s) in de tabel eronder;
- **kalibreer je parameters opnieuw** (referentieprijs, eventueel de
  inschrijvingsprijs) als je die eerder op de oude cijfers hebt afgeleid.

Komt er geen zo'n melding, dan was de reeks al correct en hoef je niets te doen.

## Wat je zult zien

- Op een waarnemingsdag (de 15e, of de beursdag ervoor) staat er vóór 18u Parijse
  tijd een regel dat de waarneming van die dag pas na sluiting wordt vastgelegd. De
  waarde van het fonds beweegt die dag gewoon mee met de koers, precies zoals het
  reglement voorschrijft voor de openstaande waarnemingen.
- Op alle andere dagen staat er enkel welke waarneming de volgende is.
  Eerstvolgende: **15-09-2026**, daarna 15-10-2026 en 13-11-2026.
- Onder **📖 Handleiding** staat het nieuwe hoofdstuk 3.10.

## Handmatige waarnemingen

Waarnemingen die je zelf hebt ingevoerd of gecorrigeerd (bron `manual`) worden door
de controlepas niet aangeraakt. Enkel wat de app zelf ophaalde (bron `auto:…`) wordt
hercontroleerd.

## Eén punt dat in de handleiding als beperking staat

De gereconstrueerde grafiek op **📈 Evolutie** werkt met historische koersreeksen die
rechtstreeks bij Yahoo opgehaald worden. Een QS-ISIN heeft daar geen notering, en de
formule wordt op die reeks niet toegepast. Gekoppelde fondsen ontbreken dus in die ene
grafiek. Overal elders — dashboard, portefeuille, fotomoment, fiscale berekening —
tellen ze volledig mee. Dit is bewust niet stilzwijgend gelaten maar in 3.10
opgeschreven; het oplossen ervan is een aparte ingreep.
