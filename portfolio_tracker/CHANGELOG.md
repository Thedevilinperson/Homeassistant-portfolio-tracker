# Changelog

Alle noemenswaardige wijzigingen aan de Portfolio Tracker add-on.

## 0.21.0
- Bulk-import via Excel (⚙️ Instellingen → 🗃️ Data). Laad transacties, dividenden en
rekeningkosten in bulk op:
  - Download een ingevulde Excel-template met drie databladen (Transacties, Dividenden,
Kosten), voorbeeldrijen en een instructieblad.
  - Upload het ingevulde bestand: de app valideert elke rij, toont een samenvatting en de
overgeslagen rijen met reden, en importeert pas na bevestiging.
  - Onbekende activa worden automatisch aangemaakt (vul naam/type/munt in voor een correcte TOB).
TOB en EUR-omrekening gebeuren automatisch (historische wisselkoers indien geen fx_koers
opgegeven); de dividendketen wordt aangevuld zoals in het formulier; performance shares
worden ondersteund (kolommen performance_share + personenbelasting_eur).
- Simulatiemodule meerwaardebelasting (nieuwe pagina 🧮 Simulatie). Schat vooraf in hoe de
Belgische meerwaardebelasting uitdraait:
  - Een bewerkbare tabel met je huidige posities; geef per positie een te verkopen aantal
(geheel of gedeeltelijk) en een verkoopprijs op, en optioneel een heraankoop (aantal + prijs).
  - De simulatie berekent de gerealiseerde meerwaarde, de belastbare basis na de jaarlijkse
vrijstelling (incl. opbouw en reeds gerealiseerde winst dit jaar), de extra meerwaardebelasting
(10%), de TOB op verkopen én heraankopen, en het netto resultaat na belasting + TOB.
  - Het fotomoment (slotkoers 31/12/2025) wordt correct toegepast op loten van vóór 2026.
  - Er wordt niets opgeslagen of uitgevoerd — het is een zuivere doorrekening.
- requirements: openpyxl toegevoegd (nodig voor het lezen/schrijven van Excel).

## 0.20.1
- Bugfix: vervangen van de uitgefaseerde st.components.v1.html (scroll-naar-boven bij het openen van een bewerkformulier) — die werd na 2026-06-01 verwijderd en veroorzaakte waarschuwingen in de log. Het bewerkformulier toont nu een duidelijke banner i.p.v. de JS-scroll. Zijbalktekst over de AI-planning bijgewerkt naar het nieuwe dagelijkse advies.
- Bugfix: in de overzichten van transacties, activa en dividenden gaf een rijselectie na het filteren soms een IndexError (de bewaarde selectie wees buiten de kortere lijst). Een buiten bereik vallende selectie wordt nu genegeerd (centraal én op elke oproepplaats).

## 0.20.0
- AI-privacymodus (nieuw). In ⚙️ Instellingen → AI kies je hoeveel data naar OpenAI gaat:
  - Uit — volledige data (tickers + bedragen), zoals voorheen.
  - Bedragen verbergen — enkel gewichten in %, geen eurobedragen; tickers blijven.
  - Volledig anoniem — ook tickers en namen worden vervangen door POS1, POS2, ...; de
ratings worden achteraf weer aan je echte aandelen gekoppeld. Het advies blijft bruikbaar
maar is iets minder specifiek.
Daarnaast kun je elke AI-functie apart in- of uitschakelen (maandelijks belastingadvies,
dagelijks portefeuilleadvies). Een uitgeschakelde functie doet geen enkele AI-oproep.
- AI-advies geherstructureerd. De drie losse markt-evaluaties per dag (opening/middag/slot)
zijn vervangen door één volledig portefeuilleadvies per werkdag (18:00). Dat ene advies
levert zowel een tekstadvies als de koop/houden/verkoop-ratings. Die ratings voeden de
synthese-tabellen op de 💼 Portefeuille-pagina, en het tekstadvies verschijnt daar nu ook
(uitklapbaar) naast de tabel. Het maandelijkse belastingadvies blijft op de 🤖 AI Advisor-pagina.
- De 🤖 AI Advisor-pagina heeft nu twee tabbladen: Belastingoptimalisatie (maandelijks) en
Dagelijks portefeuilleadvies, met telkens een knop om meteen te genereren.
- Bugfix: de knop "Naar AI Advisor" (vanuit dashboard/portefeuille) gaf een foutmelding door
de manier waarop de paginakeuze werd gewijzigd. De navigatie gebeurt nu via een tussenstap
zodat Streamlit geen widget-fout meer werpt.


