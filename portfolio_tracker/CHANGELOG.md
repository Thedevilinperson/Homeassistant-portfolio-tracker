# Changelog

Alle noemenswaardige wijzigingen aan de Portfolio Tracker add-on.

## 0.41.0
Euronext ontsleuteld (punt 6, optie 3). Euronext Live versleutelt zijn AJAX-antwoorden nu als
{"ct": "..."} (AES-CBC met een vaste sleutel + IV uit hun JavaScript). De app ontsleutelt dat nu
server-side, met een zelfherstellende sleutelaanpak.

**Ontsleuteling.** De {"ct": ...}-envelope wordt herkend op alle drie de Euronext-endpoints
(detailed quote, chartdata én de zoeker/MIC-resolutie) en met AES-CBC/PKCS7 ontsleuteld voor de
bestaande parsers ze zien. Zo werkt Euronext weer als koersbron — en straks als basis voor de
FSMA-status (punt 9).

**Zelf-afstemmende sleutel.** In plaats van een sleutel hard te coderen (die breekt bij rotatie),
haalt de app de kandidaat-strings uit de live JS-bundels en zoekt het (sleutel, IV)-paar dat een
ECHT versleuteld staal correct ontcijfert. Zo vindt hij de juiste sleutel zonder dat die vooraf
gekend moet zijn, en herkent hij vanzelf een geldige payload.

**Sleutelrotatie: detectie + logging.** Werkt de sleutel niet meer, dan komt er een duidelijke
waarschuwing op de statuspagina ('Euronext-sleutel werkt niet meer, mogelijk geroteerd'). De
dagelijkse statuscontrole (22:45) houdt de sleutel automatisch fris en herstelt een rotatie zelf;
bij een wijziging wordt de nieuwe afdruk gelogd en als info-melding getoond.

**Nieuw op de Status-pagina: '🔑 Euronext-sleutel'.** Toont of er een sleutel is (met afdruk en
laatste controle), een knop '🔁 Sleutel opnieuw opbouwen', en een handmatige invoer voor sleutel/IV
(met uitleg hoe je ze via F12 → Sources zelf vindt) voor als het automatisch opbouwen niet lukt.
Het bestaande diagnoseblok '🔧 Euronext-respons inspecteren' blijft ernaast staan.

Nieuwe afhankelijkheid: cryptography (voor AES). Getest: de AES-ontsleuteling, de zelf-afstemmende
sleutelontdekking en de rotatiedetectie zijn end-to-end lokaal gevalideerd (met een nagebootste
Euronext-bundel + staal). Het echte ophalen bij Euronext test jij live, zoals afgesproken — lukt
het automatisch opbouwen niet meteen, gebruik dan één keer de handmatige invoer.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.40.0
Diagnosehulp voor punt 6 (Euronext geeft geen koers terug). Nog geen fix — eerst zicht op wat
Euronext precies terugstuurt.

**Nieuw: '🔧 Euronext-respons inspecteren' op de Status-pagina.** Geef een ISIN (en optioneel een
MIC) in en de app haalt de RUWE Euronext-respons op zoals de add-on ze ziet: HTTP-status,
content-type, lengte, het begin van de body, en wat de tabelparser eruit haalt. Zo wordt meteen
zichtbaar waarom er geen koers uit komt. Puur diagnostisch — het verandert niets aan de
koersophaling.

Waarom deze aanpak: de Euronext-oproep gebeurt server-side in de add-on (niet in de browser),
dus in F12 → Network zie je niets. En een browser kan door andere cookies/IP een ander antwoord
krijgen dan de add-on. Deze knop toont exact wat de add-on binnenkrijgt. Draai ze voor een ISIN
die faalt en bezorg me de uitvoer (de 'body_head'), dan pas ik de parser gericht aan. De
waarschijnlijke oorzaak is dat het detailed-quote-fragment niet langer een HTML-tabel is (Euronext
is op Drupal 10 overgestapt; mogelijk een JSON-envelope of andere opmaak), maar dat bevestigt de
ruwe respons.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.39.0
Punt 5 van Groep C: Deutsche Börse Live als koersbron, en de aparte bronnen 'Börse Frankfurt'
en 'Lang & Schwarz' verwijderd.

**Nieuwe bron 'Deutsche Börse Live' (live.deutsche-boerse.com).** Belangrijk om te weten: die
site gebruikt dezelfde officiële backend als Xetra/Börse Frankfurt (api.boerse-frankfurt.de) —
er is geen aparte, salt-vrije API. De vroegere twee bronnen zijn daarom samengevoegd tot één
nette bron die per handelsplaats (MIC) achtereenvolgens probeert:
1. de kop-koers zoals de live-site die toont (quote_box/single — één call, de 'last price');
2. de recentste bied/laat (dekt illiquide certificaten zonder recente trade);
3. de laatste EOD-slotkoers van de afgelopen 14 dagen.
De bewezen stappen 2 en 3 (die de oude 'Börse Frankfurt'-bron ook al deed) blijven behouden, met
de kop-koers als snellere eerste poging erbovenop.

**Verwijderd:** de aparte providers 'Börse Frankfurt' en 'Lang & Schwarz' (ls-tc.de), inclusief
de L&S-functie. De onderliggende Deutsche Börse-API-client (sessie, salt, headers, backoff) is
hergebruikt en hernoemd naar een neutrale naam, want die client praat met dezelfde officiële
backend en is nog nodig voor de nieuwe bron én voor de historische slotkoers van het fotomoment.

**Bronvolgorde nu:** Yahoo → onvista → Euronext → Tradegate → Deutsche Börse Live. Deutsche
Börse Live staat bewust laatst: de backend-WAF geeft af en toe 403 en elke poging kost door de
salt-/retry-afhandeling meer tijd. De bronvermeldingen in de app (activaformulier, diagnose) zijn
overal bijgewerkt.

Eerlijke kanttekening: omdat de backend dezelfde is als de oude 'Börse Frankfurt', is de winst
vooral consolidatie (één nette bron i.p.v. twee overlappende) plus de snellere quote_box-call.
Of de WAF je stoort hangt af van je IP — vanaf je thuisnetwerk (residentieel IP) is de kans
kleiner dan vanuit een datacenter. Ik kon de nieuwe endpoint niet vanuit de sandbox live testen
(geen netwerktoegang tot die host); de bron-selectie en de terugval-logica zijn met mocks getest,
de echte werking test jij live zoals afgesproken.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.38.0
Punt 2 + 3 van Groep B: een aparte statuspagina die de gezondheid van je koersdata bewaakt,
met automatische detectie van tickerwijzigingen, splits, naamsafwijkingen, verouderde koersen
en dagen zonder koersbeweging.

**Nieuwe pagina '🩺 Status'.** Toont openstaande waarschuwingen met een kleurbadge per ernst
(🔴 fout, 🟠 waarschuwing, 🔵 info), telkens met activum, boodschap, sinds-wanneer en acties
('✓ Gezien', 'Sluiten', en bij een split 'Split registreren'). Een knop '🔄 Nu controleren'
draait de controle meteen; ze draait sowieso elke dag automatisch om 22:45 (nieuwe planner-job).

**Wat er gecontroleerd wordt:**
- **Tickerwijziging / meerdere producten onder één ISIN.** Yahoo geeft voor sommige ISIN's
  meerdere symbolen terug (bv. SK Hynix: het oude SKHYV blijft bestaan naast het nieuwe SKHY,
  maar beweegt niet meer). De app kiest nu het symbool dat het RECENTST verhandeld werd (op
  basis van de noteringstijd), werkt de kolom 'Gevonden ticker' (resolved_symbol) automatisch
  bij, en meldt de wijziging. Zo pakt de app voortaan de juiste, actieve koers.
- **Aandelensplits.** Uitgevoerde splits (via yfinance) die nog niet geregistreerd zijn, worden
  gemeld. Ze worden NIET automatisch toegepast — dat zou je kostbasis wijzigen; pas na 'Split
  registreren' worden je transacties aangepast (FIFO).
- **Naamsafwijking.** Wijkt de naam bij de bron sterk af van de opgeslagen naam (na normalisatie
  van suffixen als Inc/AG/ADR), dan wordt dat gemeld — een mogelijke indicatie van een fusie of
  rebranding.
- **Verouderde koers.** Geen nieuwe koers sinds meer dan X dagen (instelbaar via
  'status_stale_days', standaard 4). Dit ving in de tests meteen de bevroren SK Hynix-koers op.
- **Geen koersbeweging op een dag.** Een activum waarvan de koers een hele dag identiek bleef
  (min = max over minstens 3 metingen) — bv. AMZE, waar de bron telkens dezelfde slotkoers
  teruggeeft. Dit is het signaal dat je vroeg voor de US-aandelen op 0%.

Toestanden die niet meer gelden (koers wordt weer ververst, split geregistreerd, ...) worden bij
de volgende controle automatisch gesloten. Dezelfde toestand levert geen dubbele waarschuwingen.

**Verband met punt 1.** Een US-aandeel op 0% is normaal als de markt gesloten is; is er écht een
updateprobleem (zoals de SK Hynix-tickerwijziging), dan verschijnt dat nu als 'Verouderde koers'
én 'Tickerwijziging' op deze pagina, met de koers die zichzelf herstelt zodra het actieve symbool
gekozen is.

Opmerkingen: de online-detectie ('Nu controleren') doet netwerkcalls per activum en kan bij een
grote portefeuille even duren. De netwerkdelen zijn met mocks getest (de sandbox heeft geen
live toegang); de databasedelen (verouderd/geen beweging, opslag, auto-sluiten) zijn end-to-end
getest. Aangekondigde (nog niet uitgevoerde) splits zijn via gratis bronnen niet betrouwbaar
detecteerbaar — enkel uitgevoerde splits worden opgepikt.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.37.0
Punt 8 van Groep B: een volledige koersdoel-historiek per activum op de Evolutie-pagina,
met alle koersdoelen erin - handmatig én AI - en de mogelijkheid om een koersdoel opnieuw
te bepalen.

