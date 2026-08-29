# Plaatsing 1.8.11

Deze zip bevat alles van 1.8.8 tot en met 1.8.11. Wat je nog niet geplaatst had, zit
erbij.

## Wat er in dit pakket zit

| Bestand | Waarom |
|---|---|
| `portfolio_tracker/views/assets.py` | Terugzetknop en majoratievoorstel (1.8.11); sleutel per activum, waarschuwingen (1.8.10) |
| `portfolio_tracker/fcpe_pricing.py` | Berekening van de majorations en het eerste rechtgevende jaar (1.8.11) |
| `portfolio_tracker/market_data.py` | Dividendhistoriek ophalen (1.8.11); historische reeks voor gekoppelde activa (1.8.9); waarneming pas na beurssluiting (1.8.8) |
| `portfolio_tracker/HANDLEIDING.md` | Hoofdstuk 3.10 aangevuld |
| `HANDLEIDING.md` (root) | Identiek aan die van de add-on |
| `portfolio_tracker/config.yaml` | Versie → 1.8.11 |
| `portfolio_tracker/CHANGELOG.md` | Rubrieken 1.8.8 t/m 1.8.11 |

## Plaatsen

1. Kopieer de bestanden over de bestaande, met behoud van de mappen. Let op de twee
   `HANDLEIDING.md`: één in de root, één in `portfolio_tracker/`.
2. Commit en push naar `main` én `master`.
3. In Home Assistant: Instellingen → Add-ons → Portfolio Tracker → **Herbouwen**.

## Belangrijk: de terugzetknop werkt niet met terugwerkende kracht

De knop kan alleen terugzetten wat de app zélf bewaard heeft, en dat begint pas bij de
eerste opslag ná deze versie. De overschrijving die je gisteren opliep, kan er dus niet
mee ongedaan gemaakt worden. Daarvoor blijft de weg:

- terugzetten uit een back-up van vóór die bewerking
  (`⚙️ Instellingen → 🗃️ Data → 💾 Back-up en herstel`), of
- de parameters van het 2022-fonds met de hand herstellen: α 16, referentieprijs
  13,1403, inschrijvingsprijs 10,52, 60 waarnemingen, dag 15, eerste waarnemingsmaand
  januari 2023, aanvang 22-12-2022, eindvervaldag 15-12-2027, rendement 1,5 % per jaar
  en 7,73 % op vervaldag.

Vanaf die eerste opslag is elke volgende vergissing wél één klik terug te draaien.

## De majoraties laten voorstellen

Onder het majoratieveld zit `🌐 Majoraties voorstellen uit de dividendhistoriek`.

1. Controleer **Aandelen per deelbewijs** (10) en **Majoration** (0,10). Ze staan in het
   reglement en kunnen per jaargang verschillen.
2. Klik op `🔎 Dividenden ophalen en voorstellen`. De regel eronder zegt vanaf welk jaar
   er recht op bestaat, berekend uit je aanvangsdatum.
3. Kijk de tabel na. 🆕 = nog niet ingevuld, ✅ = klopt met wat er staat, ⚠️ = wijkt af
   van jouw regel.
4. `➕ Die N regel(s) toevoegen` vult alleen de nieuwe regels aan. Daarna nog steeds
   `💾 Opslaan en activeren` klikken.

Bekijk de voorstellen echt als voorstellen. Yahoo geeft de **ex-datum**, terwijl de
beheerder de betaaldatum in zijn afrekening zet — die kunnen een dag of enkele dagen
verschillen. En keert ENGIE in een jaar zowel een interim- als een slotdividend uit, dan
verschijnen die allebei, terwijl je afrekening er misschien maar één telt. Een ⚠️ is een
reden om na te kijken, niet om jouw cijfer te vervangen: jouw regel komt uit de
afrekening, het voorstel uit een koersdatabank.

## Nakijken achteraf

De kalibratie tegen de officiële NAV is de scherpste controle op je majoraties. Ontbreekt
er één, dan loopt de berekende waarde vanaf die datum blijvend onder de officiële NAV, en
dat zie je meteen in de vergelijkingstabel.
