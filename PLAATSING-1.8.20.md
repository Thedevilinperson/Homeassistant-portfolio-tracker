# Plaatsing 1.8.20 — koers in de munt van het activum

## Gewijzigde bestanden
| Bestand | Wat |
|---|---|
| `portfolio_tracker/market_data.py` | Notering kiezen volgens de munt van het activum (koers, historiek, fotomoment, dividenden, marktstatus) |
| `portfolio_tracker/views/assets.py` | Bronnen diagnose toont munt per notering en de keuze van de app |
| `portfolio_tracker/config.yaml` | Versie 1.8.20 |
| `portfolio_tracker/CHANGELOG.md` | Changelog |

Geen databasemigratie nodig.

## Plaatsen
1. Kopieer de bestanden naar dezelfde paden in de repository en push naar GitHub.
2. Home Assistant → Add-ons → Portfolio Tracker → **Herbouwen** (geen gewone herstart).

## Controleren
1. Activa beheren → 🔬 Bronnen diagnose → Global X Genomics → *Diagnose uitvoeren*.
   - Je ziet alle Yahoo-noteringen met hun munt; de EUR-notering (verwacht: GNOM.MI) staat
     met 👉 als gekozen, GNOM.L (USD) met ⚠️.
2. Dashboard: na de volgende koersverversing (max. 5 min) staat GNOM in **EUR**, rond de
   koers die DEGIRO op Euronext Milan toont.
3. Statuspagina: eventueel één info-melding "Notering aangepast aan de munt van het
   activum: GNOM.L (USD) → GNOM.MI". Dat is verwacht, geen tickerwijziging.

## Goed om te weten
- Kent Yahoo geen EUR-notering, dan neemt de app de eerste andere bron in EUR (onvista
  staat eerst). Pas als niemand EUR levert, wordt de USD-koers gebruikt en omgerekend.
- Andere activa waarbij ooit dezelfde fout speelde (notering in een andere munt dan het
  activum), corrigeren zich automatisch. Hun fotomomentwaarde en historiek kunnen
  daardoor licht wijzigen — dat is de correctie.
