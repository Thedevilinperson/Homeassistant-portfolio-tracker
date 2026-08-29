# Plaatsing 1.8.12

Deze zip bevat alles van 1.8.8 tot en met 1.8.12.

## Wat er in dit pakket zit

| Bestand | Waarom |
|---|---|
| `portfolio_tracker/views/assets.py` | NAV-export: reeks en kolom kiezen, wisknop, waarschuwing bij dubbele maanden (1.8.12); terugzetknop en majoratievoorstel (1.8.11) |
| `portfolio_tracker/database.py` | `delete_official_nav()` (1.8.12) |
| `portfolio_tracker/fcpe_pricing.py` | Berekening van de majorations (1.8.11) |
| `portfolio_tracker/market_data.py` | Dividendhistoriek (1.8.11), historische reeks voor gekoppelde activa (1.8.9), waarneming pas na beurssluiting (1.8.8) |
| `portfolio_tracker/HANDLEIDING.md` en `HANDLEIDING.md` | Hoofdstuk 3.10 aangevuld |
| `portfolio_tracker/config.yaml` | Versie -> 1.8.12 |
| `portfolio_tracker/CHANGELOG.md` | Rubrieken 1.8.8 t/m 1.8.12 |

## Plaatsen

1. Kopieer de bestanden over de bestaande, met behoud van de mappen. Let op de twee
   `HANDLEIDING.md` en op `database.py`, dat nu ook meegaat.
2. Commit en push naar `main` en `master`.
3. In Home Assistant: Instellingen -> Add-ons -> Portfolio Tracker -> **Herbouwen**.

## De vervuilde reeks opruimen

1. Ga naar `Activa -> Koppelingen -> Fondsformule -> Parameters kalibreren`.
2. Onderaan, onder de vergelijkingstabel, staat nu
   **"Alle N ingelezen NAV-regels wissen"**. Klik daarop: de hele reeks van dit fonds
   gaat weg. Je waarnemingen en je parameters blijven staan.
3. Laad de export van Amundi opnieuw op. De app toont nu welke reeksen ze in het
   bestand vindt.
4. Vink alleen de reeks(en) aan die bij dit fonds horen. Staat het ISIN of de naam van
   je fonds in de omschrijving, dan staat die al aangevinkt.
5. Zijn er meerdere getalkolommen, kies dan de kolom met de NAV. De voorbeeldwaarden
   naast elke kolom helpen: het aantal deelbewijzen ziet er anders uit dan een bedrag.
6. Kijk de regel na die zegt hoeveel regels je gaat inlezen en over welke periode.
   Verschijnt er nog een waarschuwing over meerdere waarden per maand, dan zit er nog
   een tweede fonds in je selectie.
7. Pas dan op **Inlezen en kalibreren**.

## Nog iets om na te kijken

In je huidige vergelijking staat de berekende waarde exact op 10,52 voor elke datum tot
en met 14 juni 2024, en pas vanaf 15 juli 2024 loopt ze mee. Dat is geen toeval: de app
geeft exact de inschrijvingsprijs terug voor elke datum op of vóór de aanvangsdatum. Je
opgeslagen **Datum van aanvang** ligt dus ergens tussen 14 juni en 14 juli 2024, terwijl
die voor het fonds van 2022 op 22 december 2022 hoort te staan. Dat is vermoedelijk nog
een restant van de parameterverwisseling. Zet ze recht voor je opnieuw kalibreert,
anders zoekt de kalibratie een referentieprijs die de eerste anderhalf jaar moet
goedmaken.