**Nieuwe tabel price_target_history.** Elk koersdoel wordt nu vastgelegd met datum, waarde,
munt en bron ('manual' of 'ai'). De logging zit centraal in de database-laag, dus ELK
koersdoel wordt automatisch mee opgenomen, ongeacht waar het vandaan komt:
- handmatig bij het toevoegen van een activum, bij een transactie, via de Activa-tabel, of via
  de nieuwe knop op de Evolutie-pagina;
- elk AI-koersdoel uit de dagelijkse adviesrondes (Luik 1).

Om herhaling te vermijden wordt een koersdoel enkel gelogd als het effectief WIJZIGT: hetzelfde
koersdoel van dezelfde bron twee keer na elkaar levert geen dubbele lijn op. Een handmatig doel
ná een AI-doel met dezelfde waarde (of omgekeerd) wordt wél bijgehouden - dat is een bewuste
bevestiging vanuit een andere bron.

**Eenmalige backfill.** Bij de eerste start van deze versie wordt de historiek meteen gevuld met
wat er al in de database zat: bestaande AI-koersdoelen (met hun eigen datum uit ai_ratings),
koersdoelen die aan transacties hangen (met de transactiedatum), en het huidige handmatige
koersdoel op elk activum (als recentste ijkpunt). Zo staat er meteen een tijdlijn, ook voor
koersdoelen van vóór deze versie. De backfill draait maar één keer en dedupt consecutieve
gelijke waarden.

**Op de Evolutie-pagina: '🎯 Koersdoel-historiek'.** Kies een activum en je krijgt:
- een tabel (nieuwste eerst) met wanneer welk koersdoel werd vastgelegd, de bron (handmatig/AI +
  model) en de wijziging t.o.v. het vorige doel;
- een grafiek met het geldende koersdoel als trapjeslijn door de tijd, bolletjes per moment
  (blauw = handmatig, groen = AI) en de werkelijke koers als grijze achtergrondlijn;
- een uitklapbaar blok 'Koersdoel opnieuw bepalen' om meteen een nieuw handmatig doel vast te
  leggen - dat wordt het actieve doel én komt als wijziging in de historiek.

Alle bedragen volgen de 2-decimalen-weergave van 0.36.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.36.0
Groep A van de openstaande lijst: dashboard-tijdstip, 2-decimalen door de hele app, en de
bevinding rond de US-koersen onder een filter.

**Punt 7 - hele app op maximaal 2 decimalen (zonder overbodige nullen).** De centrale
weergave-instellingen staan nu op 2 decimalen i.p.v. 4: show_df() (alle read-only tabellen)
en num() ronden af op 2 decimalen, en het bestaande '%.10g'-formaat laat de overbodige nullen
weg zoals voorheen. De INLINE bedrag/koers-teksten die nog op 4 decimalen stonden (o.a. de
waarde bij toekenning, de gemiddelde kostprijs op de grafiek, de snapshot-prijs per stuk) staan
nu ook op 2.

Bewust NIET beperkt tot 2 decimalen, want dat zou fout of onbruikbaar zijn:
- **Wisselkoersen** (bv. de historische FX-koers bij een transactie): blijven op 4. Een JPY-koers
  als 0,01 i.p.v. 0,0061 is waardeloos.
- **Aantallen/stuks** (verkoop- en beschikbaarheidsmeldingen): blijven op volle precisie, anders
  klopt 'beschikbaar' niet meer bij fractionele posities.
- **AI-microkosten in $** ($0,0034): op 4, anders lees je overal $0,00.
- **De BEWERKBARE tabellen** (transacties, dividenden, verkoop/simulatie, WHT-tarieven): blijven
  op volle precisie. Afronden van een invoerveld kan de opgeslagen waarde veranderen, en een
  RV-tarief als 26,375% mag niet op 26,38 komen. Zeg maar als je die tabellen OOK op 2 decimalen
  wil zien, dan pak ik de niet-bewerkbare (berekende) kolommen daarin apart mee.

**Punt 4 - datum en uur van de laatste koersupdate in de dashboardtabel.** De tabel
'Dagresultaat vandaag' heeft een extra kolom 'Laatste update' (DD/MM UU:MM, Brusselse tijd): het
tijdstip waarop de planner de koers voor dat activum het recentst wegschreef. Zo zie je meteen of
een koers echt vers is of al dagen stilstaat.

**Punt 1 - US-aandelen 'updaten niet' onder een filter: wat ik vond.** Ik heb het koerspad
volledig nagelopen. De koersen worden ALTIJD globaal opgehaald voor alle open posities
(open_position_tickers is niet rekening-afhankelijk) en per ticker toegepast op genormaliseerde
(uppercase) sleutels. De rekeningfilter bepaalt enkel WELKE posities getoond worden, niet welke
koersen opgehaald of hoe ze gekoppeld worden. In de code is er dus geen pad waarlangs een filter
de koers van een US-aandeel anders maakt. De meest waarschijnlijke verklaring is dat de US-markt
gesloten is op het moment van kijken (koers = vorige slot = 0%), wat opvalt zodra je op een
US-zware rekening filtert. De nieuwe kolom 'Laatste update' maakt dit nu controleerbaar: staat de
tijd daar recent, dan is 0% normaal (markt dicht); staat ze dagen terug, dan is er wel degelijk
een echt updateprobleem (bv. de SK Hynix-tickerwijziging) - stuur me in dat geval de tickers +
de tijdstippen uit die kolom, dan fix ik het gericht. Dit valt sowieso samen met de statuspagina
van punt 2/3.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.35.2
Bugfix: StreamlitAPIException bij het herberekenen van de TOB.

**Oorzaak.** Na een geslaagde herberekening zette de code het bevestigingsvinkje terug uit met
st.session_state["tob_rc_confirm"] = False. Streamlit verbiedt dat: een widget-key mag niet meer
overschreven worden nadat de widget in diezelfde run is aangemaakt. De herberekening zelf liep
wél door, maar eindigde in een foutmelding i.p.v. een bevestiging.

**Opgelost** met een nonce in de key van de checkbox: na de actie krijgt de checkbox een nieuwe
key en is het dus een nieuwe (lege) widget. Het vinkje staat daardoor netjes uit, zonder een
verboden toekenning.

**Dezelfde fout zat ook in de dividendherberekening** (div_rc_confirm) - daar zou ze op precies
hetzelfde moment toegeslagen hebben. Ook gefixt. Een scan van alle widget-keys in app.py
bevestigt dat dit de enige twee plaatsen waren waar een key ná het aanmaken van de widget werd
overschreven.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.35.1
Fix + transparantie rond "gesloten posities": de app zegt nu WELKE posities ze overslaat.

**Twee positieberekeningen naast elkaar - dat had ik nooit mogen doen.** Voor het overslaan van
gesloten posities (0.34.1) schreef ik een eigen SQL-som (SUM(buy) - SUM(sell)) in database.py,
terwijl het dashboard en de portefeuillepagina de FIFO-logica van belgian_tax gebruiken. Twee
implementaties van dezelfde vraag lopen vroeg of laat uiteen, en dan haalt de app geen koersen
meer op voor een positie die je wél nog hebt - zonder dat je ziet waarom.

Die eigen SQL is verwijderd. Er is nu één bron van waarheid: belgian_tax.open_position_tickers(),
die build_fifo_positions gebruikt op de split-gecorrigeerde transacties - exact wat het dashboard
toont. De scheduler kan dus per definitie niet meer van het dashboard verschillen.

**De log noemt de namen.** "5 gesloten positie(s) overgeslagen" zonder namen is niet
controleerbaar. De scheduler logt nu welke tickers worden overgeslagen, en op de 🏢 Activa-pagina
staat dezelfde lijst met een korte uitleg. Staat er iets tussen dat je nog wél bezit, dan
ontbreekt er een transactie (of staat er een verkoop te veel) - dan weet je meteen waar te
kijken.

Let op: het is goed mogelijk dat de 5 overgeslagen posities gewoon KLOPPEN (volledig verkocht).
De nieuwe lijst maakt dat controleerbaar in plaats van giswerk. Kijk zeker na of de warrant
NL0015002RI2 in die lijst staat: zo ja, dan denkt de app dat je hem verkocht hebt en ontbreekt
er een aankoop in je transacties.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.35.0
Eigen wisselkoers per transactie, filters die een herlaad overleven, en de TOB-fout op vreemde
munten gevonden én herstelbaar gemaakt.

**De TOB-fout op vreemde munten: gevonden.** Je vermoeden klopte. De TOB-berekening zelf was
altijd correct (ze rekent op de EUR-tegenwaarde), maar de EUR-tegenwaarde niet. In compute_eur
stond:  rate = get_historical_exchange_rate(...) or 1.0.  Lukte die lookup niet (netwerkhapering
bij het opslaan), dan werd de koers stilzwijgend 1,0 en was het "EUR-bedrag" gewoon het bedrag
in USD - waarna 0,35% op dat USD-bedrag werd berekend. Voorbeeld: 10 x $200 aan koers 0,92 =
EUR 1.840, TOB EUR 6,44. Met de stille 1,0 werd dat EUR 7,00. Een koers van 1,0 is voor geen
enkele vreemde munt een verdedigbare terugval; voor bv. JPY zou de fout gigantisch zijn.

Opgelost met een expliciete bronketen: eigen koers -> historische koers -> actuele koers (met
waarschuwing) -> None. Nooit meer stilzwijgend 1,0. Kan er geen enkele koers gevonden worden,
dan weigert de app op te slaan en vraagt ze om je eigen koers. Dezelfde correctie in
bulk_import.py.

**Herberekenen (💰 Transacties -> "TOB en EUR-tegenwaarde controleren/herberekenen").** Toont
eerst een VOORBEELD: per transactie de oude en nieuwe koers, EUR-tegenwaarde en TOB, plus het
verschil in totale TOB. Transacties waarvan de opgeslagen TOB exact overeenkomt met het tarief
toegepast op het bedrag in vreemde munt, worden gemarkeerd met 🚩 - dat is precies de oude fout.
Pas na een expliciet vinkje wordt er iets weggeschreven. Lijnen met een eigen wisselkoers of een
handmatige TOB blijven ongemoeid.

