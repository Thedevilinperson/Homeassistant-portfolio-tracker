# Plaatsing versie 1.8.18

## Wat zit erin

Zie `CHANGELOG.md` voor het volledige overzicht. Kort samengevat:

1. Dividendkalender: één lijn per rekening in plaats van een opgeteld aantal.
2. Dividendkalender: geen lijnen meer zonder open positie of vóór je eerste aankoop
   (enkel bij scope 'In portefeuille' — 'Alles (ook suggesties)' blijft ongewijzigd).
3. Nieuw vinkje **Geen dividend** bij 🏢 Activa → 📋 Overzicht, voor fondsen die nooit
   uitkeren (bv. FCPE Multiple).
4. Nieuwe knop om een kalenderlijn **handmatig als geboekt** te markeren.
5. Dividendvrijstelling/FBB-instellingen verhuisd naar een eigen tab **💰 Dividenden**
   (voorheen onderaan bij 🧾 Meerwaardebelasting).
6. Verificatie van de terug te vorderen roerende voorheffing (€499,80-plafond) —
   geen codewijziging, de bestaande berekening bleek correct.

## Bestanden in deze zip

```
portfolio_tracker/database.py
portfolio_tracker/config.yaml
portfolio_tracker/CHANGELOG.md
portfolio_tracker/views/common.py
portfolio_tracker/views/dividends.py
portfolio_tracker/views/assets.py
portfolio_tracker/views/settings.py
```

Enkel deze 7 bestanden zijn gewijzigd; de rest van de add-on blijft ongemoeid.

## Database-migratie

Automatisch bij opstart (`database.py:init_db()`), geen actie nodig:

- `assets.no_dividend` (INTEGER, default 0) — nieuwe kolom.
- `dividend_calendar.manual_booked` (INTEGER, default 0) — nieuwe kolom.

Beide zijn `ALTER TABLE ... ADD COLUMN` met een `_column_exists`-check ervoor, dus
veilig te herhalen en zonder impact op bestaande data.

## Plaatsingsstappen (Home Assistant add-on)

1. Kopieer de 7 bestanden hierboven naar dezelfde paden onder
   `portfolio_tracker/` in je add-on-repository (overschrijf de bestaande).
2. Commit/push naar je repository (`main` én `master`, zoals gebruikelijk).
3. In Home Assistant: Instellingen → Add-ons → Portfolio Tracker →
   **⟳ Herbouwen** (niet enkel herstarten — anders blijft de oude Docker-laag
   hangen en zie je 1.8.18 niet).
4. Na het herbouwen: controleer onderaan de instellingenpagina dat de versie
   **1.8.18** toont, en dat de nieuwe tab **💰 Dividenden** verschijnt.

## Controlepunten na plaatsing

- 🏢 Activa → 📋 Overzicht: kolom **Geen dividend** is zichtbaar naast
  **Div=aandeel**. Vink dit aan voor je ENGIE FCPE Multiple-fonds(en) als die
  geen dividend uitkeren (de Classic/Liberty-varianten kunnen dat wel doen —
  controleer per fonds).
- 💰 Dividenden → 📅 Kalender: een activum op twee rekeningen toont nu twee
  aparte lijnen. Filter 'In portefeuille' + 'Voorbije' mag geen lijnen meer
  tonen voor activa die je niet (meer) aanhoudt.
- Nieuwe knop **✅ Manueel markeren als geboekt / niet geboekt** onder de tabel
  werkt en overleeft een pagina-ververs.
- ⚙️ Instellingen → **💰 Dividenden**: de vrijstelling en FBB-instellingen staan
  hier nu, met dezelfde waarden als voorheen (niets gaat verloren — enkel de
  tab is verplaatst).
- 🧾 Aangifte: het bedrag "Terug te vorderen roerende voorheffing" verandert
  NIET door deze plaatsing — die berekening was al correct (zie changelog).

## Terugdraaien

Zet de 7 bestanden terug naar de 1.8.17-versie en herbouw opnieuw. De twee
nieuwe kolommen (`no_dividend`, `manual_booked`) blijven dan ongebruikt in de
database staan, zonder effect op de rest van de app.
