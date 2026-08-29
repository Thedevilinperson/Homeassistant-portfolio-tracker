# Plaatsing 1.8.14

Deze zip bevat alles van 1.8.8 tot en met 1.8.14.

## Wat er in dit pakket zit

| Bestand | Waarom |
|---|---|
| `portfolio_tracker/views/portfolio.py` | Melding onder de totalen: posities zonder koers tellen niet mee (1.8.14) |
| `portfolio_tracker/views/assets.py` | Overzicht van posities zonder koers en zonder koppeling (1.8.14); kalibratie op alle NAV-datums (1.8.13); NAV-export selecteren (1.8.12); terugzetknop en majoratievoorstel (1.8.11) |
| `portfolio_tracker/market_data.py` | `fcpe_spots()` (1.8.13), dividendhistoriek (1.8.11), historische reeks voor gekoppelde activa (1.8.9) |
| `portfolio_tracker/database.py` | `delete_official_nav()` (1.8.12) |
| `portfolio_tracker/fcpe_pricing.py` | Berekening van de majorations (1.8.11) |
| `portfolio_tracker/HANDLEIDING.md` en `HANDLEIDING.md` | Hoofdstuk 3.10 aangevuld |
| `portfolio_tracker/config.yaml` | Versie -> 1.8.14 |
| `portfolio_tracker/CHANGELOG.md` | Rubrieken 1.8.8 t/m 1.8.14 |

## Plaatsen

1. Kopieer de bestanden over de bestaande, met behoud van de mappen. Let op de twee
   bestanden in `views/`.
2. Commit en push naar `main` en `master`.
3. In Home Assistant: Instellingen -> Add-ons -> Portfolio Tracker -> **Herbouwen**.

## Daarna: de twee ontbrekende koppelingen instellen

Ga naar `Activa -> Koppelingen`. Bovenaan staat nu welke posities geen koers en geen
koppeling hebben. Op basis van je export zijn dat er twee:

| Fonds | Aantal |
|---|---|
| LINK CLASSIC 2024 (C) — QS0009135912 | 224,23 |
| LINK CLASSIC (C) — QS0009103829 | 241,02 |

Beide zijn Classic-fondsen, dus 1:1 op het aandeel — net als je LINK CLASSIC 2022 en
LINK LIBERTY, die al gekoppeld zijn.

Open `Afgeleide koers`, vink het filter uit zodat de volledige lijst verschijnt, kies
het fonds, en vul in:

- Onderliggende waarde: **Engie SA (ENGI.PA)**
- Basisbedrag: **0**
- Multiplicator: **1**
- Referentiekoers: **0**
- Ondergrens: **uit**

Opslaan, en herhalen voor het tweede fonds. De koers verschijnt meteen; verversen is
niet nodig.

Bij een koers van 24,50 euro komt daar ongeveer 5.493 euro bij voor CLASSIC 2024 en
5.905 euro voor CLASSIC (C) — samen zo'n 11.400 euro die nu in je totalen ontbreekt.
Controleer wel eerst of die twee inderdaad 1:1 zijn volgens hun reglement; is er een
hefboom of een gegarandeerd bedrag mee gemoeid, dan hoort het bij de fondsformule en
niet bij de afgeleide koers.
