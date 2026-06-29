# Changelog

Alle noemenswaardige wijzigingen aan de Portfolio Tracker add-on.

## 0.12.0
- AI-kosten in de zijbalk: de totale AI-kost (en deze maand) staat nu links in de zijbalk.
- Rekeningfilter als multiselect op het dashboard en de portefeuille: selecteer één,
meerdere of (leeg) alle rekeningen tegelijk.
- Compactere overzichten: de overzichten van activa, transacties en dividenden zijn nu
echte tabellen (kolommen/rijen) in plaats van losse regels, met veel minder lege ruimte.
- Bewerken/verwijderen/herschikken gebeurt via een actiebalk onder de tabel.
- Dashboard YTD ↔ all-time: een schakelaar wisselt de overzichtslijn (gerealiseerde W/V,
dividenden, totale meer-/minwaarde) tussen "dit jaar" en "sinds start".
- Oudere transacties: datums vanaf 1/1/2000 zijn nu toegelaten (voorheen kon je niet
verder terug dan ~10 jaar).
- Transactiekosten standaard in EUR in plaats van de valuta van het activum.

## 0.11.0
Dividenden — gedetailleerde invoer van de volledige voorheffingsketen. Naast de
bestaande eenvoudige invoer kun je nu ingeven: ① bruto dividend vóór buitenlandse
bronbelasting, ② buitenlandse bronbelasting, ③ bruto na bronbelasting / vóór Belgische
roerende voorheffing, en ④ netto na alle voorheffingen. De Belgische RV wordt afgeleid
(③ − ④). Elk veld heeft een eigen muntkeuze, en lege velden worden waar mogelijk
automatisch berekend uit de ingevulde velden (zelfde munt). Zo is duidelijk over welk
brutobedrag het gaat en wordt het netto niet langer automatisch verondersteld.
De waarschuwing over niet-ingehouden Belgische roerende voorheffing is verwijderd.
Totalen en het netto per rekening rekenen nu met het werkelijk ontvangen netto (EUR).

## 0.10.0
- Fotomoment (referentiewaarde 31/12/2025) voor de meerwaardebelasting. Voor
stukken die je vóór 2026 kocht, vertrekt de belastbare meerwaarde niet langer van
de werkelijke aankoopprijs, maar van het fotomoment:
  - Ligt de slotkoers op 31/12/2025 hoger dan je aankoopprijs, dan wordt die de
fiscale instapprijs (de winst van vóór 2026 is vrijgesteld).
Ligt ze lager, dan mag je de (hogere) werkelijke aankoopprijs gebruiken, maar
het resultaat wordt tot €0 begrensd (historische minderwaarden zijn niet
aftrekbaar). Die keuze geldt t/m boekjaar 2030; vanaf 2031 telt altijd de
fotomomentwaarde.
  - Een minderwaarde ná het fotomoment blijft aftrekbaar.
  - Stukken gekocht vanaf 2026 gebruiken gewoon de aankoopprijs (FIFO).
  - Werkt voor alle activa; gemengde loten (deels vóór, deels vanaf 2026) worden
per schijf correct behandeld.
- Per activum een fotomomentwaarde (slotkoers 31/12/2025), met een knop om die
automatisch op te halen via Yahoo Finance of handmatig in te vullen — in zowel het
toevoeg- als het bewerkformulier, en zichtbaar in het activa-overzicht.
- Dashboard en belastingpagina tonen nu duidelijk het verschil tussen de
economische winst/verlies en de (lagere) belastbare basis na het fotomoment; de
vrijstelling en de geschatte belasting worden op de fiscale basis berekend.

## 0.9.0
Dividenden per rekening: een dividend wordt nu aan een rekening gekoppeld,
niet enkel aan een activum.
- Het toevoegformulier heeft een rekeningselector.
- In het overzicht kun je filteren per rekening, de rekening per dividend
aanpassen, en bij "alle rekeningen" zie je een netto-uitsplitsing per rekening.
- Keert eenzelfde activum op meerdere rekeningen een dividend uit, dan voer je
dat als aparte lijnen in (het bedrag verschilt toch per aantal aandelen op die
rekening); de globale totalen en de belastingcijfers blijven kloppen.
- Bestaande dividenden krijgen bij de upgrade automatisch de standaardrekening
toegewezen; je kunt ze nadien per stuk herschikken.