**Eigen wisselkoers per transactie.** Nieuw vinkje "Eigen wisselkoers gebruiken (koers van je
broker)" in het transactieformulier, met de afwijking t.o.v. de marktkoers erbij. De koers wordt
opgeslagen (kolom fx_manual) en blijft voorgoed bij die transactie: geen enkele herberekening
overschrijft ze nog. Ook instelbaar in de tabel (kolommen "FX-koers" en "FX eigen"), en een
koers in een bulk-importbestand wordt automatisch als eigen koers behandeld.

Met een uitdrukkelijke waarschuwing: **tel de auto-FX-kosten niet dubbel.** Zit de wisselmarge
van je broker al verwerkt IN die koers (auto-FX), voeg ze dan niet ook nog eens toe bij
"Transactiekosten" - anders trek je ze twee keer af van je rendement. Rekent je broker de
wisselkost als een aparte lijn aan (en gebruikt hij de zuivere marktkoers), zet ze dan wel bij
de kosten en gebruik de marktkoers.

**TOB manueel aanpasbaar in de tabel.** De kolom "TOB €" was read-only. Ze is nu bewerkbaar;
pas je ze aan, dan wordt "TOB eigen" automatisch aangevinkt en laat de herberekening die lijn
met rust.

**Filters en keuzes overleven een herlaad.** Streamlit gooit zijn session_state weg bij een
refresh van de pagina, waardoor elke filter terugsprong naar de standaardwaarde. Filters en
keuzes worden nu in de database bewaard (sleutel ui_state) en bij het opbouwen van de widget
opnieuw ingesteld: rekeningfilter, sectiekeuzes, de filters op de transactiepagina (activum,
type, jaar, rekening), de taartbasis, de opvolgperiode van luik 2. Verdwijnt een optie (bv. een
verwijderde rekening), dan valt de app netjes terug op de standaardwaarde.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.34.1
Drie fixes: de 400-fout op nieuwe modellen, geen koersen meer voor gesloten posities, en de app
stopt met proberen na 10 mislukte ophalingen.

**API-fout op de GPT-5-modellen (400 Bad Request).** De nieuwe modellen weigeren 'max_tokens'
("Use 'max_completion_tokens' instead") en aanvaarden vaak enkel de standaardtemperatuur.
Erger: mijn foutafhandeling stelde de VERKEERDE diagnose - ze zag een 400 en concludeerde
"JSON-modus niet ondersteund", verwijderde response_format en probeerde opnieuw met dezelfde
foute parameter. Vandaar twee keer 400 en dan een harde fout.

Opgelost met een adaptieve parameterlaag: de app kiest een verstandige startwaarde per
modelfamilie (GPT-5/o-serie -> max_completion_tokens, geen temperature; GPT-4 -> max_tokens),
en wijst de API tóch een parameter af, dan wordt exact díé parameter aangepast en de call
opnieuw gedaan. Wat werkte, wordt per model onthouden, zodat de volgende oproep meteen juist
is. Nieuwe modellen breken de app dus niet meer, en de log vermeldt voortaan de échte reden.

**Geen koersen meer voor gesloten posities.** De scheduler haalde elke 5 minuten koersen op voor
ÁLLE activa, ook voor posities die je volledig verkocht hebt. Nu enkel nog voor open posities
(netto aantal > 0). De historiek en de gerealiseerde meerwaarden blijven uiteraard bewaard - die
komen uit de transacties, niet uit de actuele koers. Activa zonder enige transactie (net
toegevoegd, nog niets gekocht) worden wél gevolgd, zodat je de koers al ziet vóór je koopt.

**Stoppen na 10 mislukte pogingen.** Nieuwe teller per activum (kolom price_fail_count). Vinden
alle bronnen tien keer op rij niets, dan is dat geen tijdelijke storing maar een instrument dat
nergens genoteerd staat: de app stopt met proberen. Dat scheelt vijf mislukte netwerkcalls en
evenveel logregels bij élke koersverversing. Een geslaagde ophaling zet de teller terug op nul,
zodat een tijdelijke storing een activum niet stilaan naar de grens duwt. Een handmatige koers
blijft gewoon werken. In het activaoverzicht zie je de teller in de kolom "Mislukt", met een
waarschuwing en een knop "🔄 Heractiveer" wanneer een activum gestopt is.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.34.0
Eigen model voor luik 2, kostenraming per oproep, actuele modellen, en getallen zonder
overbodige nullen.

**Apart model voor luik 2 (marktopportuniteiten).** Marktonderzoek met live websearch vraagt
vaak ander redeneervermogen dan het beoordelen van je eigen posities - en je wilt die kost los
kunnen sturen. Er is nu een aparte keuze "② Model voor marktopportuniteiten" (instelling
openai_market_model). Laat je ze leeg, dan valt luik 2 gewoon terug op het model van luik 1.

**Modellen bijgewerkt naar de actuele OpenAI-catalogus**, met de prijzen van de officiële
prijspagina (opgehaald op 12/07/2026, USD per 1M tokens, standaardtarief, korte context):
  - GPT-5.6: Sol $5/$30 · Terra $2,50/$15 · Luna $1/$6
  - GPT-5.5 $5/$30 · GPT-5.5 Pro $30/$180
  - GPT-5.4 $2,50/$15 · Mini $0,75/$4,50 · Nano $0,20/$1,25 · Pro $30/$180
  - De vorige generatie (GPT-4.1 / 4o) blijft beschikbaar als goedkope optie.
Standaardkeuze voor nieuwe installaties is GPT-5.6 Terra (sterk en betaalbaar). De maandelijkse
prijsverversing blijft werken en overschrijft deze richtprijzen zodra ze wijzigen.

**Kostenraming per oproep, per model.** Nieuwe uitklapper bij ⚙️ Instellingen → AI: voor élk
model de geraamde kost van één oproep van luik ①, luik ② en het belastingadvies, plus een ruwe
maandraming (21 werkdagen). Belangrijk: zodra een functie een keer gedraaid heeft, wordt het
GEMETEN gemiddelde tokengebruik uit je eigen historiek gebruikt in plaats van een richtwaarde -
de raming wordt dus vanzelf accurater. Voor luik ② is ook de websearch-oproep meegerekend
($0,025 per oproep) plus de opgehaalde zoekinhoud, die als input-tokens wordt aangerekend. Het
blijft een raming; de echte factuur staat op je OpenAI-dashboard.

**Getallen zonder overbodige nullen.** Gehele getallen tonen niet langer nullen achter de komma:
€100 in plaats van €100,00, +5% in plaats van +5,00%, 10 stuks in plaats van 10,0000. Dit geldt
zowel voor de metrics en bijschriften (eur/pct/num) als voor alle tabellen (kolomformaat %.10g,
met afronding op 4 decimalen zodat afrondingsruis geen eindeloze decimalen oplevert).

Let op: dit trimt ALLE overbodige nullen, dus ook €100,50 wordt €100,5. Dat is bewust: de
tabellen doen dat sowieso, en anders zou dezelfde waarde er in een metric anders uitzien dan in
een tabel. Wil je liever dat bedragen altijd twee decimalen houden (€100 maar €100,50), zeg het
- dat is één regel in _trim_zeros.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.33.2
Euronext: instrument gevonden, koers nu ook. Plus strengere validatie en een label-diagnose in
de log.

**Wat je log leerde.** Het endpoint klopt nu: Euronext antwoordt met HTTP 200 op
NL0015002RI2-XAMS, dus Euronext Amsterdam KENT de warrant wel degelijk. Er bleef één probleem:
"bestaat (HTTP 200) maar geeft geen koers terug". Oorzaak: de koers werd uit het HTML-fragment
gehaald met positionele regexes per label ("Last traded price</td><td>..."). Euronext varieert
de opmaak van de labelcel (soms <td>, soms <th>, soms met <strong> errond), en dan matcht zo'n
regex niet - stilzwijgend, zonder fout.

**Generieke tabelparser.** Het fragment is een tabel (label | waarde | tijdstip) en wordt nu als
tabel geparsed naar een label->waarde-map, ongeacht de opmaak. Daarna wordt gezocht op label,
in volgorde van bruikbaarheid: laatste koers -> waarderingskoers -> vorige slotkoers ->
bied/laat. Voor een illiquide warrant zonder trade vandaag levert dat dus alsnog een koers op.

**Getalnotatie.** De Engelse Euronext-pagina schrijft 1,234.56 (komma = duizendtal), maar cellen
kunnen ook 12,34 bevatten. De vorige parser maakte van "1,234.56" onherroepelijk None. Nu:
staan er zowel een komma als een punt in, dan is de laatste het decimaalteken; staat er enkel
een komma met exact drie cijfers erna, dan is het een duizendtalscheiding.

**HTTP 200 is geen bewijs meer.** Bij het aftasten van de handelsplaatsen telde elke 200 als
"gevonden", maar Euronext geeft ook 200 terug op een leeg fragment - waardoor de eerste
kandidaat (XAMS voor NL) altijd "won", ook voor een onbekend instrument. Nu telt enkel een echt
geparste tabel (minstens 3 velden) als bewijs.

**Label-diagnose.** Vindt Euronext het instrument maar zit er geen koers in de tabel, dan logt de
app voortaan WELKE velden Euronext teruggaf. Zo is meteen zichtbaar of een koersveld anders
heet (dan voegen we het label toe) of dat alle koersvelden gewoon leeg staan (dan is er echt
geen notering). Dezelfde velden verschijnen ook in de Bronnen-diagnose in de app.

Overige meldingen in je log zijn verwacht gedrag, geen fouten: onvista/Tradegate/Lang & Schwarz
kennen dit product niet (het noteert enkel op Euronext Amsterdam), en Borse Frankfurt blijft
403 geven door zijn bot-detectie - die bron staat daarom laatst in de keten en wordt na een 403
tijdelijk gepauzeerd.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.33.1
Bugfix: het dagelijkse portefeuilleadvies (luik 1) faalde met "Unterminated string starting
at ...".

**Oorzaak.** Het antwoord bevat het tekstadvies PLUS een rating per positie, maar de
tokenlimiet stond vast op 2200. Met een portefeuille van enkele tientallen posities paste dat
niet: het model brak middenin de JSON af, waarna het volledige antwoord onbruikbaar was - ook
de ratings die al compleet waren. In de log zag je enkel de cryptische JSON-fout, niet de
werkelijke reden (afkapping).