## 0.19.0
- Volwaardig cash-grootboek (nieuwe pagina 💶 Cash). Per rekening wordt een cashpositie
bijgehouden:
  - Stortingen (cash in) en opnames (cash out) geef je handmatig in.
  - Aankopen (− incl. kosten en TOB), verkopen (+ netto), dividenden (+ netto) en
rekeningkosten (−) worden automatisch uit je bestaande data afgeleid.
  - Beschikbare cash = stortingen − opnames + verkopen − aankopen + dividenden −
rekeningkosten. Dit cijfer verschijnt ook op het dashboard en de portefeuille.
  - Een volledig chronologisch grootboek toont elke beweging met een lopend saldo per
rekening; handmatige stortingen/opnames kun je verwijderen (met bevestiging).
- Performance shares en cash. Een toekenning (vesting) kost geen brokergeld en telt in
de cashpositie voor €0 — anders dan een gewone aankoop die cash afroomt. De personenbelasting
wordt doorgaans via je loon ingehouden en is dus géén beweging op je beleggingsrekening;
betaalde je ze tóch vanaf de rekening, dan boek je dat als een opname. Bij latere verkoop
komt de cash gewoon binnen.
Geld uit het systeem halen is in België geen belastbaar feit (de meerwaardebelasting valt op
de verkoop); een opname verlaagt enkel je beschikbare cash.
- Beschikbare cash verschijnt nu ook als regel op het dashboard en de portefeuille (rekening-bewust).

## 0.18.0
- Performance shares — reële winst-zienswijze. Het netto resultaat van performance shares
is nu de reële winst: huidige waarde − betaalde personenbelasting. De toekenningswaarde telt
niet langer als kost (je investeerde in feite enkel de betaalde belasting). De dashboard-toggle
schakelt tussen deze reële zienswijze (standaard) en de zuivere meerwaarde t.o.v. de
toekenningswaarde. De meerwaardebelasting zelf blijft op de kostbasis (toekenningswaarde) berekend.
- Bestaande transacties omvormen tot performance shares. In het bewerkformulier van een
transactie kun je nu "🎁 Is een toekenning" aanvinken en de personenbelasting (% of exact bedrag)
ingeven; de TOB wordt dan op €0 gezet. Handig om reeds ingevoerde aandelen alsnog correct te markeren.


## 0.17.0
- Bevestiging bij verwijderen. De wis-knoppen in de overzichten van transacties, activa en
dividenden vragen nu eerst een expliciete bevestiging (met annuleren). Eén klik wist dus niet
langer onmiddellijk data — extra belangrijk bij "Wis (incl. transacties)" op een activum.
- Performance shares (toekenning / vesting). Bij het toevoegen van een aankoop kun je nu
"🎁 Performance shares" aanvinken. Je voert het aantal en de koers op de toekenningsdatum in:
die waarde wordt de kostbasis voor de meerwaarde (je betaalde er al personenbelasting op), er
wordt géén TOB aangerekend en er is geen cash-uitgave.
- Personenbelasting als apart gegeven. Bij een toekenning geef je het marginale tarief
(± 53,5%) of een exact bedrag in; dit wordt apart bijgehouden, los van de broker-/beurskosten.
- Dashboard-toggle personenbelasting. Wanneer er performance shares zijn, verschijnt op het
dashboard een schakelaar om de invloed van de betaalde personenbelasting op het netto resultaat
aan of uit te zetten (zowel in het staafdiagram als in het totaal). De meerwaardebelasting zelf
blijft ongewijzigd berekend op de kostbasis (toekenningswaarde).
- De resultaattabel per activum (portefeuille) toont nu ook een kolom "Personenbel." en verrekent
die in het netto resultaat.

## 0.16.0
overgeslagen versienummer, anders werd AI gek