## 0.8.0
Meer-/minwaarden over rekeningen heen:
- Het dashboard toont nu een totale meer-/minwaarde (gerealiseerd over alle
jaren + ongerealiseerd), zodat winst uit een verkoop en latere heraankoop
zichtbaar is.
- Selecteer je een rekening met netto-0-positie (bv. een afgesloten rekening),
dan blijven de historiek en gerealiseerde meer-/minwaarden van die rekening
zichtbaar in plaats van een leeg scherm.
- Nieuwe sectie "Gerealiseerde meer-/minwaarden (historiek)" op zowel het
dashboard als de portefeuille, rekening-bewust en over alle jaren. Bij "alle
rekeningen" zie je zo de volledige historiek van een activum, ook wanneer het
op de ene rekening verkocht en op een andere heraangekocht is.
- De fiscale berekening (gerealiseerde W/V per boekjaar, vrijstelling) blijft
zoals het hoort globaal per persoon.

## 0.7.0
- Aandelensplitsingen: nieuwe tab "🔀 Splitsingen" op de Activa-pagina om een
(omgekeerde) splitsing te registreren (bv. NVIDIA 1→10). Transacties van vóór de
splitsdatum worden automatisch omgerekend (aantal × ratio, prijs ÷ ratio); de
kostbasis blijft gelijk en posities/waarde blijven consistent met de
split-gecorrigeerde Yahoo-koersen. Het transactie-overzicht toont nog steeds je
oorspronkelijk ingevoerde waarden.

## 0.6.0
- TOB correcter berekend: het tarief houdt nu rekening met of een ETF/fonds
in België is aangeboden/geregistreerd (FSMA). Een kapitaliserende ETF die niet
in België is aangeboden (bv. een ETC zoals G2XJ.DE) valt nu onder 0,35% i.p.v.
1,32%. Per activum is er een duidelijke aanvinkoptie "In België aangeboden",
en het toepasselijke TOB-tarief wordt in het activumformulier getoond. Ook
obligaties (0,12%) zijn toegevoegd. De plafonds (€1.300 / €1.600 / €4.000)
blijven gelden.
- Transactieformulier:
  - De munt wordt automatisch ingevuld op basis van het gekozen activum.
  - Aantal en prijs starten leeg in plaats van met "1".
  - Na het toevoegen wordt het volledige formulier leeggemaakt en verschijnt een
    bevestiging dat de transactie is toegevoegd.
- Transactie-overzicht: bij het bewerken springt de pagina automatisch naar
boven, naar het bewerkformulier.

## 0.5.0
- Activumnaam i.p.v. ticker op meer plaatsen, makkelijker te herkennen:
- Dashboard: staafdiagram "Ongerealiseerde winst/verlies per positie" toont de naam.
- Portefeuille: de keuzelijst en titel bij "Prijsgeschiedenis" tonen de naam.
- Transacties: keuzelijst bij "Nieuwe transactie" en de naam in elke regel van het overzicht.
- Dividenden: keuzelijst bij "Dividend toevoegen" toont de naam.
Overal in de vorm "Naam (TICKER)".
- Activa: de naam is nu een verplicht veld; in het overzicht is een filter op
naam of ticker bijgekomen.
- Transacties: in het overzicht is de tekstfilter op ticker vervangen door een
keuzelijst "Activum" (op naam), wat tegelijk de naam- en tickerfilter dekt.

## 0.4.2
Foutmelding bij onbekende ticker: als "🔍 Info ophalen via Yahoo Finance" niets vindt, toont de app nu een duidelijke fout (met hint over het beurssuffix) i.p.v. stilletjes standaardwaarden in te vullen.
Ticker corrigeren: in het activum-bewerkformulier kan je nu ook de ticker zelf aanpassen (bv. STMPA → STMPA.PA). De bijbehorende transacties, dividenden, koershistoriek en AI-ratings verhuizen mee, zodat een verkeerde ticker zonder dataverlies te herstellen is.

## 0.4.1
Fix: crash bij het toevoegen van een transactie (st.session_state.pt_input cannot be modified after the widget ... is instantiated). Het koersdoelveld en de AI-knop gebruiken nu een veilig reset-patroon; de transactie verschijnt meteen zonder refresh.

