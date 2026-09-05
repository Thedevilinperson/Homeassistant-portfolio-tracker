# Plaatsing versie 1.8.19

## Wat zit erin

Zie `CHANGELOG.md` voor het volledige verhaal. Kort samengevat:

1. **Correctie in de aangifte**: dividenden die BRUTO op je rekening kwamen
   (Amundi/FCPE) werden ten onrechte opgegeven als terug te vorderen roerende
   voorheffing. Er is daar nooit iets ingehouden — ze horen bij de ZELF aan te
   geven inkomsten, met 30% verschuldigd.
2. De cash-boeking van een lijn bepaalt voortaan of er RV is ingehouden; die
   regel staat op één plaats en wordt overal gebruikt (invoer, bewerken,
   bulkimport, 'keten herberekenen').
3. Nieuwe kolom **🇧🇪 RV ingeh.** bij 💰 Dividenden, om het per lijn zelf te
   overschrijven.
4. De aangiftetabellen tonen nu de **naam** van het activum naast de ticker,
   plus een kolom **RV ingeh.**
5. Eenmalige herijking van je bestaande dividendlijnen.

## Bestanden in deze zip

```
portfolio_tracker/belgian_tax.py
portfolio_tracker/database.py
portfolio_tracker/views/declaration.py
portfolio_tracker/views/dividends.py
portfolio_tracker/views/common.py
portfolio_tracker/views/tax.py
portfolio_tracker/config.yaml
portfolio_tracker/CHANGELOG.md
PLAATSING-1.8.19.md
```

Enkel deze bestanden zijn gewijzigd; de rest van de add-on blijft ongemoeid.

## ⚠️ Verwacht een LAGER terug te vorderen bedrag

Dit is de belangrijkste vaststelling na plaatsing. Op je schermafdruk stond
€499,80 — het plafond van 30% × €1.666. Dat bedrag was te hoog: het steunde voor
zo'n €474 op voorheffing die de keten had BEREKEND maar die nooit is afgehouden.
Na plaatsing zie je ongeveer **€242**, en verschijnen de Amundi-dividenden bij de
regel "Dividenden waarop geen Belgische roerende voorheffing werd ingehouden" —
waar 30% op verschuldigd is.

Dat is de correctie, geen nieuwe fout. Het verklaart meteen ook waarom het bedrag
vorig jaar en dit jaar identiek leek: de spookvoorheffing duwde de grondslag elk
jaar boven het plafond, dus kwam er telkens hetzelfde maximum uit.

## Database-migratie

Automatisch bij opstart (`database.py:init_db()` → `_backfill_rv_withheld()`),
geen actie nodig:

- `dividends.belgian_rv_withheld` wordt eenmalig herijkt op de cash-boeking:
  `gross_after` / `gross_before` → 0, `net` met RV in de keten → 1, geen RV in de
  keten → 0.
- De migratie markeert zichzelf met de instelling `migr_rv_withheld_from_cash=1`
  en draait daarna nooit meer. Zo blijft een handmatige correctie op een lijn
  overeind bij elke volgende start.

Geen nieuwe kolommen, geen tabelherbouw. Wil je de herijking ooit opnieuw laten
lopen (bv. na een grootschalige correctie van cash-boekingen), zet die instelling
dan op `0` en herstart.

## Plaatsingsstappen (Home Assistant add-on)

1. Kopieer de bestanden hierboven naar dezelfde paden in je add-on-repository
   (overschrijf de bestaande). `PLAATSING-1.8.19.md` hoort in de hoofdmap, naast
   `repository.yaml`.
2. Commit/push naar je repository (`main` én `master`, zoals gebruikelijk).
3. In Home Assistant: Instellingen → Add-ons → Portfolio Tracker →
   **⟳ Herbouwen** (niet enkel herstarten — anders blijft de oude Docker-laag
   hangen en zie je 1.8.19 niet).
4. Neem vóór het herbouwen een reservekopie of noteer de huidige bedragen op de
   🧾 Aangifte-pagina, zodat je het verschil kunt nakijken.

## Controlepunten na plaatsing

- **💰 Dividenden → tabel**: nieuwe kolom **🇧🇪 RV ingeh.** Bij je Amundi-lijnen
  staat ze UIT (cash-boeking = ③ Bruto na bronbelasting), bij je ING-lijnen AAN
  (cash-boeking = ④ Netto). Klopt dat niet voor een lijn, zet het vinkje dan om;
  de lijn wordt daarmee als 🔒 handmatig gemarkeerd en overleeft een
  herberekening.
- **🧾 Aangifte → "Terug te vorderen roerende voorheffing"**: het bedrag is
  gedaald en de Amundi-lijnen staan er niet meer tussen. De opbouw toont nu ook
  "Aandelendividend zonder ingehouden RV" en "Ongebruikte vrijstellingsruimte".
- **🧾 Aangifte → "Dividenden waarop geen Belgische RV werd ingehouden"**: hier
  staan de Amundi-lijnen nu wél, met daaronder een opbouw inclusief het
  verschuldigde bedrag bij 30%.
- **Onderliggende lijnen**: kolom **Naam** naast **Activum**, en een kolom
  **RV ingeh.**
- **Onderaan de aangifte** staat een notitie die benoemt hoeveel lijnen bruto
  werden uitbetaald, op welke rekeningen, en welk bedrag de keten ten onrechte
  als voorheffing rekende. Loop die één keer na tegen je rekeninguittreksels.
- **🧾 Belgische Belasting → Dividendfiscaliteit**: "In aanmerking komende
  dividenden" telt nu alleen nog de dividenden mét ingehouden RV, met een
  aparte lijn over het bruto uitbetaalde deel.

## Aandachtspunt voor je aangifte

Blijft er vrijstellingsruimte ongebruikt omdat er op je bruto uitbetaalde
aandelendividenden niets is ingehouden, dan meldt de app dat. Codes 1437/2437
geven *ingehouden* voorheffing terug; of de vrijstelling van art. 21, 14° WIB
ook toepasbaar is op dividenden die je zelf aangeeft onder 1444/2444, is
betwiste materie. De app rekent bewust conservatief — leg dat punt voor aan je
boekhouder voor je de aangifte indient.

## Terugdraaien

Zet de vorige versie van de acht bestanden terug en herbouw. De migratie is
niet omkeerbaar via de bestanden alleen: wil je de oude (foute) vlaggen terug,
draai dan onder ⚙️ Instellingen → databasebeheer een reservekopie van vóór de
plaatsing terug.
