# Plaatsing 1.8.9

Deze zip vervat alles van 1.8.8 én 1.8.9. Heb je 1.8.8 nog niet geplaatst, dan kun je
die overslaan en meteen hiermee verder — er is niets dat je moet overslaan of in
volgorde moet doen.

## Wat er in dit pakket zit

Enkel de gewijzigde bestanden. Behoud de mappenstructuur — de paden zijn relatief aan
de wortel van de repo.

| Bestand | Waarom |
|---|---|
| `portfolio_tracker/market_data.py` | Historische reeks voor gekoppelde activa (1.8.9); waarneming pas na beurssluiting + controlepas (1.8.8) |
| `portfolio_tracker/views/assets.py` | Sync-knop draait de controlepas mee, meldingen blijven zichtbaar (1.8.8) |
| `portfolio_tracker/fcpe_pricing.py` | Ongebruikte `monthly_reading_dates()` geschrapt (1.8.8) |
| `portfolio_tracker/HANDLEIDING.md` | Hoofdstuk 3.10 over gekoppelde koersen, bijgewerkt voor 1.8.9 |
| `HANDLEIDING.md` (root) | Identiek aan die van de add-on |
| `portfolio_tracker/config.yaml` | Versie 1.8.7 → 1.8.9 |
| `portfolio_tracker/CHANGELOG.md` | Rubrieken 1.8.8 en 1.8.9 |

## Plaatsen

1. Kopieer de bestanden over de bestaande, met behoud van de mappen. Let op de twee
   `HANDLEIDING.md`: één in de root, één in `portfolio_tracker/`. Ze zijn identiek.
2. Commit en push naar `main` én `master`.
3. In Home Assistant: Instellingen → Add-ons → Portfolio Tracker → **Herbouwen**
   (niet enkel herstarten — Docker hergebruikt anders de oude laag).

## Daarna, éénmalig (uit 1.8.8)

Ga naar **🏢 Activa → 🔗 Koppelingen → 📐 Fondsformule** en klik op
**🔄 Waarnemingen ophalen**.

Die knop legt de al bewaarde waarnemingen opnieuw naast de definitieve slotkoers.
Verschijnt er een melding "🩺 … waarneming(en) … bijgewerkt", dan zat er een
intraday-koers in de reeks. In dat geval:

- controleer de gecorrigeerde datum(s) in de tabel eronder;
- **kalibreer je parameters opnieuw** als je die eerder op de oude cijfers afleidde.

Komt er geen zo'n melding, dan was de reeks al correct.

## Wat je nu op 📈 Evolutie zult zien

Je gekoppelde fondsen tellen mee in de gereconstrueerde historiek. Vóór 1.8.9 vielen
ze daar volledig uit: de grafiek toonde een portefeuille zonder dat fonds, terwijl het
dashboard, de portefeuillepagina en de fiscale berekening het wel meetelden. De
totalen op die pagina zullen dus hoger liggen dan wat je gewend was — dat is de
correctie, geen nieuwe fout.

De reeks wordt gerekend, niet opgehaald: per dag de formule, en bij de fondsformule
met de waarnemingen die op díé dag al bestonden. De koersreeks van de onderliggende
waarde wordt daarvoor zonder dividendcorrectie opgehaald, want het reglement rekent op
de werkelijke slotkoers.

Twee dingen om te weten:

- De grafiek op die pagina heeft een cache van dertig minuten. Zie je de wijziging niet
  meteen, wacht dan even of gebruik **Rerun** in het menu rechtsboven.
- Verander je een parameter of corrigeer je een waarneming, dan werkt dat meteen door
  in de berekende reeks: die wordt bewust niet apart gecachet.

## Waar je het aan kunt nakijken

Neem één datum uit de grafiek en vergelijk met de waarde die het paneel
`📐 Fondsformule` voor diezelfde datum toont. Ze horen exact gelijk te zijn — beide
rekenen sinds 1.8.9 met dezelfde parameters, uit dezelfde bron.
