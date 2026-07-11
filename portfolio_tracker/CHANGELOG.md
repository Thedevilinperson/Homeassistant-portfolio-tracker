# Changelog

Alle noemenswaardige wijzigingen aan de Portfolio Tracker add-on.

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