## 0.15.0
- Dashboard — AI-kooptips i.p.v. lange tekst: het AI-blok toont nu enkel de aandelen met
een koopadvies (sterk kopen / kopen), zonder de uitleg, plus een knop "➡️ Naar AI Advisor".
- Dashboard — advieswijzigingen: toont voor welke aandelen het koop/houden/verkoop-advies
is opgewaardeerd (🔺) of afgewaardeerd (🔻) sinds de vorige adviesronde.
- Dashboard — staafdiagram houdt nu rekening met dividenden en kosten: de balk per activum
toont het netto resultaat = ongerealiseerde + gerealiseerde W/V + ontvangen dividenden − de
aan het aandeel gelinkte kosten (transactiekosten + TOB), met de opsplitsing in de tooltip.
- Portefeuille — AI-advies bij minder dan 9 rondes: de synthese en de AI-advieskolommen
tonen nu meteen iets, ook met 1–8 adviesrondes (titel toont het werkelijke aantal). Een
tickermatch-correctie zorgt ervoor dat ratings voor Europese tickers (bv. VWCE.DE) ook
echt worden opgeslagen wanneer de AI het basis-symbool (VWCE) teruggeeft.
- Portefeuille — wijzigingssymbool: 🔺/🔻 naast het advies wanneer het sinds de vorige
ronde bullisher/bearisher werd.
- Portefeuille — herordening: "Totaal resultaat per activum" staat nu bovenaan, dan de
open posities, dan de gerealiseerde historiek, dan de AI-synthese en de prijsgeschiedenis.
- De resultaattabel toont nu ook dividenden, kosten en het netto resultaat per activum.
- Portefeuille — netto dividenden (all-time): de KPI "Netto dividenden" toont nu de
all-time waarde (rekening-bewust) i.p.v. enkel het lopende jaar (toonde 0 als de dividenden
in een ander jaar geboekt waren).

## 0.14.0
- AI-belastingadvies nu maandelijks (i.p.v. dagelijks) — de scheduler genereert het
advies op de 1e van de maand.
- Maandelijkse AI-prijsverversing: een scheduler zoekt maandelijks de actuele prijzen
van de AI-modellen op en past ze indien nodig aan. De modelprijzen staan nu in de
database (instelbaar), met een knop "💲 Ververs nu" en een prijzentabel in het
- AI-kostenpaneel. Ongeldige/onwaarschijnlijke prijzen worden genegeerd.
- ISIN-fallback voor Europese listings: bij het ophalen van info (.BR/.DE e.d.) worden
nu meerdere bronnen geprobeerd om de ISIN te vinden. Lukt het niet, dan verschijnt een
duidelijke melding om de ISIN handmatig in te vullen (Yahoo geeft die niet altijd mee).
- TOB-ingangsdatum: transacties vóór een instelbare datum krijgen geen TOB. Standaard
1/1/2017 — sinds dan zijn Belgische beleggers via een buitenlandse tussenpersoon
TOB-plichtig. Aanpasbaar via ⚙️ Instellingen → TOB.
- TOB-FX-correctie: de TOB wordt nu berekend op de EUR-tegenwaarde van de transactie
in plaats van op het bedrag in vreemde munt. Dat lost de afwijking op bij historische
aankopen in USD e.d. (bv. Anavex: €0,34 i.p.v. €0,37). Let op: bestaande, eerder
ingevoerde transacties behouden hun oude TOB-waarde — corrigeer ze eventueel via bewerken.
- W/V-indicator + AI-advies in de historiektabellen: de tabel "Totaal resultaat per
activum" en de gerealiseerde-historiektabel tonen nu een 🟢/🔴-bol voor winst/verlies,
en de resultaattabel toont ook het AI-advies (kopen/houden/verkopen).
- Klikbare rijselectie: in de overzichten van activa, transacties en dividenden klik je
nu rechtstreeks op een rij in de tabel om ze te bewerken, verwijderen of te verplaatsen
(de aparte keuzelijst is vervangen).

## 0.13.1
Fix: het dashboard gaf een fout bij een netto gerealiseerd verlies (de
vrijstellings-indicator kreeg een negatieve waarde). De voortgangsbalk wordt nu
correct afgeklemd op 0–100%.

## 0.13.0
- Totaal resultaat per activum, over de rekeningen heen. De gerealiseerde winst/verlies
van een activum wordt nu opgeteld over álle geselecteerde rekeningen (niet langer per
rekening apart) en gecombineerd met de lopende ongerealiseerde W/V:
  - Dashboard: drie aparte cijfers — totale ongerealiseerde W/V, totale gerealiseerde
W/V en de som (totale W/V) — over de geselecteerde rekeningen. Het staafdiagram toont nu
per activum de totale W/V (ongerealiseerd + gerealiseerd), met de opsplitsing in de tooltip.
  - Portefeuille: een nieuwe tabel "Totaal resultaat per activum" met per activum de
ongerealiseerde W/V, de gerealiseerde W/V en het totaal — inclusief activa die op de ene
rekening volledig verkocht en op een andere heraangekocht zijn.

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