**Drie ingrepen:**
- De tokenlimiet schaalt nu mee met het aantal posities (ongeveer 1400 + 170 per positie, met
  een plafond). Bij 37 posities is dat ~7700 tokens in plaats van 2200.
- Afkapping wordt herkend (finish_reason 'length') en als zodanig gelogd, in plaats van als
  een raadselachtige parseerfout door te komen.
- Een afgekapt antwoord wordt hersteld: de openstaande string en haakjes worden gesloten, zodat
  de al complete adviezen alsnog bewaard worden. Het onvolledige laatste item valt weg via de
  gewone veldvalidatie. Je krijgt dan een duidelijke melding ("x van de y posities kregen een
  rating") in plaats van niets.

Daarnaast wordt geldige JSON nu afgedwongen via response_format; modellen die dat niet
ondersteunen vallen automatisch terug op een gewone call. De tokenlimiet voor de
marktopportuniteiten (luik 2) ging van 3500 naar 5000, want zes onderbouwde ideeën liepen tegen
dezelfde grens aan.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.33.0
Handmatige dividendcorrecties worden niet meer overschreven, en de buitenlandse
bronbelasting werkt voortaan per jaar.

**Herberekenen overschrijft je handmatige correcties niet langer.** De knop "keten
herberekenen" bouwde elke lijn blind opnieuw op vanaf het brutobedrag - ook lijnen waarin jij
net een bedrag had gecorrigeerd (bv. omdat je broker een afwijkend verdragstarief toepaste).
Vanaf nu:
  - Dividendlijnen krijgen een vlag "handmatig gecorrigeerd" (nieuwe kolom 🔒 Handmatig in de
    tabel). Die wordt automatisch gezet zodra je zelf een bedrag (①-④) aanpast; je kunt ze ook
    zelf aan- of afvinken.
  - De herberekening SLAAT die lijnen standaard over.
  - Je krijgt eerst een VOORBEELD te zien: welke lijnen zouden wijzigen, van welke waarde naar
    welke, met het tarief en het jaar dat wordt toegepast, en de totale impact op je netto in
    euro. Pas na een expliciet vinkje + klik wordt er iets weggeschreven.
  - Wil je toch alles herbouwen (bv. na een tariefcorrectie), dan kies je "ook handmatig
    gecorrigeerde lijnen overschrijven" - met een aangepaste bevestigingstekst, zodat de impact
    duidelijk is vóór je klikt.

**Buitenlandse bronbelasting per jaar.** Bronbelastingtarieven wijzigen over de jaren
(verdragen, nationale hervormingen), en een dividend hoort belast te worden tegen het tarief
dat gold OP DAT MOMENT - niet tegen het tarief van vandaag. De tarieven zijn nu per jaar
instelbaar (⚙️ Instellingen → Belasting), met doorschuiving: stel je 2024 in, dan geldt dat
ook voor 2025, 2026, ... tot je voor een van die jaren iets anders instelt. Je registreert dus
enkel de WIJZIGINGEN, niet elk jaar opnieuw dezelfde tabel.
  - Elk dividend gebruikt automatisch het tarief van zijn eigen jaar: bij het invoeren, bij het
    inline bewerken, bij de bulk-import én bij het herberekenen van de keten.
  - Dekkingscontrole: de instellingenpagina toont welke jaren met transacties of dividenden nog
    geen jaartabel hebben (die vallen terug op de standaardtarieven) en welke er wél zijn.
  - Een overzichtstabel toont per land wat er in elk ingesteld jaar effectief geldt, inclusief
    wat een jaar van een vorig jaar erft.
  - Een jaartabel wissen kan; dat jaar erft dan weer van het jaar ervoor.
  - Wat je vóór deze versie had ingesteld (de jaarloze tarieventabel) blijft gewoon werken als
    basislaag - er gaat niets verloren.

Let op: nieuwe tarieven opslaan herberekent bestaande dividenden NIET automatisch. Dat is
bewust - je beslist zelf, met het voorbeeld erbij, via de knop op de 💰 Dividenden-pagina.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.32.0
Twee designaanpassingen, en de echte oorzaak van de warrant-fout gevonden.

**Euronext gebruikte een fout endpoint (de 404 in je log).** De detailed-quote-call ging naar
/en/ajax/getDetailedQuoteAjax/... — dat pad bestaat niet. Het juiste endpoint is
/en/intraday_chart/getDetailedQuoteAjax/<ISIN>-<MIC>/full via GET. Meteen ook de MIC-detectie
herwerkt: de zoeker van Euronext kent gestructureerde producten vaak niet (vandaar "geen
zoekresultaat"), dus de handelsplaatsen worden nu ECHT AFGETAST tegen het quote-endpoint
(NL: XAMS, TNLA, ALXA, MTAA, daarna XBRU/XPAR; analoog voor BE/FR/PT/...). De eerste die HTTP
200 geeft, wint en wordt gecachet. Ook een negatief resultaat wordt gecachet, zodat er niet
elke 5 minuten opnieuw zes beurzen worden afgetast. De koers wordt uit het HTML-fragment
gehaald in de volgorde laatste koers -> waarderingskoers -> vorige slot -> bied/laat, zodat
ook een illiquide product zonder trade vandaag een waarde oplevert.

**Nieuw: Bronnen-diagnose (Activa -> Bronnen diagnose).** Vraagt élke koersbron apart wat ze
van een ISIN weet en toont per bron het antwoord (gekend / onbekend / HTTP-status / koers).
Zo zie je zwart op wit waar het misloopt in plaats van enkel "alle bronnen faalden". Dit is
nodig omdat de ontwikkelomgeving geen live netwerktoegang heeft tot deze bronnen: de diagnose
verplaatst die verificatie naar jouw omgeving.

**Nieuw: 'Enkel handm.' per activum.** Vinkje in het activaoverzicht dat ALLE onlinebronnen
overslaat en enkel de handmatige koers gebruikt. Voor een effect dat nergens publiek genoteerd
is, is elke onlinepoging bij voorbaat zinloos: deze vlag scheelt vijf mislukte netwerkcalls en
evenveel foutregels in de log bij élke koersverversing (om de 5 minuten).

**Keuze personenbelasting enkel nog zichtbaar waar ze van toepassing is.** De zienswijzekeuze
voor performance shares verscheen op het dashboard zodra er ergens in de portefeuille
personenbelasting betaald was — ook als je filterde op een rekening zonder zulke producten.
Nieuwe helper has_income_tax(rekeningen) kijkt enkel naar de GESELECTEERDE rekening(en); bij
"alle rekeningen" telt de hele portefeuille mee, zoals voorheen.

**Taartdiagram: keuze tussen huidige waarde en geïnvesteerd kapitaal.** Een schakelaar boven de
taart. "Huidige waarde" toont het gewicht van elke positie vandaag (dus mee bepaald door
koersbewegingen); "Geïnvesteerd kapitaal" toont de kostbasis, dus hoe je je geld effectief hebt
verdeeld. Samen laten ze zien welke posities zwaarder of lichter zijn gaan wegen. Voor
performance shares volgt de kostbasis dezelfde zienswijze als de KPI "Totaal geïnvesteerd", zodat
taart en cijfers elkaar niet tegenspreken. Posities met waarde 0 worden weggelaten (die
vertekenen de taart).

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.31.0
Het dagelijkse AI-advies bestaat nu uit twee duidelijk gescheiden luiken, en het dashboard
toont een dagresultaat per positie.

**Luik 1 - Portefeuilleadvies (dagelijks, 18:00).** Ongewijzigd van opzet, maar strikt
afgebakend: het gaat nu UITSLUITEND over de aandelen die je al bezit, met (sterk) kopen /
behouden / (sterk) verkopen per positie. De kop "Koopopportuniteiten" is uit dit advies
verwijderd - die verhuist volledig naar luik 2. Zo blijven beide adviezen los van elkaar
leesbaar en opvolgbaar.

**Luik 2 - Marktopportuniteiten (dagelijks, 07:45, nieuw).** Elke werkdag vóór de opening
speurt de AI de WERELDWIJDE markt af naar nieuwe koopideeën buiten je portefeuille, op basis
van bedrijfsprestaties en cijfers, vooruitzichten, macro-economische inzichten, geopolitiek
en financiële berichtgeving. Per dag exact 6 voorstellen:
  - 2x defensief (focus op groei en eventueel dividendrendement)
  - 2x matig speculatief
  - 2x sterk speculatief
Elk idee komt met onderbouwing, katalysatoren, de belangrijkste risico's, een koersdoel op
12 maanden en een rating. Alles staat in drie visueel gescheiden blokken op de AI-pagina.

**Live websearch voor luik 2.** Zonder live zoekopdracht kan een taalmodel enkel uit zijn
trainingskennis putten - "recente financiële berichtgeving" is dan per definitie verouderd.
Luik 2 gebruikt daarom de websearch-tool van OpenAI (Responses-API), zodat het model zelf
actuele koersen, resultaten en nieuws opzoekt. Ondersteunt je model de tool niet of faalt de
call, dan valt de app stil terug op een gewoon advies op basis van trainingskennis - dat
wordt dan expliciet gelogd én in de app gemeld, zodat je nooit denkt dat iets "live" is
terwijl het dat niet is. Aan/uit via Instellingen -> AI.

**Opvolging over 7 dagen, 1 maand en 3 maanden.** Elk voorgesteld aandeel wordt bijgehouden
in een nieuwe tabel market_ideas. Per periode toont de app per aandeel het GEMIDDELDE ADVIES:
de ratings van die periode worden omgezet naar een score (sterk kopen +2, kopen +1, behouden
0, verkopen -1, sterk verkopen -2), gemiddeld, en weer naar een label vertaald. Daarnaast:
hoe vaak het aandeel werd voorgesteld, in welke risicoklasse(n), de startkoers, de koers nu
en het rendement sinds het eerste advies. Een nieuwe schedulerjob (dagelijks 22:30, na de
Amerikaanse slotbel) volgt de koers van elk voorgesteld aandeel op, zodat dat rendement uit
de database komt en de pagina zonder netwerkcalls laadt.

**Dashboard: dagelijkse P/L per positie (nieuw).** Een blok "Dagresultaat vandaag" toont per
open positie de vorige slotkoers, de koers nu, het dagverschil in % en de dag-P/L in euro,
plus een totaal, het aantal stijgers/dalers en de beste/zwakste naam van de dag. Referentie
is de laatste koers die vóór vandaag is vastgelegd (de planner schrijft elke 5 minuten weg,
dus in de praktijk de slotkoers van de vorige beursdag). De omrekening naar euro gebeurt met
de wisselkoers die al in de positie zit - geen extra FX-call. Let op: dit vult zich pas
vanaf de eerste volledige dag dat de planner draait; posities zonder oudere koers worden
netjes overgeslagen en onderaan de tabel benoemd.

**Instellingen.** Nieuw: aan/uit voor luik 2 en voor de live websearch. De AI-kostenpagina
splitst de nieuwe functie apart uit ("② Marktopportuniteiten"), zodat je ziet wat websearch
kost.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.30.0
Nieuwe koersbron + fors snellere app.

**Euronext Live als vijfde koersbron (lost NL0015002RI2 op).** De ING Markets-warrant
noteert enkel op Euronext Amsterdam en is onbekend bij alle vier de Duitse platformen
(onvista, Tradegate, Lang & Schwarz, Boerse Frankfurt) en bij Yahoo. Euronext Live heeft
sleutelloze JSON-endpoints (dezelfde die live.euronext.com zelf gebruikt): een
zoek-endpoint dat de handelsplaats (MIC) per ISIN oplevert (terugval: land-MIC, bv.
NL -> XAMS, BE -> XBRU), chartdata (eerst intraday, dan de volledige daghistoriek voor
illiquide producten zonder trade vandaag) en als laatste redmiddel het
detailed-quote-fragment (bied/laat-/referentiekoers). De bron staat direct na onvista in
de keten: snel, en ze dekt precies het gat van de Duitse platformen - producten die
enkel op Euronext noteren, dus ook illiquide fondsen op Euronext Brussel. Test na de
update via Activa -> ISIN-check of wacht een koersrondje van de scheduler af; de log
toont dan geen "Geen koers gevonden voor: NL0015002RI2" meer. Endpoints zijn onofficieel
(kunnen ooit wijzigen) en volledig defensief afgehandeld: elk afwijkend antwoord wordt
gelogd en de volgende bron neemt het gewoon over.

**App laadt vrijwel meteen: koersen komen nu uit de database i.p.v. live tijdens het
renderen.** De scheduler schrijft elke 5 minuten al verse koersen naar price_history
(apart proces), maar de app haalde bij elk verstrijken van de cache ALLES opnieuw live
en een voor een op - bij elke ticker eerst Yahoo (traag info-object) en voor effecten
zonder Yahoo-notering ook nog de volledige bronnenketen met timeouts. Dat blokkeerde de
volledige paginarender, soms tientallen seconden. get_overview leest nu eerst de
recentste opgeslagen koers (nieuwe gebatchte query get_latest_prices: 1 query i.p.v. 1
per ticker) en accepteert die tot 20 minuten oud; enkel ontbrekende/verouderde tickers
worden nog live opgehaald. In de praktijk: geen enkele netwerkcall meer tijdens het
laden zolang de scheduler draait.

**Live ophalen is voortaan parallel.** Als er toch live gehaald moet worden (scheduler,
ontbrekende koersen, of via de knop "Ververs prijzen") gebeurt dat nu met maximaal 8
gelijktijdige workers i.p.v. serieel: de totale duur wordt ongeveer die van het traagste
effect i.p.v. de som van allemaal. Boerse-Frankfurt-calls zijn daarbij geserialiseerd
met een lock (gedeelde sessie + salt-status zijn niet thread-safe); de 403-retry roept
intern de locked-variant aan om een deadlock te vermijden.

**"Ververs prijzen" forceert nu echt een live rondje.** De knop leegde enkel de
Streamlit-cache; met de nieuwe DB-first-logica zou hij anders gewoon de opgeslagen
scheduler-koersen herlezen. Hij zet nu eenmalig live=True (met spinner) en leegt ook de
in-memory koerscache van market_data.

**init_db draait nog maar een keer per proces.** Streamlit voert app.py bij elke
interactie volledig opnieuw uit; alle CREATE TABLE's en migratiechecks (PRAGMA
table_info per tabel) liepen dus bij elke klik mee. Nu via cache_resource eenmalig.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.29.2
0.29.2
- Analyse van de aangeleverde log: het antwoord op "welke ticker faalt consequent" is zo goed als
zeker NL0015002RI2 (de ING-warrant). Ze faalt op alle vier externe bronnen (onvista, Börse
Frankfurt, Tradegate, Lang & Schwarz) én kan niet terugvallen op 'ticker rechtstreeks op Yahoo',
omdat de ticker zelf de ISIN is (dat pad wordt bewust overgeslagen om de 'Invalid ISIN
number'-exception te vermijden). FR0013215407 faalt weliswaar ook op alle vier externe bronnen,
maar hoort bij een ticker mét een apart Yahoo-symbool (vermoedelijk ALMEX.PA) dat meestal wél
rechtstreeks lukt — vandaar dat de teller steevast op 36/37 blijft steken. Vanaf deze versie
bevestigt de log dit voortaan expliciet i.p.v. dat je het moet afleiden (zie hieronder).
- Scheduler noemt voortaan de falende ticker(s) met naam. "✅ 36/37 koersen opgeslagen" werd niet
aangevuld met wélke ticker de ontbrekende was. Een nieuwe regel "⚠️ Geen koers gevonden voor:
..." somt ze nu expliciet op bij elke koersverversing.
- Bugfix: 'Invalid ISIN number'-crash in get_price_series (historische reeksen, bv. grafieken).
Dezelfde yfinance-exception die al in vier andere functies was opgelost, dook hier nog op omdat
deze functie gemist was. Lost nu ook eerst een Yahoo-symbool op via de ISIN.
Bugfix: sommige logregels (bv. de 'Invalid ISIN number'- en 'Connection aborted'-meldingen in de
aangeleverde log) verschenen zonder tijdstip/niveau. Oorzaak: Streamlit draait als apart proces
van scheduler.py en had nooit een logging-configuratie — die meldingen kwamen dus via Pythons
kale 'lastResort'-handler binnen. app.py configureert nu dezelfde logging-opmaak als
scheduler.py, zodat voortaan ELKE regel (of ze nu van een interactieve klik of van de
achtergrondplanner komt) een tijdstip en niveau toont.
- Minder onnodige netwerkcalls en logspam: een ticker waarvoor zonet nog alle online bronnen
faalden, wordt de eerstvolgende 30 minuten niet meer opnieuw bij die bronnen geprobeerd (rechtstreeks
naar de handmatige koers) — dat scheelt 4+ netwerkcalls en flink wat logregels per koersverversing
(om de 5 min) voor een effect dat toch bij niemand gevonden wordt. Na 30 minuten of bij een
succesvolle vondst wordt gewoon opnieuw geprobeerd.
- Börse Frankfurt staat nu laatst in de bronnenketen (na onvista, Tradegate, Lang & Schwarz) i.p.v.
op de tweede plaats. Ondanks dynamische salt en Chrome-TLS-imitatie blijft hun API op de meeste
aanvragen 403 geven — vermoedelijk bot-detectie die verder gaat dan headers/salt/TLS (bv.
cookiescope tussen hun www- en api-subdomein), wat realistisch enkel een echte browser omzeilt.
Zij blijft als laatste kans meedraaien, maar kost niet langer de eerste (en traagste) poging voor
activa die toch al bij de andere drie bronnen zouden falen.

## 0.29.1
- Naam wordt nu ook gevonden via het Yahoo-zoekresultaat. Yahoo's zoekendpoint geeft voor veel
ISIN's al een naam terug (longname/shortname), zelfs als er geen live koers beschikbaar is —
en die zoekopdracht gebeurde toch al bij het ophalen van het Yahoo-symbool, dus dit kost geen
extra netwerkcall. probe_isin_meta probeert dit nu eerst, dan onvista, dan Börse Frankfurt.
- Fotomomentwaarde (31/12/2025) van warrants/certificaten: de foutmelding legt nu uit dat "geen
slotkoers gevonden" meestal betekent dat het effect toen nog niet bestond of niet verhandeld werd
(bv. een pas in 2026 uitgegeven warrant) — en dat dat geen probleem is: het fotomoment geldt enkel
voor posities die je al vóór 2026 bezat. Voor een in 2026 gekocht effect mag het veld gewoon leeg
blijven; de meerwaardebelasting gebruikt dan gewoon de werkelijke aankoopprijs.
- Bugfix: de fotomomentwaarde kon stilzwijgend de ACTUELE koers gebruiken i.p.v. de historische
slotkoers van 31/12/2025, via een terugval op de live Tradegate-koers. Voor een tax-gevoelig veld
is een foutieve waarde erger dan geen waarde. Die terugval is vervangen door een echte historische
opzoeking via Börse Frankfurt (price_history rond de gevraagde datum); lukt ook dat niet, dan
geeft de functie nu None (handmatig invullen) i.p.v. een misleidend 'actueel' cijfer.
- Diagnose Börse Frankfurt: de Chrome-TLS-imitatie (0.27.8) en de dynamische salt (0.27.6) werken nu
aantoonbaar (logs tonen 'curl_cffi met Chrome-imitatie actief' en 'salt: dynamisch opgehaald'),
maar de API blijft op sommige aanvragen alsnog 403 geven. Dat wijst op bot-detectie die verder
gaat dan headers/salt/TLS-vingerafdruk (bv. sessie-/cookiescope tussen www. en api.-subdomeinen,
of gedragsdetectie) — iets wat enkel een echte browser (headless Chrome) betrouwbaar omzeilt, geen
scriptmatige HTTP-client. Voor de naam/type-opzoeking staat Börse Frankfurt daarom nu na Yahoo en
onvista in de rij (die twee zijn intussen betrouwbaarder gebleken); voor de koers zelf blijft de
volledige keten (onvista → Börse Frankfurt → Tradegate → Lang & Schwarz) actief.

## 0.29.0
- Bugfix: historische wisselkoers kon licht variëren tussen de TOB-preview en het effectief
opslaan van een transactie (twee aparte, ongecachete netwerkcalls voor dezelfde munt/datum; bij
een tijdelijke hapering viel één ervan terug op de actuele in plaats van de historische koers).
Historische FX wordt nu permanent gecachet per (munt, datum): een afgesloten handelsdag heeft een
vaste koers, dus dezelfde combinatie geeft nu altijd exact dezelfde koers terug. Dit verklaart de
licht afwijkende TOB bij buitenlandse aandelen.
- Interest en securities lending hoeven niet langer aan een activum gekoppeld te worden. Dividenden
blijven verplicht een activum (dat IS waarvoor ze uitgekeerd worden), maar interest en securities
lending tonen nu een vinkje "Niet gekoppeld aan een specifiek activum" (standaard aan) — handig
voor algemene cash-rekeninginterest. De database-kolom is versoepeld van NOT NULL naar optioneel;
bestaande databases migreren automatisch met behoud van data. Niet-gekoppelde lijnen tonen
"— Algemeen (niet gekoppeld) —" in alle overzichten en het cash-grootboek toont voortaan ook het
juiste label (Interest/Securities lending i.p.v. altijd "Dividend").
- ISIN is nu de bron van waarheid voor koersopzoeking. Voorheen probeerde de app eerst de opgeslagen
ticker rechtstreeks op Yahoo — bij ambigue of foutieve tickers (beurssuffixen, gelijkaardige
ISIN's) kon dat de verkeerde koers opleveren. Heeft een activum een ISIN, dan wordt die nu altijd
eerst gebruikt om het juiste Yahoo-symbool op te zoeken (en pas als terugval de rauwe ticker
rechtstreeks). Het gevonden symbool wordt bewaard in de nieuwe kolom 'Gevonden ticker' in het
activaoverzicht — puur informatief, de ISIN blijft de brondata.
- Koersdoel instelbaar bij het toevoegen van een activum (i.p.v. pas bij een transactie), inclusief
dezelfde "🤖 Bepaal via AI"-knop. Ook nadien aanpasbaar via de nieuwe 'Koersdoel'-kolom in het
activaoverzicht. Een koersdoel op activumniveau heeft voorrang op een ouder transactie-koersdoel.
Bugfix: "Vul lege velden in" (gedetailleerde dividendinvoer) wiste het gekozen activum, de
rekening, de datum en de munteenheden. Oorzaak: die knop vernieuwt een nonce die bedoeld was om
enkel de bedragvelden (①②③④) te verversen, maar alle widgets in het formulier deelden dezelfde
nonce — inclusief activum/datum/rekening/munt. Die laatste gebruiken nu stabiele keys die niet
meer resetten wanneer de bedragvelden ververst worden.
- Bugfix: bedragkolommen in tabellen (bv. "Gerealiseerde meer-/minwaarden") sorteerden verkeerd bij
een klik op de kolomkop. Oorzaak: bedragen werden als opgemaakte tekst ("€1.234,56") getoond,
waardoor een sortering alfabetisch i.p.v. numeriek gebeurde. Alle overzichtstabellen met een
geld-, aantal- of percentagekolom (gerealiseerde W/V, activaresultaten, open posities,
belastingoverzicht, TOB-detail, AI-kostenoverzicht, cash-grootboek en -bewegingen) gebruiken nu
numerieke kolommen met enkel de weergave opgemaakt, zodat kolomsortering overal correct werkt.

## 0.28.2
- Naam en beurs worden nu automatisch ingevuld bij een ISIN-only activum (bv. een warrant). De
ISIN-flow riep enkel probe_isin aan, dat alleen prijs/munt/bron teruggeeft — de naam bleef dus
altijd leeg, ook al werd de koers wel gevonden. Nieuwe functie probe_isin_meta haalt de naam (en
het type) op via onvista, met een terugval op de instrument_information van Börse Frankfurt. De
melding onder het formulier onderscheidt nu expliciet vier gevallen (naam+koers gevonden,
enkel koers, enkel naam, geen van beide) zodat duidelijk is wat je zelf nog moet invullen.
- 'Invalid ISIN number'-crash bij het fotomoment (31/12) opgelost. get_close_on_date (gebruikt
door de knop 'Ophalen 31/12/2025') gaf voor een ISIN-only activum nog steeds de rauwe ISIN aan
yfinance door, met dezelfde 'Invalid ISIN number'-exception tot gevolg als eerder al bij
get_stock_info en get_current_price was opgelost. Lost nu eerst een Yahoo-symbool op; is er
geen, dan valt de fotomomentwaarde terug op de slotkoers via onvista (chart_history) of Tradegate.
- Ook get_market_state gebruikt nu dezelfde ISIN-naar-Yahoo-symboolvertaling.
De onvista-provider is opgesplitst in herbruikbare bouwstenen (zoeken/snapshot), zodat zowel de
actuele koers, de naam/type als de fotomomentwaarde er gebruik van kunnen maken zonder de
zoekopdracht te dupliceren.

## 0.28.1
- Nieuwe primaire ISIN-koersbron: onvista. Ondanks correcte dynamische salt, browserheaders,
cookies én Chrome-TLS-imitatie (0.27.8) blijft Börse Frankfurt 403 geven — hun beveiliging is
vermoedelijk verder aangescherpt dan het bekende 2022-algoritme (er bestaan zelfs projecten die
hiervoor naar Selenium-browserautomatisering grepen). In plaats van die wapenwedloop verder te
voeren is de open onvista-API (api.onvista.de) toegevoegd als eerste externe bron: geen salt of
TLS-verdediging, dekt ook derivaten zoals warrants/certificaten. Het patroon volgt het bewezen
pyOnvista-project: instrument zoeken op ISIN, daarna een snapshot per instrumenttype met
quote.last (terugval: bid/laat en quoteList-noteringen; onbekende instrumenttypes proberen een
tweede URL-vorm). De keten is nu: Yahoo → onvista → Börse Frankfurt → Tradegate → Lang & Schwarz
→ handmatige koers. De formulierteksten benoemen de nieuwe bronnen.

## 0.28.0
- Vier robuustheidsverbeteringen aan de koersbronnen (n.a.v. code-review):
  - Canonieke URL-encoding voor de trace-id-hash. De gehashte string moet byte-identiek zijn aan de
effectief verstuurde URL; daarom nu strikt percent-encoding (%20 i.p.v. '+', zodat geen enkele
HTTP-client iets hernormaliseert), JS-stijl booleans ('true'/'false' i.p.v. Pythons
'True'/'False') en een vaste parametervolgorde.
  - Betere salt-diagnose: staat het woord 'salt' wél in een bundle maar matcht het patroon niet
(hernoemd, geobfusceerd of verstopt in een groter config-object), dan logt de melding voortaan
de context rond die plek — zo is bij een toekomstige wijziging meteen zichtbaar hoe de nieuwe
vorm eruitziet.
  - Exponentiële backoff i.p.v. een vaste blokkade van 10 minuten: bij een aanhoudende 403 pauzeert
Börse Frankfurt nu 30s, dan 60s, 120s, ... tot maximaal 10 minuten, en een geslaagde call reset
de teller. Zo blokkeert één tijdelijke weigering de interactieve app niet onnodig lang.
  - Nieuwe koersbron Lang & Schwarz (ls-tc.de) als extra vangnet ná Börse Frankfurt en Tradegate:
een toegankelijker platform zonder salt-beveiliging dat veel warrants/certificaten verhandelt.
Instrument wordt op ISIN opgezocht, de koers komt uit de recentste chartdata; elk afwijkend
antwoord wordt gelogd en valt netjes door naar de volgende bron.

## 0.27.8
- TLS-vingerafdruk was de resterende 403-oorzaak bij Börse Frankfurt. De 0.27.7-log toonde
'salt=dynamisch' — salt en headers klopten dus — en tóch een lege 403: hun WAF herkent de
TLS-handdruk van Python-requests als bot, ongeacht de headers. De Börse-Frankfurt-sessie loopt nu
via curl_cffi met Chrome-imitatie (dezelfde techniek en dezelfde bibliotheek waarmee yfinance
Yahoo's botdetectie omzeilt; zit al in de container). curl_cffi zet daarbij zelf consistente
Chrome-headers; alleen Origin/Referer/taal worden toegevoegd zodat de imitatie intact blijft.
Is curl_cffi onverhoopt niet bruikbaar, dan valt de code terug op gewone requests en meldt de log
dat expliciet. De sessie-aanmaak, de terugval en de volledige request-flow met dynamische salt
zijn getest; ook de timeout-signatuur van curl_cffi is geverifieerd.

## 0.27.7
- Brotli-bug in de salt-detectie opgelost. Het HTML-snippet in de 0.27.6-log toonde binaire data:
de homepage van Börse Frankfurt kwam Brotli-gecomprimeerd binnen omdat de headers 'br'
adverteerden, terwijl requests Brotli alleen uitpakt als het brotli-pakket geïnstalleerd is (en
dat zit niet in de container). De salt-detectie zocht dus scripttags in gecomprimeerde bytes. De
sessie adverteert nu enkel 'gzip, deflate' (die pakt requests altijd zelf uit), met een extra
vangnet dat een onverhoopt toch Brotli-gecomprimeerd antwoord uitpakt als het pakket aanwezig is.
Alle vijf salt-extractiepaden zijn geregresseerd.

## 0.27.6
- Salt-detectie Börse Frankfurt generiek gemaakt. De log van 0.27.5 toonde de exacte oorzaak: de
homepage werd wel opgehaald, maar de detectie vond er 'geen main-bundle' in — de site gebruikt
intussen een ander bundelformaat, waardoor stil op de verouderde 2022-salt werd teruggevallen en
de API alles met 403 weigerde. De extractie is nu formaat-onafhankelijk: de salt wordt eerst in de
homepage-HTML zelf gezocht (inline config), daarna in álle script- en preload-bundles (src én
href, dubbele én enkele quotes, main-achtige namen eerst, max 6 downloads). Getest op vijf
lay-outs: klassiek Angular (main.HASH.js), nieuwe Angular (main-HASH.js), Vite (index-HASH.js),
modulepreload-chunks en inline-HTML-salt. Faalt alles, dan logt de melding voortaan wélke bundles
gevonden werden of het begin van de pagina — zo is een WAF-blokkadepagina meteen herkenbaar in de
add-on-log.

## 0.27.5
- Börse Frankfurt HTTP 403 aangepakt. De 403's uit de log hadden twee waarschijnlijke oorzaken, die
beide zijn opgelost:
  - Cookies ontbraken: alle verkeer loopt nu via één gedeelde sessie die eerst de homepage bezoekt
(zoals een browser en zoals het werkende bf4py doet), zodat de WAF-cookies meegaan met de
API-calls. Losse verzoeken zonder cookies worden door hun beveiliging geweigerd. De headers zijn
ook volwaardig browser-achtig gemaakt (volledige User-Agent, Accept-Language, Sec-Fetch-*).
  - De salt kon stil verkeerd zijn: de detectie herkende alleen het oude bundelformaat
(main.HASH.js) en viel bij het nieuwe formaat (main-HASH.js) zonder enige logmelding terug op
een verouderde salt uit 2022 — met een ongeldige trace-id en dus 403 tot gevolg. De detectie
ondersteunt nu beide formaten en logt voortaan altijd welke salt-bron actief is
('dynamisch opgehaald' of 'TERUGVAL-salt gebruikt (reden)').
  - Extra: bij een 403 wordt eenmalig de salt vers opgehaald en opnieuw geprobeerd (de salt roteert
af en toe); blijft het 403, dan pauzeert de provider 10 minuten (circuit-breaker) zodat de log
niet volloopt en verversingen niet vertragen. Bij fouten wordt nu ook een stukje van het
antwoord gelogd, zodat een WAF-blokkade herkenbaar is.

## 0.27.4
- Restpunten uit de logs van de ISIN-flow opgelost (aanvulling op 0.27.3):
  - Geen 'Invalid ISIN number'-exceptions meer. yfinance gooit een exception zodra je een ISIN als
ticker doorgeeft die Yahoo niet kent; daardoor werd de ISIN-fallback in get_stock_info nooit
bereikt en vervuilde elke prijsverversing de log. Een ISIN wordt nu eerst via het
Yahoo-search-endpoint naar een verhandelbaar symbool vertaald; lukt dat niet, dan gaat de flow
meteen (zonder exception) naar de externe bronnen. Ook get_current_price slaat de rechtstreekse
Yahoo-call over wanneer het ticker een ISIN is.
  - Tradegate-lognoise beperkt: een niet-JSON-antwoord (ISIN noteert er niet, zoals bij het
ING-certificaat) wordt nu herkend als 'geen notering' i.p.v. een parsefout.
  - Streamlit-waarschuwing bij 'Land van herkomst' opgelost: de selectbox kreeg zowel een
default (index) als een waarde via session state (gezet door de info-ophaalflow). De default
loopt nu volledig via session state, zodat de warning met stacktrace uit de log verdwijnt.

## 0.27.3
- Börse Frankfurt effectief werkend voor warrants/certificaten. De 0.27.2-provider gebruikte
'quote_box/single' — dat blijkt een streaming-endpoint te zijn, geen gewone JSON-call, waardoor er
nooit een koers terugkwam. De provider is herschreven op basis van de bewezen werkende
bf4py-aanpak met echte JSON-endpoints: eerst worden de handelsplaatsen van het instrument
opgevraagd (instrument_information), daarna per handelsplaats de recentste bied-/laatkoers
(bid_ask_history — dekt illiquide certificaten zonder recente trade, zoals de 'Geld'-koers 12,22
van de ING-warrant) en anders de laatste EOD-slotkoers (price_history, afgelopen 14 dagen). De
MIC-lijst bevat nu ook de Zertifikate-platformen (XFRA/XSC1/XSCO). Verder is de
zomertijd-terugval gecorrigeerd (X-Security gebruikt Frankfurt-tijd; zonder tzdata in de container
wordt CET/CEST nu handmatig juist berekend i.p.v. vast +1u) en volgt de salt-extractie exact het
werkende bf4py-patroon. De volledige request-flow (headers, MIC-detectie, bid/ask- en EOD-pad) is
getest tegen een nagebootste API.

## 0.27.2
- Solide koersen voor warrants/certificaten via Börse Frankfurt. De Börse-Frankfurt-provider is
herschreven zodat hij effectief werkt voor structured products zoals ING-Markets-warrants (bv.
NL0015002RI2). Hun API vereist beveiligingsheaders (Client-Date, X-Client-TraceId, X-Security) met
een hash van tijd + URL + een salt die in hun JS-bundle zit en periodiek wijzigt. De salt wordt nu
dynamisch en zelfherstellend uit de live bundle gehaald (24u gecachet, met een terugval), de
X-Security gebruikt de Frankfurt-tijd (Europe/Berlin) ongeacht de serverzone, en er worden meerdere
handelsplaatsen geprobeerd (XFRA/XETR/XSTU/XGAT) met terugval op bied/laat als er geen slotkoers is.
- De hash-berekening is geverifieerd tegen het gedocumenteerde voorbeeld. Börse Frankfurt staat nu
vooraan in de ISIN-bronnenketen (vóór Tradegate).
Ticker als ISIN. Voegde je een effect toe met de ISIN in het Ticker-veld maar zonder het ISIN-veld
in te vullen, dan wordt de ticker nu zelf als ISIN gebruikt voor het ophalen van koersen.

## 0.27.1
- Verkoop van fractionele aandelen en verkoopdatum vóór de aankoop. Drie samenhangende fixes bij
het invoeren van een verkoop:
  -De verkoopvalidatie kijkt nu naar de positie op de verkoopdatum i.p.v. de totale positie.
Ligt de verkoopdatum vóór je aankoop (chronologisch onmogelijk), dan krijg je een duidelijke
melding om de datum te corrigeren. Voorheen kon je zo'n verkoop invoeren, waarna de FIFO de
verkoop tegen een lege positie verwerkte: het aandeel bleef volledig 'in bezit' én de winst werd
met kostbasis 0 geboekt, zodat de portefeuille dubbel telde.
  - Fractionele tolerantie: je kunt nu exact je volledige positie verkopen (bv. 5,1885) zonder de
melding 'onvoldoende positie'. Het aantalveld gebruikt bovendien een fijnere stap (0,0001) die
bij de 4 decimalen past.
  - Nieuwe optie '🔻 Volledige positie verkopen' bij een verkoop: vult automatisch exact je
beschikbare aantal op de gekozen datum in — handig bij fractionele aandelen.
Heb je al een verkoop met een datum vóór de aankoop ingevoerd? Corrigeer dan de verkoopdatum
in het transactie-overzicht (die is inline bewerkbaar); de portefeuille en gerealiseerde winst
worden dan meteen juist herberekend.

## 0.27.0
- Filterbug definitief weg op álle pagina's. De terugspringende tabbladen (kiezen van een filter
sprong terug naar het eerste tabblad en toonde plots het invoerformulier) zijn nu overal opgelost:
activa, transacties, dividenden, cash, AI-advies en instellingen gebruiken allemaal een blijvende
keuzeschakelaar i.p.v. st.tabs. Je blijft nu op de gekozen sectie terwijl je filtert of bewerkt.
- Gratis aandelen registreren zonder personenbelasting. Bij een aankoop kun je nu '🎁 Toegekend als
loon of gratis gekregen' aanvinken en daaronder '🆓 Écht gratis aandeel — geen personenbelasting'.
De waarde per stuk mag dan 0 zijn (de validatie 'prijs > 0' geldt niet meer voor toekenningen) en
er wordt geen personenbelasting bijgehouden; de kostbasis is gelijk aan de opgegeven waarde (€0 bij
een volledig gratis aandeel), geen TOB en geen cash-uitgave. De database-CHECK op de prijs is
versoepeld van > 0 naar >= 0; bestaande databases worden bij het opstarten automatisch en met
behoud van data gemigreerd.
- Effecten zonder ticker toevoegen (enkel ISIN). Vul je in het Ticker-veld een ISIN in (bv. een
ING-warrant NL0015002RI2) en klik je op 'Info ophalen', dan herkent de app dat het een ISIN is:
het ISIN- en landveld worden ingevuld, de munt wordt via een externe bron (Tradegate/Börse
Frankfurt) geprobeerd, en je hoeft enkel nog een naam in te geven. Koersen worden nadien
automatisch via de ISIN opgehaald; een handmatige koers blijft het laatste redmiddel.

## 0.26.2
- Dividenden herberekenen herstelt nu ook de cash-boeking. De herberekenknop keek enkel of de
keten (bronbelasting/RV/netto) klopte en sloeg een lijn over zodra dat zo was — óók als het
EUR-cashbedrag (cash_eur/net_eur) nog verouderd was. Daardoor leek de knop "niets te doen" en
bleef het cash-grootboek op de oude bedragen staan. De idempotentiecheck vergelijkt nu ook de
EUR-bedragen en de cash-boeking, zodat een verouderde cash-boeking wordt hersteld en het
cash-grootboek mee wijzigt. Klopt alles al, dan blijft de tabel ongemoeid.
- Filterbug op de dividendpagina opgelost. De pagina gebruikte tabbladen (Toevoegen / Overzicht);
bij het kiezen van een rekening- of jaarfilter herlaadt Streamlit en sprong de weergave terug naar
het eerste tabblad, waardoor plots het invoerformulier verscheen. De tabbladen zijn vervangen door
een blijvende keuzeschakelaar, zodat je op het overzicht blijft terwijl je filtert.

## 0.26.1
- Bugfix cash-grootboek bij EUR-herberekening. De knop "💱 Herbereken EUR-bedragen" werkte voor
dividenden enkel het bruto- en ingehouden bedrag in EUR bij, maar niet het netto- en cashbedrag
(net_eur/cash_eur). Daardoor bleef het cash-grootboek na een herberekening op de oude bedragen
staan. De herberekening bouwt nu álle EUR-velden van een dividend opnieuw op vanuit de native
keten (bruto → bronbelasting → RV → netto) met de wisselkoers op de dividenddatum, inclusief de
cash-boeking volgens de gekozen cash-basis. Het cash-grootboek volgt nu correct.

## 0.26.0
- Koersen via ISIN + meerdere bronnen. Effecten zonder Yahoo-notering (bv. ING-warrants met enkel
een ISIN, zoals NL0015002RI2) krijgen nu automatisch een koers. De ophaalvolgorde is: (1) Yahoo op
het ticker, (2) Yahoo via een symbool afgeleid uit de ISIN, (3) externe niet-Yahoo-bronnen op basis
van de ISIN (Tradegate, Börse Frankfurt), en pas (4) de handmatige koers als álles faalt. De
handmatige koers is dus niet langer prioritair maar het laatste redmiddel. Extra bronnen zijn
eenvoudig toe te voegen via _ISIN_PROVIDERS in market_data.py. get_stock_info herkent
bovendien een ISIN die als ticker wordt ingegeven en zoekt er een verhandelbaar symbool bij.
- Bugfix dividenden herberekenen na landcorrectie. De herberekening bouwt de keten nu telkens
opnieuw op vanaf ① bruto met het huidige land (buitenlandse bronbelasting) en de RV uit de
instellingen. Ze is zelfherstellend en idempotent: lijnen die al kloppen blijven ongemoeid, en
lijnen die na een import verkeerd stonden (bv. Belgische RV op een Amerikaans aandeel omdat het
land nog niet juist stond) worden hersteld zodra je het land corrigeert en opnieuw op herberekenen
klikt. Voorheen bleven zulke lijnen na de eerste herberekening vastzitten.
- ID-kolom terug in de dividendtabel. De (alleen-lezen) ID-kolom staat weer vooraan, zodat je snel
het juiste dividend kunt selecteren om te verwijderen.

## 0.25.1
- kleine fixes
- handmatige koers is mogelijk

## 0.25.0
- Bugfix dividendafhandeling — automatische RV/netto-berekening. Bij de bulk-import en de
inline-tabel werd de dividendketen aangeroepen zonder het RV-tarief en de bronbelasting, waardoor
bij het opladen van enkel het brutobedrag geen roerende voorheffing en netto berekend werden
(netto = bruto). Nu worden de Belgische RV (uit de instellingen) en de buitenlandse bronbelasting
(uit het land van het activum) automatisch toegepast bij zowel import als inline bewerken.
- Herbereken-knop voor bestaande lijnen. Op de dividendenpagina staat nu "🔄 RV en netto
herberekenen (lijnen zonder RV)": dit herstelt eerder geïmporteerde lijnen waar nog niets werd
ingehouden (netto ≈ bruto), zonder correct ingevoerde lijnen aan te raken.
- ID-kolom verwijderd uit de dividendtabel (bewerken gebeurt positioneel; de ID was overbodig).
- De 🇧🇪 RV-kolom (berekend) is toegevoegd voor controle.
- Interest & securities lending. Nieuwe kolom "Soort" bij inkomsten (Dividend / Interest /
Securities lending), in het invoerformulier, de inline-tabel en de bulk-import (kolom kind).
Enkel echte dividenden tellen mee voor de €833-vrijstelling; interest en securities lending worden
apart bijgehouden (ze hebben hun eigen fiscale regels) maar lopen wel gewoon mee in de cashpositie.

## 0.24.0
- Performance shares — drie zienswijzen (dashboard-brede toepassing). De vroegere aan/uit-toggle
is vervangen door een keuze uit drie modi, die nu doorwerkt in totaal geïnvesteerd, de
ongerealiseerde W/V, de kostenweergave én het staafdiagram (voorheen enkel het diagram):
  -Personenbelasting als kost — de aandelen krijgen kostbasis €0 (ongerealiseerde W/V = volledige
huidige waarde) en de personenbelasting verschijnt als kost ("Kosten (txn + rekening + personenbel.)").
  - Personenbelasting als investering — kostbasis = betaalde belasting; de meerwaarde start vanaf
die belasting (reële winst = huidige waarde − belasting). Geen aparte kost.
  - Personenbelasting negeren — meerwaarde t.o.v. de toekenningsprijs; de belasting telt niet mee.
De keuze wordt gedeeld met de portefeuillepagina. Toerekening gebeurt pro rata bij een gedeeltelijke
verkoop.
- Dividendvrijstelling in de personenbelasting (nieuw). De app houdt nu rekening met de
vrijstelling van roerende voorheffing op 'gewone' aandelendividenden (instelbaar, standaard
€833 per persoon — max €249,90 recupereerbare RV p.p.), inclusief het aantal personen uit je
huwelijksstelsel. Fonds-/ETF-dividenden tellen niet mee. Optioneel: de FBB voor Franse aandelen
(15% van het netto na Franse bronheffing, in te schakelen in ⚙️ Instellingen).
  - Op het dashboard toont de dividendmetric het recupereerbare voordeel als delta.
  - Op de dividendenpagina verschijnt per selectie/jaar het recupereerbare bedrag.
  - Op de 🧾 Belgische Belasting-pagina staat een volledige uitwerking per jaar (in aanmerking
komende dividenden, recupereerbare RV, FBB, optimalisatietips, codes 1437/2437).
- Toegekende effecten breder ondersteund. De toekennings-optie in het transactieformulier heet nu
"Toegekend als loon (warrants, RSU, gratis/bonus aandelen)" en dekt zo ook warrants (bonus van het
werk met bedrijfsvoorheffing op de basiswaarde) en gratis aandelen (belasting op 0 = geen kost).

## 0.23.0
- Meerdere rijen tegelijk verwijderen (alle tabellen). Elke tabel heeft nu een multiselect
om één of meerdere rijen te kiezen, met een wis-knop die pas na een EXPLICIETE bevestiging
uitvoert (overzicht van wat verwijderd wordt + "Ja, definitief verwijderen" / "Annuleren").
Toegepast op: transacties, activa, dividenden, rekeningkosten, splitsingen en handmatige
cash-bewegingen.
- Inline bewerkbare tabellen overal. De vormgeving en functionaliteit van de dividenden- en
kostentabellen (rechtstreeks in de tabel bewerken + "💾 Wijzigingen opslaan") is doorgetrokken:
  - Transacties: datum, type (aankoop/verkoop), aantal, prijs, munt, rekening, kosten,
koersdoel, performance shares (+ personenbelasting) en notities zijn inline bewerkbaar.
  - Totaal, EUR-tegenwaarde en TOB worden bij het opslaan herberekend. Het aparte
bewerkformulier en het klik-systeem zijn vervangen.
  - Activa: naam, type, ETF-type, BE-registratie, munt, land, beurs, ISIN en de
fotomomentwaarde zijn inline bewerkbaar (EUR-fotomomentwaarde wordt herberekend). Nieuwe
knop "📸 Ophalen (ontbrekende)" haalt de slotkoers 31/12/2025 op voor alle activa zonder
fotomoment. Ticker corrigeren zit in een aparte uitklapsectie.
  - Splitsingen: overzicht in tabelvorm; verwijderen nu ook met bevestiging (voorheen wiste
één klik direct).
- Validatie bij het inline opslaan: ongeldige datums/bedragen en inconsistente rijen worden per
rij gemeld en overgeslagen; de rest wordt gewoon opgeslagen.

## 0.22.0
- Dividenden — slimmer invoerformulier (gedetailleerde modus):
  - Lege velden worden live berekend en getoond; met de knop "🪄 Vul lege velden in" worden de
berekende bedragen in de invoervelden zelf gezet, zodat je ze kunt nakijken en aanpassen vóór
het opslaan.
  - Omgekeerde controle (④ → ③ → ② → ①) die de keten terugrekent en afwijkingen meldt, met
een tolerantie van ± €0,02 voor afrondingsfouten.
  - De munt volgt het gekozen activum: wissel je van activum, dan springen de muntvelden mee
naar de munt van dat activum.
  - Buitenlandse bronbelasting automatisch berekend op basis van het land van het activum en
de heffingstarieven in ⚙️ Instellingen → 🏛️ TOB & bronbelasting (bewerkbare tabel per land,
met indicatieve standaardtarieven). Het voorgestelde bedrag blijft aanpasbaar.
  - Land van herkomst toegevoegd aan activa (toevoeg- en bewerkformulier + bulk-import); bij
"Info ophalen" wordt het land afgeleid uit de ISIN.
  - Help-icoontjes bij de vier bedragvelden die uitleggen wat elk veld is en wanneer je het
invult (① enkel voor buitenlandse activa; ③ het brutodividend van Belgische aandelen; ④ wat
er effectief overblijft; ② wordt automatisch voorgesteld).
  - De Belgische roerende voorheffing is nu instelbaar in het invoerformulier (standaard 30%,
bv. 15% voor VVPR-bis) en wordt gebruikt om ④ uit ③ af te leiden (of omgekeerd).
  - Cash-boeking op basis van een gekozen veld: per dividend kies je exclusief of het netto
(④, standaard), het bruto na bronbelasting (③) of het bruto vóór bronbelasting (①) als
dividendregel in het cash-grootboek (💶 Cash) geboekt wordt — handig wanneer je broker bruto
stort en belastingen later apart afhoudt.
- Dividenden — inline bewerken in de tabel. Het overzicht is nu een bewerkbare tabel
(datum, rekening, bedragen ①–④, munt, cash-basis, notities): pas rechtstreeks in de tabel aan
en klik op "💾 Wijzigingen opslaan". De keten, RV en EUR-bedragen worden bij het opslaan
herberekend en gecontroleerd (rijen met een inconsistente keten worden geweigerd met uitleg).
- Het aparte bewerkformulier en het klik-systeem zijn vervangen; verwijderen gebeurt via een
selectie met bevestiging.
- Rekeningkosten — zelfde vormgeving en functionaliteit als dividenden: een inline bewerkbare
tabel (datum, rekening, omschrijving, bedrag, munt) met "Wijzigingen opslaan" (EUR wordt
herberekend) en verwijderen met bevestiging.
- Bulk-import bijgewerkt: nieuwe kolommen land (Transacties — voor het aanmaken van nieuwe
activa) en cash_basis (Dividenden — netto/bruto_na/bruto_voor); template en instructieblad
aangepast.

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