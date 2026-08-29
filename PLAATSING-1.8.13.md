# Plaatsing 1.8.13

Deze zip bevat alles van 1.8.8 tot en met 1.8.13.

## Wat er in dit pakket zit

| Bestand | Waarom |
|---|---|
| `portfolio_tracker/views/assets.py` | Kalibratie op alle NAV-datums, eerlijke foutmelding (1.8.13); NAV-export selecteren (1.8.12); terugzetknop en majoratievoorstel (1.8.11) |
| `portfolio_tracker/market_data.py` | `fcpe_spots()`: koers van de onderliggende waarde op elke NAV-datum (1.8.13) |
| `portfolio_tracker/database.py` | `delete_official_nav()` (1.8.12) |
| `portfolio_tracker/fcpe_pricing.py` | Berekening van de majorations (1.8.11) |
| `portfolio_tracker/HANDLEIDING.md` en `HANDLEIDING.md` | Hoofdstuk 3.10 aangevuld |
| `portfolio_tracker/config.yaml` | Versie -> 1.8.13 |
| `portfolio_tracker/CHANGELOG.md` | Rubrieken 1.8.8 t/m 1.8.13 |

## Plaatsen

1. Kopieer de bestanden over de bestaande, met behoud van de mappen.
2. Commit en push naar `main` en `master`.
3. In Home Assistant: Instellingen -> Add-ons -> Portfolio Tracker -> **Herbouwen**.

## Daarna: het fonds van 2024 kalibreren

De 22 NAV-regels die je net ingelezen hebt, zijn de juiste — je hoeft ze niet te
wissen. Klik gewoon opnieuw op **Inlezen en kalibreren**.

Kijk vóór je kalibreert wel deze drie dingen na, want ze bepalen het resultaat meer dan
de referentieprijs zelf:

1. **Aanvangsdatum (Date de Commencement).** Ligt die ná je NAV-reeks, dan is de
   berekende waarde overal gelijk aan de inschrijvingsprijs en valt er niets te passen.
   De app zegt dat nu ook met zoveel woorden.
2. **Inschrijvingsprijs.** Staat er nu 10,52, en dat is de waarde van het fonds van
   2022. Voor de jaargang 2024 hoort daar een ander bedrag te staan. Neem in je
   NAV-export bij voorkeur de oprichtingsdag mee: die NAV is per reglement exact de
   inschrijvingsprijs, en dan pint de app ze zelf vast.
3. **Waarnemingsdag.** Je NAV wordt op de 25e gepubliceerd, terwijl de waarnemingen nu
   op de 15e staan. Dat kan kloppen — de waarderingsdag van de beheerder en de Relevé
   uit het reglement zijn twee verschillende dingen — maar controleer het in het
   reglement van je jaargang. Staat er een andere dag, pas dan de waarnemingsdag aan,
   sla op, en haal de waarnemingen opnieuw op. De regels van de oude reeks worden dan
   gemeld met een opruimknop erbij.

Ook α (nu 24) en de eindvervaldag horen uit het reglement van de jaargang 2024 te komen,
niet uit dat van 2022.