## 0.4.0
- Activa bewerken: bestaande activa kunnen aangepast worden (✏️ in het
overzicht): naam, type, ETF-subtype, munt, beurs en ISIN.
ISIN: activa hebben nu een ISIN-veld; het wordt mee opgehaald en getoond.
- Beurs wordt nu effectief bewaard: voorheen werd de opgehaalde beurs niet
opgeslagen bij automatisch invullen; dat is nu gecorrigeerd.
- Info ophalen vóór opslaan: in het activumformulier vult de knop
"🔍 Info ophalen via Yahoo Finance" naam, munt, type, beurs en ISIN direct in
het formulier in, zodat je ze kunt nakijken en aanpassen vóór je bewaart
(i.p.v. pas achteraf te zien of het juist liep).

## 0.3.2
- verwijderen van deprecated ARM-arch values in config

## 0.3.1
- fix van changelog

## 0.3.0
- **AI-kosten in de app:** het tokengebruik en de geschatte kost per AI-oproep
  worden bijgehouden en getoond op de AI-adviseur-pagina: totaal, deze maand, en
  een uitsplitsing per model en per functie (belastingadvies, marktevaluatie,
  ratings, koersdoel). Richtprijzen medio 2026; de exacte factuur blijft op het
  OpenAI-dashboard.
- **Dividenden — voorheffing-kenmerken:** bij een dividend kan je nu aangeven of
  de bronbelasting (buitenlandse roerende voorheffing) en/of de Belgische
  roerende voorheffing al is ingehouden. Het overzicht waarschuwt voor dividenden
  waarop de Belgische RV nog niet is ingehouden en die je dus mogelijk nog moet
  aangeven.
- **Fix:** `use_container_width` vervangen door `width='stretch'` om de Streamlit-
  deprecation (verwijdering na 2025-12-31) voor te zijn.

## 0.2.1
- **Fix:** scheduler crashte bij het opstarten op `job.next_run_time`
  (`AttributeError`) met nieuwere APScheduler-versies, waardoor de geplande jobs
  (koersophaling, dagelijks belastingadvies, marktevaluaties) niet meer draaiden.
  De volgende runtijd wordt nu veilig bepaald.
- **Fix:** `apscheduler` vastgepind op de 3.x-reeks (`<4.0`) om te vermijden dat
  een herbouw per ongeluk de incompatibele 4.x-API binnenhaalt.

## 0.2.0

- **Transacties bewerken:** bestaande transacties kunnen gecorrigeerd en
  aangevuld worden (✏️ in het overzicht); EUR-bedragen worden herberekend.
- **Algemene rekeningkosten:** kosten die niet aan een aandeel hangen
  (bv. beheerskosten, bewaarloon) via de tab "🏦 Rekeningkosten". Ze verlagen het
  nettorendement, maar niet de meerwaardeberekening of de individuele posities.
- **AI-advies synthese:** synthese van de laatste 9 AI-adviesrondes per ticker
  (Sterk kopen / Kopen / Behouden / Verkopen / Sterk verkopen) met consensus en
  koersdoel op de Portefeuille-pagina.
- **Topadviseur met profiel per rekening:** de AI-adviseur weegt portefeuille,
  macro-economische trends en technologische ontwikkelingen af, afgestemd op een
  instelbaar beleggingsprofiel per rekening (agressief, neutraal, speculatief,
  lange termijn, defensief).
- **Investeringsvolume:** instelbaar bedrag per maand/jaar voor realistische,
  op het budget afgestemde AI-voorstellen.
- **Koersdoel bij transactie:** nieuw koersdoelveld met optionele AI-bepaling;
  het model hiervoor is apart instelbaar.
- **Koersdoel in Portefeuille:** kolommen "Koersdoel" en "Potentieel" (%).

## 0.1.0

- Integratie van rekeningen (multi-rekening/multi-broker), de evolutiepagina met
  historische waardereconstructie, volledige EUR-omrekening op transactiedatum,
  het Belgische huwelijksstelsel (gemeenschap van goederen) en de meerjarige
  opbouw van de vrijstelling.

## 0.0.1

- Basisversie: portefeuillebeheer, FIFO-kostbasis, Belgische
  meerwaardebelasting, TOB en dividenden.