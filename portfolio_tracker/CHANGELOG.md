# Changelog

Alle noemenswaardige wijzigingen aan de Portfolio Tracker add-on.

## 1.8.17
### 🔀 Fonds transfereren (fondsfusie / klasse-omzetting)

Een nieuwe sectie **➕ Transacties → 🔀 Fonds transfereren** voor een fondsfusie of
klasse-omzetting (bv. kapitalisatie → distributie van hetzelfde fonds, of een
ISIN-wijziging bij een fusie — zoals bij het ENGIE-FCPE-fonds). Economisch blijft
dat dezelfde belegging: **geen verkoop**, geen beurstaks, geen gerealiseerde
meer- of minwaarde.

**Wat er verhuist**

- De **kostbasis** én de **oorspronkelijke aankoopdatum per lot** verhuizen exact
  mee naar het bestemmingsfonds — cruciaal voor de fotomoment-grens van het
  meerwaarderegime (van kracht sinds 2026): een lot van vóór 2026 blijft ook ná een
  transfer zijn fotomoment-bescherming behouden.
- Een eventuele **blokkering** (bv. een werkgeversplan/FCPE dat nog niet vrij is)
  verhuist mee, met een duidelijke waarschuwing als dat het geval is.
- Een gedeeltelijke transfer wordt FIFO verwerkt: de oudste stukken verhuizen
  eerst, net als bij een gewone verkoop.

**Hoe het technisch werkt**

- Eén 'verkoop' op het bronfonds en één 'aankoop' per meegenomen lot op het
  bestemmingsfonds, allebei gemarkeerd als transfer (`is_transfer`) en gekoppeld
  via een gedeelde `transfer_group`.
- **Geen cashbeweging**: een transfer telt voor €0 in de cashpositie en het
  cash-grootboek, net als een toekenning of stockdividend.
- **Geen beurstaks, geen belastbare winst**: de fiscale motor (FIFO-kern) boekt
  voor een transfer altijd 0 gerealiseerde én 0 fiscale winst/verlies, ongeacht de
  ingebedde meerwaarde — die blijft gewoon verder leven als ongerealiseerd op het
  bestemmingsfonds, zodat ze nergens dubbel geteld wordt.
- De transferdatum (niet de oorspronkelijke datum) bepaalt de FIFO-volgorde en de
  plaats in de portefeuille-evolutie; de oorspronkelijke datum (`origin_date`) telt
  apart voor de fotomoment-grens. Zo blijven chronologie én fiscaliteit allebei
  correct, ook als het bestemmingsfonds al langer eigen transacties had.
- Een logboek met alle transfers, en "ongedaan maken" via de bestaande
  prullenbak/undo-mechaniek (verwijdert beide benen samen, in één klik terug te
  zetten).
- Transferregels zijn herkenbaar in 📋 Overzicht (🔀 Transfer-uit/-in) en in de
  jaaroverzichten op 🧮 Belasting (🔀 Transfer i.p.v. Verkoop, altijd €0 W/V).

Bedoeld voor een **gedwongen fondsgebeurtenis**, niet voor een bewuste switch naar
een ander fonds — boek die laatste gewoon als een normale verkoop + aankoop, zodat
de meerwaarde wél correct belast wordt.

## 1.8.16
### 📈 Golden cross / death cross

Een nieuwe tab op de statuspagina, **📈 Golden/Death Cross**, die het 50-daags
gemiddelde (MA50) naast het bestaande 200-daags gemiddelde (MA200) zet en elk
kruispunt tussen de twee bijhoudt.

**Wat een golden/death cross is**

Een **golden cross** is het moment waarop MA50 van onder naar boven door MA200
breekt — algemeen gelezen als een bullish signaal. Het omgekeerde, een **death
cross**, wordt als bearish gelezen. Het zijn achterlopende trendmaatstaven, geen
koop- of verkoopsignalen op zich: ze bevestigen een trendwissel pas nadat die al
bezig is, en geven in een zijwaartse markt makkelijk valse signalen.

**Hoe de app het bijhoudt**

- Een apart logboek (`ma_cross_events`), los van de gewone statusmeldingen: een
  kruising is een vaststaand feit op een vaste datum, geen toestand die later weer
  kan verdwijnen zoals een verouderde koers.
- Detectie kijkt ongeveer 2,5 jaar terug over de koersreeks van elke open positie,
  herkent elk punt waar MA50 en MA200 van teken wisselen, en registreert enkel wat
  nog niet in het logboek stond — dezelfde kruising wordt bij een volgende controle
  dus niet dubbel geteld.
- Draait automatisch mee met de dagelijkse statuscontrole (22:45); kan ook manueel
  met de knop op de nieuwe tab.
- Gebruikt dezelfde koersreeks als de rest van de app (`auto_adjust=False`, en voor
  een gekoppeld fonds automatisch de fondsformule), zodat een MA50/MA200 voor bv.
  het ENGIE-FCPE-fonds consistent blijft met de koers die elders getoond wordt.

**Wat je op de nieuwe tab ziet**

- Een tabel met MA50, MA200, koers en actuele stand ("golden" of "death") per open
  positie, met de datum van de laatst gekende kruising.
- Een grafiek per gekozen activum: koers, MA50 en MA200, met markers op elk
  gedetecteerd kruispunt.
- Het volledige chronologische logboek van alle gedetecteerde kruisingen.

## 1.8.15
### 📅 Dividendkalender, uitschieters uit de koersdoelen en het 200-daags gemiddelde

Negen punten in één versie. De rode draad: cijfers die je al zag, worden
betrouwbaarder, en wat je tot nu toe zelf moest opzoeken staat nu in de app.

**📅 Nieuw: dividendkalender** (💰 Dividenden → 📅 Kalender)

Per activum de uitkeringen met hun **betaaldatum**, het brutobedrag per aandeel en
de ex-datum. Elke uitkering staat apart, dus een interimdividend (acompte) en het
saldo zijn twee lijnen met elk hun eigen datums en bedrag. Bij elke lijn staat wat
je op de ex-datum aanhield, per rekening, en het geschatte brutobedrag.

De datum die telt is de **betaaldatum**: dat is de dag waarop het geld op je
rekening komt en dus de datum waarop een dividend geboekt hoort te worden. De
ex-datum staat er los naast — dat is de dag VANAF wanneer een aankoop geen recht
meer geeft op die uitkering (koop je op die dag zelf, dan krijg je ze al niet meer).

Twee bronnen: Yahoo altijd, en optioneel Financial Modeling Prep. Yahoo kent van
VOORBIJE uitkeringen enkel de ex-datum, niet de betaaldatum; met een FMP-sleutel
(⚙️ Instellingen → 📊 Gegevensbronnen) worden die aangevuld. Let op: op het gratis
plan van FMP zitten enkel Amerikaanse noteringen — voor Euronext heb je een betalend
plan nodig. Zonder sleutel werkt alles gewoon door en vul je ontbrekende
betaaldatums zelf aan. Wat je zelf invoert, wordt door een ophaling nooit
overschreven.

De planner ververst de kalender dagelijks om 23:40, voor je open posities én voor de
aandelen die de AI de laatste 30 dagen voorstelde.

**📥 Een uitkering boeken met één klik**

De knop "Boek dit dividend" vult het gewone dividendformulier in met het activum, de
rekening, de betaaldatum en het geschatte bruto (aantal × bedrag per aandeel). Bij
een buitenlands aandeel komt dat bedrag als ① bruto vóór bronbelasting, bij een
Belgisch als ③ — zo klopt de fiscale keten meteen. Er wordt bewust NIETS
rechtstreeks weggeschreven: een aangekondigd bedrag kan nog wijzigen en je broker
rekent af op zijn eigen datums en koersen, dus jij kijkt na en slaat op. Staat er al
een dividend rond die datum, dan waarschuwt de app voor een dubbele boeking. Een
uitkering die nog moet komen, kan je niet boeken — dat zou je cashsaldo en je
aangifte vooruit laten lopen op de feiten.

**📅 Waarschuwing voor aankomende ex-dividenddatums** (dashboard)

Voor je eigen posities én voor de aandelen die de AI voorstelt: welke ex-datums
vallen binnen veertien dagen. Bij een suggestie is dat een timingsgegeven — koop je
ná de ex-datum, dan mis je die uitkering. Er staat uitdrukkelijk bij dat de koers op
de ex-datum doorgaans met ongeveer het dividendbedrag zakt; er ontstaat dus geen
gratis winst door er net voor te kopen.

**💰 Nieuw op 🩺 Status: voorbije dividenddatums**

Een aparte tab met de uitkeringen waarvan de betaaldatum voorbij is terwijl er nog
niets geboekt staat — enkel voor activa waarvoor je op de ex-datum effectief stukken
had. Een werklijst dus, geen opsomming. Er wordt gezocht binnen drie weken rond de
datum, want de valutadatum van je broker wijkt vaak af.

**🎯 Uitschieters tellen niet meer mee in de koersdoelen**

De AI geeft af en toe een koersdoel dat nergens op slaat: een komma verkeerd, een
ander aandeel bedoeld, of gewoon een uitschieter. Eén zo'n waarde trok het
gemiddelde over negen bepalingen volledig scheef — en dat gemiddelde stond
vervolgens als "het koersdoel" in je tabellen. Er wordt nu rond de MEDIAAN gefilterd
(mediaan + MAD, met een harde grens op 50% afwijking), op één plek in de code zodat
geen enkele tabel eruit kan lopen. Bij minder dan drie bepalingen wordt er niets
geweerd: met twee cijfers valt niet uit te maken welk van beide de uitschieter is.
Is een reeks gewoon sterk gespreid zonder aanwijsbare uitschieter, dan telt alles
mee.

**🎯 Nieuwe kolommen "AI 30d" en "Pot. 30d"** (💼 Portefeuille en 📊 Dashboard)

Het gemiddelde AI-koersdoel van de laatste 30 dagen, uitschieters eruit, naast het
koersdoel dat GELDT. Dat laatste kan een handmatig doel zijn; deze kolom toont wat
de AI de afgelopen maand dacht, los daarvan. Beide naast elkaar laten meteen zien of
je eigen doel nog in de buurt van het AI-beeld ligt.

**🎯 Gemiddeld koersdoel per periode** (🤖 AI Advisor → marktopportuniteiten)

Bij de opvolging van de voorgestelde aandelen staat nu het gemiddelde koersdoel over
de GEKOZEN periode (7 dagen / 1 maand / 3 maanden), plus het potentieel tegenover de
koers van nu. Het laatste koersdoel alleen zei weinig bij een aandeel dat vijf keer
werd voorgesteld.

**📉 Nieuw: 200-daags voortschrijdend gemiddelde** (📈 Evolutie)

Voor de aandelen die je NU aanhoudt: het gemiddelde van de laatste 200 slotkoersen,
de verhouding van de koers tot dat gemiddelde, en een grafiek per positie. Het is een
trendmaatstaf, geen koopsignaal: ver boven het gemiddelde betekent ook een minder
gunstig instapmoment, en ver eronder maakt een aandeel niet vanzelf koopwaardig.
Berekend zonder dividendcorrectie — een gecorrigeerde reeks ligt in het verleden
lager en zou het gemiddelde te laag zetten. Staat het gemiddelde op minder dan 200
slotkoersen, dan zegt de tabel dat erbij.

Dezelfde cijfers gaan als `ma200` en `koers_vs_ma200_pct` mee naar de AI-adviseur bij
het dagelijkse portefeuilleadvies, met de opdracht de trend expliciet mee te wegen.
Bij volledige privacymodus gaat enkel het percentage mee, niet het koersniveau.

**🧾 AI-kosten handmatig ingeven** (🤖 AI Advisor)

De bedragen die de app toonde, zijn een RAMING uit tokengebruik en richtprijzen. Je
werkelijke OpenAI-factuur kan je nu zelf ingeven. Die staat bewust NAAST de raming en
wordt er niet bij opgeteld: het zijn twee metingen van dezelfde kost, geen twee
kosten. Handmatige bedragen tellen ook niet mee in de kost-per-oproep die de app
elders raamt — anders zou een factuurregel het gemeten tokengemiddelde vervuilen en
elke raming in de app slechter maken.

**📄 Een dividend overnemen van een eerder dividend**

Zoals bij de transacties: activum, rekening, munt, de keten ①-④, de cash-boeking en
het effectief toegepaste RV-tarief (bv. VVPR-bis 15% in plaats van blind 30%) worden
overgenomen. De datum wordt vandaag; bedragen overnemen is optioneel.

**🗑️ De eenvoudige invoerwijze voor dividenden is weg**

Alleen de gedetailleerde invoer blijft. De eenvoudige variant sloeg de keten over en
leverde lijnen op waar de bronbelasting, de RV en de €833-vrijstelling achteraf niet
meer uit af te leiden waren.

### ⚠️ "Sinds je vorige bezoek" hing af van je filterselectie

Het bedrag in het bezoekblok werd berekend op de rekeningen die je toevallig
geselecteerd had. Met één rekening actief verscheen de aangroei van alleen die
rekening als "je portefeuille ging X vooruit". Erger: dat gefilterde bedrag werd ook
als referentie weggeschreven, zodat je bij een volgend bezoek met een ándere filter
een verschil zag dat nergens op sloeg. Het blok rekent nu altijd op je VOLLEDIGE
portefeuille — dat is een eigenschap van je portefeuille, niet van je schermkeuze.
Staat er een filter aan, dan zegt de melding dat er uitdrukkelijk bij.

## 1.8.14
### ⚠️ Posities zonder koers verdwenen stilzwijgend uit je totalen

Een positie waarvoor geen koers bekend is, telde als niets. Ze stond wel in de
tabel, met een lege kolom Koers en een lege Huidige waarde, maar in "Totale
waarde", op het dashboard en in de blootstelling ontbrak ze volledig — zonder
enige melding. Bij een gewoon aandeel is dat een tijdelijke hapering. Bij een
werkgeversfonds is het de normale toestand: een QS-ISIN noteert nergens, dus
zolang er geen koppeling ingesteld is, blijft die koers uit, hoe vaak je ook
ververst.

Twee plaatsen zeggen dit nu:

- **💼 Portefeuille** meldt onder de totalen hoeveel posities zonder koers er
  zijn, welke dat zijn, en dat ze niet meegeteld zijn.
- **🏢 Activa → 🔗 Koppelingen** toont bovenaan de posities die je wél bezit maar
  die noch een koers noch een koppeling hebben, met de suggestie om ze te
  koppelen. Voor een 1:1-fonds (Classic, Liberty) is dat basis 0, multiplicator
  1 en referentie 0.

De lijst gebruikt dezelfde FIFO-berekening als het dashboard, zodat hij niet uit
de pas kan lopen met wat je elders ziet.

## 1.8.13
### 🎯 Kalibreren werkt nu ook als de NAV op andere dagen gepubliceerd wordt

De kalibratie gebruikte als koers van de onderliggende waarde uitsluitend de
bewaarde WAARNEMINGEN. Ze kon daardoor alleen rekenen op datums waarop toevallig
zowel een waarneming als een gepubliceerde NAV stond. Voor een fonds dat op de
15e wordt waargenomen maar op de 25e gewaardeerd, overlapte er geen enkele
datum: de kalibratie haakte af met de melding "haal eerst de waarnemingen op",
terwijl die er wel degelijk stonden.

De koers wordt nu voor ELKE NAV-datum bepaald. Bestaat er een waarneming op die
dag, dan krijgt die voorrang — die is gecontroleerd. Voor de rest wordt de
koershistoriek van de onderliggende waarde gebruikt, zonder dividendcorrectie en
met de laatste slotkoers op of vóór die dag, zodat een NAV-datum die op een
feestdag valt niet wegvalt.

### 💬 De melding zegt nu wat er werkelijk ontbreekt

"Haal eerst de waarnemingen op" verscheen bij elke reden waarom de kalibratie
niet startte. Er staat nu wat er echt aan de hand is: geen NAV ingelezen, geen
waarnemingen, te weinig bruikbare datums (met hoeveel er bruikbaar zijn en
waarom), of een aanvangsdatum die ná de NAV-reeks ligt — in dat laatste geval is
de berekende waarde overal de inschrijvingsprijs en valt er niets te passen.

## 1.8.12
### 📥 De NAV-export wordt niet meer blind ingelezen

Een export van de beheerder bevat meestal ALLE fondsen van je plan onder elkaar,
elk met zijn eigen waarderingsdata. De inlezer nam per regel de eerste datum en
het eerste getal dat hij tegenkwam, zonder te kijken bij welk fonds die regel
hoorde. Alles belandde daardoor bij één fonds: meerdere NAV-waarden per maand,
waarvan er maar één klopte. De kalibratie probeerde vervolgens een formule door
punten van drie verschillende fondsen te leggen, wat een referentieprijs oplevert
die nergens op slaat.

De app leest nu eerst wat er in het bestand zit en toont wat ze vindt:

- **Welke reeksen** erin zitten, met per reeks het aantal regels en de
  datumperiode. Bevat het bestand er meer dan één, dan kies je zelf welke bij dit
  fonds horen; reeksen waarvan de omschrijving het ticker of de naam van je fonds
  bevat, staan al aangevinkt.
- **Welke kolom de NAV is**, als er meerdere getalkolommen zijn — met een paar
  voorbeeldwaarden erbij, zodat je het bedrag herkent en niet per ongeluk het
  aantal deelbewijzen inleest.
- **Hoeveel regels** je gaat inlezen en over welke periode, met een waarschuwing
  als er nog steeds meerdere waarden in dezelfde maand zitten.

Ook het lezen zelf is steviger: het scheidingsteken van een csv wordt herkend
(een Franse export gebruikt vaak een kommapunt, juist omdát de komma het
decimaalteken is), bedragen als "1.234,56" worden correct gelezen, en een getal
kan niet langer per ongeluk als datum geïnterpreteerd worden.

### 🗑️ Ingelezen NAV wissen

Onder de vergelijkingstabel staat een knop om de volledige ingelezen reeks van
dit fonds te wissen. Zonder die knop was een verkeerd ingelezen bestand alleen
via een herstel uit back-up weg te krijgen.

### ⚠️ Meerdere NAV's in dezelfde maand worden gemeld

De vergelijkingstabel controleert nu of er maanden zijn met meer dan één
officiële NAV. Dat kan voor één fonds niet, dus het betekent dat er regels van
een ander fonds tussen zitten. De app zegt dat met zoveel woorden, met de
betrokken maanden erbij, en waarschuwt dat de gekalibreerde referentieprijs
zolang onbruikbaar is.

## 1.8.11
### ↩️ Vorige parameters terugzetten

Elke opslag van een fondsformule bewaart voortaan de set die er stond. Onder de
knoppen verschijnt dan wanneer die bewaard is en welke kernparameters
verschillen, met een knop om ze terug te zetten. Zo kost een vergissing — het
verkeerde fonds geselecteerd, een parameter verkeerd overgetypt — één klik in
plaats van een herstel uit back-up, waarbij je al je andere werk van die dag
kwijtspeelt.

Het terugzetten is zelf ook omkeerbaar: de teruggezette set wordt op haar beurt
de "vorige", zodat je heen en weer kunt tot je zeker bent welke de juiste is.
Alleen de laatste stap wordt bewaard; dat volstaat voor dit soort vergissing en
houdt de opslag klein.

Let op: dit werkt vanaf deze versie. Een overschrijving van vóór 1.8.11 kan de
app niet terughalen — daarvoor is de back-up van vóór die bewerking nodig.

### 🌐 Majoraties voorstellen uit de dividendhistoriek

Onder het majoratieveld zit een nieuw blok dat de dividendhistoriek van de
onderliggende waarde ophaalt en daaruit de majorations berekent:

    bedrag per deelbewijs = aandelen per deelbewijs × percentage × dividend per aandeel

Beide factoren zijn instelbaar (standaard 10 aandelen en 10 procent) en worden
mee opgeslagen. De app bepaalt zelf vanaf welk jaar een dividend recht geeft op
een majoration: twee volle kalenderjaren op naam, dus voor een fonds dat op 22
december 2022 begint is dat het dividend van 2025, en voor een fonds van
februari 2024 dat van 2027. Oudere dividenden worden niet voorgesteld.

Het resultaat is een TABEL, geen automatische invulling. Per regel staat de
ex-datum, het dividend per aandeel, het berekende bedrag en of die datum al
ingevuld is: 🆕 nieuw, ✅ gelijk of ⚠️ wijkt af. Enkel de nieuwe regels kunnen met
één knop toegevoegd worden; wat jij al ingevuld hebt wordt nooit aangepast.

Dat laatste is bewust. Een koersdatabank weet niet welke uitkeringen effectief
in aanmerking kwamen — een interimdividend, een uitkering in stukken, een
ex-datum die een dag verschilt van de betaaldatum van de beheerder — en alleen
de afrekening van de beheerder weet dat wel. Wijkt een voorstel af van jouw
cijfer, dan is dat een signaal om na te kijken, geen reden om jouw cijfer te
overschrijven.

## 1.8.10
### 🐛 Bij het omschakelen naar een ander gekoppeld fonds bleven de parameters van het vorige staan

Wie een tweede fonds koppelde (bijvoorbeeld een Link Multiple van een andere
jaargang naast die van 2022), kreeg na het omschakelen in de keuzelijst nog
steeds de parameters van het eerste fonds in de invoervelden te zien: α,
referentieprijs, inschrijvingsprijs, aanvangsdatum, eerste waarnemingsmaand. Het
scherm toonde dan een mengeling: de groene balk en de berekende waarde hoorden
bij het geselecteerde fonds, de velden eronder bij het vorige. En omdat de
waarnemingsdata uit die velden volgen, leek het nieuwe fonds de waarnemingsreeks
van het oude over te nemen.

De oorzaak zat in Streamlit: een invoerveld met een vaste sleutel negeert zijn
'value'-argument zodra er voor die sleutel al iets in de sessietoestand staat.
Alle velden van beide koppelingspanelen deelden zo'n vaste sleutel, dus ze
werden bij het wisselen van fonds nooit opnieuw uit de database gevuld. Elk veld
heeft nu een sleutel per activum.

Dit was niet alleen verwarrend maar ook riskant: op 'Opslaan en activeren'
drukken schreef de parameters van het ene fonds weg bij het andere. Ga daarom
na plaatsing je gekoppelde fondsen even na (zie de plaatsingsgids).

### 🆕 Duidelijke waarschuwing bij een fonds zonder parameters

Kies je een fonds dat nog niet ingesteld is, dan meldt de app nu expliciet dat
de getoonde waarden VOORBEELDEN uit de jaargang 2022 zijn en niet voor een
andere jaargang gelden. Elke jaargang heeft een eigen α, referentieprijs,
inschrijvingsprijs, aanvangsdatum, eindvervaldag en eerste waarnemingsmaand.

### 🧹 Waarnemingen die niet bij de reeks horen worden gemeld

Bewaarde waarnemingen waarvan de datum niet voorkomt in de waarnemingsdata die
uit de ingevulde parameters volgen, horen bij een andere reeks. Ze telden wel
gewoon mee in de waardering. De app meldt ze nu, met de eerste vijf datums
erbij, en biedt een knop om precies die waarnemingen te verwijderen. De rest
blijft staan.

## 1.8.9
### 📈 Gekoppelde fondsen verschijnen nu ook in de grafiek op Evolutie

De gereconstrueerde historiek op 📈 Evolutie werkte met koersreeksen die
rechtstreeks bij Yahoo opgehaald worden. Een QS-ISIN heeft daar geen notering,
dus voor een werkgeversfonds kwam er niets terug en viel het fonds uit de
reconstructie weg: de grafiek toonde een portefeuille zonder dat fonds, terwijl
het dashboard, de portefeuillepagina en de fiscale berekening het wel volledig
meetelden.

Er valt voor zo'n fonds ook niets op te halen — er bestaat geen reeks. De reeks
wordt daarom gerekend in plaats van opgevraagd, met dezelfde formule en dezelfde
parameters als de actuele koers. Dat geldt voor beide methodes:

- **Afgeleide koers**: de formule op de historische koers van de onderliggende
  waarde, ondergrens inbegrepen.
- **Fondsformule**: per dag opnieuw, met de waarnemingen die op díé dag al
  bestonden en de slotkoers van die dag voor alles wat toen nog openstond.
  Rekenen met waarnemingen die pas later gebeurd zijn zou de grafiek achteraf
  gelijk geven met kennis die er toen niet was.

De koersreeks van de onderliggende waarde wordt daarvoor ZONDER
dividendcorrectie opgehaald (auto_adjust=False). Dat is geen detail: een
gecorrigeerde reeks ligt in het verleden lager dan de werkelijke slotkoersen, en
met een hefboom van 16 zou dat verschil de historische waarde van het fonds ver
naast de werkelijkheid zetten. De formules van het reglement rekenen op de
werkelijke slotkoers, niet op een herrekende.

Een kringverwijzing (een gekoppeld activum dat naar zichzelf wijst) wordt na
drie stappen afgebroken, net als bij de actuele koers en het fotomoment.

### 🔒 Eén plaats voor de formuleparameters

De parameters van de fondsformule worden nu op één plaats uit de configuratie
gelezen, en van daaruit gebruikt door zowel de actuele waardering als de
historische reeks. Zo kunnen die twee niet uiteenlopen: de grafiek toont
gegarandeerd hetzelfde fonds als het dashboard.

### 📖 Handleiding

Hoofdstuk 3.10 vermeldde het ontbreken van gekoppelde fondsen in de
evolutiegrafiek als bekende beperking. Dat stuk is vervangen door een uitleg van
hoe de historische reeks nu berekend wordt en waarom de onderliggende reeks
ongecorrigeerd opgehaald wordt. De tabel met symptomen heeft er een regel bij.

## 1.8.8
### 🕒 FCPE: een waarneming wordt pas vastgelegd na sluiting van de beurs

Een "Relevé i" is per fondsreglement de SLOTKOERS van de waarnemingsdatum (de
15e van de maand, of de beursdag ervoor). De app haalde die datum al op zodra
ze aanbrak — dus ook midden op de dag, terwijl de beurs nog open was. De
koers van dat moment werd dan als officiele waarneming weggeschreven, en
omdat een bewaarde waarneming niet meer overschreven wordt, bleef die fout er
voorgoed in zitten. Elke fout van dat type zit met een gewicht van 1/60 en
een factor alfa (16) in de waarde: 10 cent verschil op een waarneming is
ongeveer 2,7 cent per deelbewijs, permanent.

Vanaf nu telt een waarnemingsdatum pas mee vanaf 18u Parijse tijd (Euronext
sluit om 17u30, slotveiling tot 17u35). Tot dan blijft de waarneming open en
wordt ze — net als alle nog niet gebeurde waarnemingen — ingevuld met de
actuele koers, precies zoals het reglement voorschrijft bij een vervroegde
uitstap.

### 🩺 Controlepas op eerder opgehaalde waarnemingen

De knop "🔄 Waarnemingen ophalen" legt de al bewaarde waarnemingen nu opnieuw
naast de definitieve slotkoers en werkt ze bij als ze afwijken. Zo verdwijnt
een intraday-koers die eerder werd vastgelegd alsnog uit de reeks. Enkel
waarnemingen die de app zelf ophaalde (bron "auto:...") komen daarvoor in
aanmerking; handmatig ingevoerde of gecorrigeerde waarnemingen blijven
onaangeroerd. Werd er iets bijgewerkt, dan meldt de app dat expliciet — je
parameters (referentieprijs, inschrijvingsprijs) zijn dan gekalibreerd op
cijfers die intussen veranderd zijn en verdienen een herkalibratie.

De automatische koersverversing (om de 5 minuten) doet die controlepas NIET:
ze haalt daarvoor telkens de volledige koershistoriek opnieuw op.

### 👀 De meldingen van "Waarnemingen ophalen" zijn nu ook echt zichtbaar

De knop toonde het resultaat en deed daarna meteen een herlaadbeurt, waardoor
het net getekende scherm — inclusief die meldingen — werd weggegooid. Je klikte
dus op de knop en zag ogenschijnlijk niets gebeuren. Die herlaadbeurt is
geschrapt: alles wat onder de knop staat (de tabel met waarnemingen, de waarde,
de metrieken) wordt in dezelfde beurt opnieuw uit de database gelezen en is dus
sowieso al bijgewerkt.

### 📖 Handleiding: een volledig hoofdstuk over gekoppelde koersen

Hoofdstuk 3.10 heet nu **"Gekoppelde koersen: effecten zonder eigen notering"** en
behandelt de hele machinerie op één plaats: waarom sommige effecten nergens
noteren, de twee methodes (lineaire afgeleide koers en fondsformule) met een
vergelijkingstabel, de formules zelf, waarom een maandgemiddelde tóch elke dag
beweegt (de clausule over vervroegde uitstap), hoe de gevoeligheid daalt van 16
naar 0 over de looptijd, hoe de waarnemingen bepaald en opgehaald worden, hoe je
de parameters vindt en kalibreert, waar een gekoppelde koers overal in doorwerkt,
de vier principes erachter, en een tabel met symptomen en oplossingen.

De twee overgebleven eigenschappen van werkgeversfondsen (uitkering in
deelbewijzen en geblokkeerde loten) staan nu apart in 3.11. Verwijzingen elders in
het document zijn mee bijgewerkt, en de woordenlijst en de bestandsindeling zijn
aangevuld.

Ook eerlijk vermeld: de gereconstrueerde grafiek op 📈 Evolutie werkt met
historische reeksen die rechtstreeks bij Yahoo opgehaald worden, en een QS-ISIN
heeft daar geen notering. Gekoppelde fondsen ontbreken dus in die ene grafiek —
overal elders tellen ze volledig mee.

De handleiding in de root van de repository stond nog op 1.5.0 en liep dus ver
achter op die van de add-on. Beide zijn nu gelijk.

### 🧹 Opgeruimd

`monthly_reading_dates()` is uit `fcpe_pricing.py` verwijderd. Die functie
werd nergens gebruikt en beweerde in haar toelichting dat de waarnemingen op
"de laatste beursdag van de maand" vallen — dat klopt niet met het reglement
(de 15e) en sprak de rest van de module tegen.

## 1.8.7
### 🏢 Optie: dividenden van een fonds laten meetellen als gewoon aandeel

Standaard telt de Belgische 833-vrijstelling op de roerende voorheffing (en de
FBB voor Franse dividenden) enkel dividenden van activa met Type 'Aandeel' —
fondsen, ETF's en beveks zijn wettelijk uitgesloten. Sommige FCPE-
werkgeversfondsen keren echter in de praktijk een gewoon, aan Belgische
roerende voorheffing onderworpen dividend uit, ook al staat hun Type hier op
ETF/fonds. Die dividenden werden daardoor standaard NIET meegeteld in de
Aangiftehulp, terwijl dat voor dat specifieke fonds wél had gemoeten.

Onder 🏢 Activa → Overzicht staat nu een kolom **"Div=aandeel"**. Vink die aan
voor een activum en de dividenden ervan tellen voortaan mee:
- voor de 833-vrijstelling (terug te vorderen roerende voorheffing), en
- voor de FBB op Franse dividenden (indien ingeschakeld).

Dit overschrijft enkel de Type-gebaseerde uitsluiting voor dat ene activum —
de rest van de fiscale berekening (TOB, meerwaardebelasting, FCPE-koers-
bepaling) verandert niet. Standaard staat het vinkje UIT voor alles behalve
'Aandeel' (dat telt sowieso altijd mee, ongeacht dit vinkje). Twijfel je of
jouw fonds hiervoor in aanmerking komt: laat het uit en vraag het na bij je
boekhouder of de FOD Financiën — onterecht aanvinken levert een te hoge
(foutieve) teruggave op.

## 1.8.6
### 📄 "Overnemen van een eerdere transactie" neemt nu ook echt alles over

De knop vulde tot nu toe enkel activum, type, rekening en (desgewenst) het
aantal in — prijs, kosten, wisselkoers, TOB-instelling, loon/gratis-aandeel
en blokkering bleven leeg, ook al stonden ze net op de gekozen transactie.
Dat was bewuste keuze in de oorspronkelijke opzet, maar in de praktijk
betekende het dat je bij elke maandelijkse aankoop toch weer alles moest
intikken behalve die drie velden.

Overnemen vult nu het volledige formulier in met de gegevens van de gekozen
transactie:
- prijs per stuk en munt
- kosten en kostenmunt
- eigen wisselkoers — enkel als die destijds manueel was ingesteld (anders
  wordt ze toch herberekend op de nieuwe datum, dus overnemen zou misleidend
  zijn)
- TOB manueel aangepast + het bedrag — enkel als dat destijds manueel was
- loon/gratis aandeel-vinkjes, inclusief "écht gratis" indien van
  toepassing (enkel bij aankopen)
- de blokkeringsdatum, indien aanwezig

Datum blijft bewust op vandaag staan en notities worden niet overgenomen —
die horen bij de vorige transactie, niet bij de nieuwe. Er wordt niets
opgeslagen tot je zelf op "Transactie toevoegen" klikt, dus je kan nog
alles aanpassen wat deze keer wél verschilt.

Ingebouwde veiligheid: een munt die niet geldig is voor het gekozen
activum, of een rekening die intussen verdwenen is, wordt gewoon
overgeslagen in plaats van een foutieve of crashende widget te veroorzaken.

## 1.8.5
### 🔁 Herstel van een regressie in 1.8.4

In 1.8.4 was `views/assets.py` per ongeluk opgebouwd vanaf de versie van vóór
1.8.2, waardoor de paneelteksten van 1.8.2 en 1.8.3 terugvielen op hun oude
vorm: de formule stond weer als *inschrijvingsprijs + rendement + α × (…)*
(de opgetelde variant), het majoraties-veld was weer "optioneel" met de oude
voorbeeldwaarde, en de waarschuwingen van de kalibratie (anker op de
oprichtingsdag, onbepaaldheid, negatieve inschrijvingsprijs) werden niet
getoond. **De berekening zelf was nooit geraakt** — `fcpe_pricing.py` bleef
correct, dus waardes en kalibratie klopten al die tijd. Alleen de uitleg op
het scherm liep achter. Alles staat er weer in.

### 🎯 De panelen openen op je eigen koppeling

Beide configuratiepanelen toonden de volledige activalijst zonder
voorkeuze, zodat je bij het openklappen op het alfabetisch eerste activum
belandde (een willekeurig aandeel) in plaats van op je fonds. Alle velden
leken dan leeg, de onderliggende waarde stond verkeerd en er waren "0"
bewaarde waarnemingen — terwijl er in werkelijkheid niets mis was.

Voortaan tonen beide panelen standaard **enkel de activa die al gekoppeld
zijn**, gemarkeerd met 🔗 respectievelijk 📐, en openen ze meteen op de eerste
daarvan met alle parameters, majoraties en waarnemingen voorgevuld. Een
checkbox schakelt de volledige lijst in wanneer je een nieuw fonds wilt
koppelen; de gekoppelde staan dan bovenaan. Is er nog niets gekoppeld, dan
verschijnt gewoon de volledige lijst met een korte uitleg. Een eerder gekozen
ticker die buiten de gefilterde lijst valt, wordt netjes opgeruimd in plaats
van een Streamlit-fout te veroorzaken.

## 1.8.4
Nieuwe sectie **🏢 Activa → 🔗 Koppelingen** met een overzichtstabel van alle
activa die een afgeleide koers (🧮) of een fondsformule (📐) gebruiken: fonds,
methode, onderliggende waarde, de kernparameters in één oogopslag (α,
referentie- en inschrijvingsprijs, aantal vastgelegde waarnemingen,
majoraties), zodat je niet meer per activum het formulier moet openen om te
zien wat er precies staat ingesteld.

De configuratiepanelen zelf (**🧮 Afgeleide koers** en **📐 Fondsformule**,
inclusief de kalibratie tegen de officiële NAV) zijn hierheen verhuisd vanuit
**📋 Overzicht** — inhoudelijk ongewijzigd, alleen makkelijker terug te vinden
naast het nieuwe totaaloverzicht. Geen enkel ander gedrag verandert; er is
geen databankmigratie.

## 1.8.3
De kalibratie kon na 1.8.2 nog een onzinnig resultaat opleveren (een te lage
referentieprijs mét een negatieve inschrijvingsprijs). De oorzaak is wiskundig,
niet numeriek: zolang **geen enkele waarneming onder de referentieprijs ligt**
— en voor Link Multiple BEL 2022 is dat zo, de laagste slotkoers (13,27 op
14-06-2024) blijft boven de referentie — wordt er nergens afgetopt en hangt de
waarde alleen af van de combinatie *(inschrijving − α × referentie)*. Referentie-
en inschrijvingsprijs zijn dan **onscheidbaar**: elke verschuiving van de één
compenseert de ander exact, en een gezamenlijke schatting glijdt naar een
willekeurig punt op die richel.

### ⚓ De oprichtingsdag pint de inschrijvingsprijs vast

De NAV op de Date de Commencement is per reglement (art. 10) exact de
inschrijvingsprijs — een meting, geen schatting. Staat die datum in de
NAV-export (voor BEL 2022: 22-12-2022 = 10,52), dan gebruikt de kalibratie hem
voortaan als anker voor de inschrijvingsprijs en zoekt ze alleen nog de
referentieprijs. Dat breekt de richel. Wijkt het anker af van de handmatig
ingevulde inschrijvingsprijs, dan verschijnt een waarschuwing.

### ⚠️ Onbepaaldheid wordt gemeld in plaats van verzwegen

Wordt de inschrijvingsprijs meegeschat zónder anker en blijkt de afwijking over
een brede strook referentieprijzen vrijwel even klein (de richel), dan zegt het
resultaat dat nu expliciet, mét de remedie. Een gevonden inschrijvingsprijs van
nul of lager krijgt een aparte waarschuwing: gebruik dat resultaat niet. De
kalibratie-uitleg vermeldt bovendien dat de **majoraties éérst** ingevuld en
bewaard moeten worden — kalibreren zonder perst de dividendsprongen in een
scheve referentieprijs.

### 🎯 De parameters voor Link Multiple BEL 2022

Uit de NAV-reeks december 2022 – augustus 2026 volgt met het gecorrigeerde model
exact één consistent stel: **referentieprijs 13,1403 · inschrijvingsprijs 10,52 ·
α 16 · majoraties 1,48 (2025) en 1,35 (2026)**. Controle: 13,1403 × 0,8 = 10,5122,
naar boven afgerond op de cent = 10,52 — precies hoe het inschrijvingsprijsbesluit
werkt. De gemiddelde absolute afwijking over 44 maandpunten zakt daarmee naar
minder dan één cent.

## 1.8.2
De fondsformule week structureel af van de officiële NAV. De vergelijking met de
gepubliceerde reeks van Link Multiple BEL 2022 (december 2022 – augustus 2026) legde
drie oorzaken bloot, waarvan twee in de code zaten.

### ➕→⬆️ Het rendement is een bodem, geen opslag

Het reglement (art. 3.11.1 / 3.12.1) definieert de prestatie als *"la valeur la plus
haute entre le Rendement et la Participation à la Hausse Moyenne Protégée"* — de
**hoogste** van de twee. De app telde ze op:

    fout:   waarde = inschrijving + rendement + participatie + majoraties
    juist:  waarde = inschrijving + max(rendement, participatie) + majoraties

Zodra de koers boven de referentieprijs noteert, wint de participatie en telt het
rendement niet meer mee. Door de optelling groeide de berekende waarde elk jaar
≈ €0,16 verder boven de officiële NAV uit (1,5% op €10,52), tot ≈ €0,60 in 2026 —
precies de langzaam oplopende drift in de vergelijkingstabel. `part_value()` neemt nu
de max, meldt in `performance_source` welke van de twee de bodem vormt, en zet de
gevoeligheid op nul zolang het rendement wint (een kleine koersbeweging verandert de
waarde dan immers niet).

### 🏛️ De oprichtingsdag

Op de Date de Commencement is de valeur liquidative per reglement (art. 10) exact de
inschrijvingsprijs. De app vulde toen al alle zestig waarnemingen met de spotkoers en
kwam €7,88 te hoog uit. Op of vóór de aanvangsdatum is de prestatie nu nul.

### 💶 De majoraties ontbraken in de invoer (geen codefout, wel een valkuil)

De sprongen van −€1,47 (mei 2025) en −€1,34 (mei 2026) in de vergelijkingstabel zijn
het **dividende majoré** van ENGIE: +10% op het dividend voor aandelen die twee volle
kalenderjaren op naam staan. De FCPE-aandelen staan sinds 22-12-2022 op naam, dus de
eerste majoration viel op het dividend van 2025 (FY2024: €1,48 → €0,148 × 10 aandelen
per deelbewijs = **€1,48**) en de tweede op dat van 2026 (FY2025: €1,35 → **€1,35**).
De formule verwerkte majoraties al, maar het veld stond leeg. Het invoerveld legt nu
uit hoe het bedrag per deelbewijs berekend wordt en toont de werkelijke waarden als
voorbeeld; zonder die regels loopt de berekening vanaf mei 2025 blijvend achter.

### 🎯 Kalibratie op het juiste model

`fit_parameters()` schatte de parameters nog op het additieve model en absorbeerde de
twee fouten hierboven dus in een verkeerde referentie- of inschrijvingsprijs. De
schatting loopt nu over het max-model: lineair op de datums waar de participatie wint,
afwijking berekend met het volledige model, en de oprichtingsdag wordt overgeslagen
(daar is de NAV per definitie de inschrijvingsprijs en zegt hij niets over de
referentieprijs). **Wie eerder gekalibreerd heeft, kalibreert best één keer opnieuw**
— of vult gewoon de reglementwaarden in (BEL 2022: α 16, inschrijving 10,52).

### Wat er daarna overblijft

Na deze correcties resteert op de BEL 2022-reeks een vrijwel vlakke afwijking van
≈ +€0,30 à +€0,44 (≈ 0,3% van de huidige NAV). Die zit niet in de formule maar in de
invoer: de exacte referentieprijs heeft meer decimalen dan de afgeronde €13,15
(de VWAP-middeling wordt niet op de cent gepubliceerd; alleen de inschrijvingsprijs
wel), en de bewaarde slotkoersen kunnen een cent verschillen van de officiële
Euronext-slotkoers waarmee Amundi rekent. Eén herkalibratie van de referentieprijs
met het gecorrigeerde model vangt beide op (verwacht ≈ 13,17) en brengt de afwijking
onder ≈ €0,05. Eén datum blijft dan nog een uitschieter van ≈ €0,15: 14-06-2024 —
controleer de bewaarde slotkoers van die dag tegen de officiële Euronext-close.

## 1.8.1
De kalibratie liet α meebewegen. Dat was fout: α staat in het fondsreglement (16 voor
de jaargang 2022, 19 voor 2018) en is geen onbekende. Hem als vrije parameter behandelen
levert altijd een iets kleinere afwijking op — een extra vrijheidsgraad past nu eenmaal
beter — maar het resultaat is dan geen schatting van de werkelijkheid meer, alleen nog
een kromme die door de punten loopt. Erger: een verkeerde α verbergt een fout elders,
bijvoorbeeld in de aanvangsdatum of in ontbrekende waarnemingen, door hem in de hefboom
te absorberen.

α wordt nu **vast gehouden** op de waarde die je hierboven invulde; enkel de
referentieprijs wordt gezocht. Twee vinkjes laten dat desgewenst los:

- *Ook de inschrijvingsprijs afleiden*, als je die evenmin kent.
- *α toch meekalibreren*, alleen voor wie het reglement van zijn jaargang echt niet
  heeft. Wijkt de gevonden α dan ver af van een rond getal, dan klopt er elders iets niet.

Het resultaat vermeldt voortaan expliciet welke parameters vrijgelaten en welke vast
gehouden zijn, en waarschuwt wanneer de afwijking groter is dan één euro — dan is de
referentieprijs zelden de enige oorzaak.

Verder rekent de kalibratie nu ook met de majoraties, de vervaldag en het rendement op
vervaldag, en verfijnt ze het raster tweemaal rond het beste punt in plaats van op de
grofste stap te blijven staan.

## 1.8.0
Een tweede waarderingsmethode voor werkgeversfondsen: de formule uit het fondsreglement
zelf, naast de bestaande lineaire methode. Per activum te kiezen.

### 📐 De fondsformule ("Participation à la Hausse Moyenne Protégée")

De bestaande methode rekent op de spotkoers: `basis + multiplicator × (koers −
referentie)`. Voor Link Classic en Liberty klopt dat exact — één deelbewijs is één
aandeel. Voor de **Multiple**-fondsen niet: die hangen aan het **gemiddelde van zestig
maandelijkse waarnemingen**, elk afzonderlijk afgetopt op de referentieprijs.

    waarde = inschrijvingsprijs + rendement + α × (gemiddelde − referentieprijs) + majoraties
    Relevé i = max(slotkoers op waarnemingsdatum i, referentieprijs)

Twee gedragingen die een lineair model per definitie niet kan nabootsen:

- **De gevoeligheid daalt.** Elke waarneming weegt 1/60; openstaande waarnemingen worden
  met de huidige koers ingevuld. Een beweging van €1 verschuift de waarde dus met
  α × (openstaand/60) × €1 — bij α=16 is dat €16 aan het begin en nog €4 wanneer er
  vijftien openstaan. Een vaste multiplicator is even gevoelig op de eerste als op de
  laatste dag.
- **Verworven stijging kan niet meer verdwijnen.** Omdat elke waarneming apart wordt
  afgetopt, kan een koersval onder de referentieprijs het gemiddelde niet omlaag halen.
  De lineaire methode met ondergrens laat die winst wél volledig wegvallen.

Nieuw bestand `fcpe_pricing.py` met de volledige formule: aftopping per waarneming,
invulling van openstaande waarnemingen, het rendement met dagtelling
`[(1+1,5%)^(Nbj/365) − 1]`, het afwijkende tarief van 7,73% op de eindvervaldag, en de
Majorations de Dividende.

### 🗓️ De waarnemingsdata worden zelf bepaald

Het reglement zegt: de 15e van elke maand, of de beursdag ervóór. Welke dagen dat zijn,
is niet vrijblijvend — de gepubliceerde reeks schuift op 14 juli en 15 augustus een dag
terug, dus de Franse feestdagen tellen mee, niet enkel de sluitingsdagen van Euronext.
De ingebouwde kalender is nagerekend tegen de **44 gepubliceerde waarnemingsdata van
januari 2023 tot augustus 2026: alle 44 komen exact uit**, inclusief de verschuivingen
naar 13 juli 2023, 14 augustus 2023 en 14 augustus 2025. De laatste gegenereerde datum
is 15 december 2027, zoals het reglement voorschrijft.

### 🔄 De historische waarnemingen worden automatisch opgehaald

Er hoeft niets ingetypt te worden. De knop *Waarnemingen ophalen* (en voortaan ook een
dagelijkse achtergrondtaak om 23:10) haalt de werkelijke slotkoers van de onderliggende
waarde op voor elke voorbije waarnemingsdatum, terug tot de start van het fonds — ook
voor jaren waarin de app zelf nog geen koersen bewaarde. Bewust met de ONGECORRIGEERDE
slotkoers: het reglement spreekt over de werkelijke slotkoers, niet over een voor
dividenden gecorrigeerde reeks.

Reeds vastgelegde waarnemingen worden nooit overschreven. Een waarneming hoort niet meer
te bewegen, en een handmatige correctie mag niet stilzwijgend ongedaan gemaakt worden.
De slotkoersen worden ruw bewaard — het aftoppen gebeurt pas bij het rekenen — zodat je
ze regel per regel tegen een beursoverzicht kunt houden.

### 🎯 Kalibratie tegen de gepubliceerde NAV

Ken je de referentie- of inschrijvingsprijs van je jaargang niet, laad dan de NAV-export
van de beheerder op. De app leidt de best passende parameters af en toont de afwijking,
plus een vergelijking berekend-tegenover-officieel per datum. Dat laatste is de enige
eerlijke controle: wijkt het stelselmatig af, dan is de gepubliceerde NAV de waarheid en
niet de berekening.

### Overige

- `assets.pricing_mode` kent nu drie waarden: `auto`, `derived` en `fcpe`; ze sluiten
  elkaar uit. Nieuw: `db.set_pricing_mode()`.
- Nieuwe tabellen `fcpe_readings` en `official_nav`, nieuwe kolom `assets.fcpe_params`.
- De statuscontrole slaat fondsformule-activa over, net als afgeleide: hun ISIN staat bij
  geen enkele koersbron, dus elke online poging zou logruis zijn.
- Het fotomoment (31/12/2025) van zo'n fonds wordt via de formule bepaald, met alleen de
  waarnemingen die op dat moment bestonden — geen kennis van later.

## 1.7.0
Een blinde vlek in de risicoweergave, en drie plekken waar de app onnodig werk van je
vroeg.

### 🎯 Blootstelling per onderliggende waarde

De sectorgrafiek toont hoe je gespreid bent over sectoren, maar niet dat drie regels in
je portefeuille economisch aan dezelfde koers kunnen hangen. Wie via een werkgeversplan
zowel het aandeel als een hefboomfonds op dat aandeel aanhoudt, ziet dat nu bij elkaar
geteld: activa met een afgeleide koers worden toegerekend aan hun onderliggende waarde,
en die keten wordt gevolgd.

Nieuwe sectie op de portefeuillepagina, met een tabel per onderliggende waarde en een
melding wanneer er meer dan 20% aan één waarde hangt (instelbaar via
`concentration_threshold_pct`).

Daarnaast kan je activa aanduiden als **werkgeversgebonden**: aandelenplannen,
FCPE-fondsen, bonusaandelen. De app kan dat niet zelf weten, dus jij duidt het aan. Staat
er iets aangeduid, dan meldt de app welk percentage van je vermogen aan dezelfde partij
hangt als je inkomen — met de kanttekening die daarbij hoort: valt die koers, dan is dat
vaak net het moment waarop ook je inkomen onder druk staat, en zit een deel er mogelijk
nog geblokkeerd. Een vaststelling, geen advies.

Wat dit **niet** doet: doorkijken naar de inhoud van fondsen. Een wereldindextracker met
4% Apple erin telt hier niet als Apple-blootstelling. Alleen expliciete koerskoppelingen
worden gevolgd, want alleen die kent de app met zekerheid.

Nieuw in `belgian_tax.py`: `underlying_exposure()`.

### ↩️ Verwijderen kan ongedaan gemaakt worden

Een bevestigingsvraag beschermt tegen de verkeerde klik, maar niet tegen de verkeerde
beslissing: dat je het verkeerde item koos, zie je meestal pas nadat het weg is.

Elke verwijdering legt nu eerst een volledige kopie van de rij in een prullenbak.
Onmiddellijk na het verwijderen verschijnt een knop **↩️ Ongedaan maken** die de hele
actie terugdraait; daarnaast staat er een blijvende prullenbak onder
**⚙️ Instellingen → 🗃️ Data** waar je per item kunt terugzetten of definitief wissen.

Terugzetten herstelt de rij mét haar oorspronkelijke nummer wanneer dat nog vrij is —
zo klopt een koppeling als die tussen een stockdividend en zijn aanwastransactie weer.
Is het nummer intussen bezet, dan komt de rij terug met een nieuw nummer: liever terug
met een ander nummer dan helemaal niet terug. Het bewaren en het verwijderen gebeuren in
dezelfde databasetransactie, zodat er nooit iets verdwijnt zonder kopie.

Werkt voor transacties, dividenden (inclusief de gekoppelde aanwastransactie) en
rekeningkosten. Nieuw in `database.py`: `list_trash()`, `restore_trash()`,
`purge_trash()`, `last_trash_group()`, `trash_count()`.

### 📄 Transactie overnemen

Een maandelijkse aankoop verschilt meestal alleen in datum en koers van de vorige. In het
formulier *Nieuwe transactie* kies je nu een eerdere transactie en neem je activum, type,
rekening en desgewenst het aantal over. Prijs, kosten en TOB blijven leeg, want die
verschillen per keer, en er wordt niets opgeslagen tot je zelf op toevoegen klikt.

Waarden die geen geldige keuze meer zijn (een verwijderde rekening bijvoorbeeld) worden
overgeslagen in plaats van stilzwijgend door de eerste optie vervangen.

### 👋 Sinds je vorige bezoek

Kom je terug na een dag of langer, dan staat er bovenaan het dashboard in één zin wat er
veranderd is: hoeveel je portefeuille voor- of achteruitging, of er nieuwe meldingen op
de statuspagina bijkwamen, en hoeveel AI-adviezen wijzigden. Binnen dezelfde zitting
blijft die zin staan zoals hij was — een teller die zichzelf bij elke klik bijwerkt, zou
altijd nul tonen.

## 1.6.0
Twee nieuwe werkinstrumenten, en een fiscale rekenfout die daarbij aan het licht kwam.

### 🔴 Meerwaardebelasting werd gerekend voor jaren waarin het regime nog niet bestond

Bij het bouwen van de aangiftehulp bleek de app voor **2025** een meerwaarde van €200
als volledig belastbaar te behandelen: €20 verschuldigd, terwijl er dat jaar voor normaal
beheer helemaal geen meerwaardebelasting bestond.

De oorzaak: `available_exemption()` geeft voor een jaar vóór 2026 terecht een
vrijstelling van 0 terug — er valt immers niets vrij te stellen — maar de berekening las
die 0 als "alles is belastbaar". Nu wordt eerst gekeken óf het regime van toepassing was;
zo niet, dan is het belastbare bedrag nul, hoe groot de meerwaarde ook was. Het overzicht
geeft dat mee als `regime_applicable`, en de aangiftehulp legt het met zoveel woorden uit
in plaats van een leeg bedrag te tonen.

Wie in de app een boekjaar vóór 2026 bekeek en daar een bedrag zag staan: dat cijfer was
fout en is nu nul.

### 📋 Aangiftehulp (nieuwe pagina)

Eén scherm dat per vak toont wat je moet invullen, met de onderbouwing eronder:

- **Dividenden zonder Belgische voorheffing** — wat je zelf moet aangeven omdat er geen
  Belgische tussenpersoon inhield, berekend als brutobedrag ná buitenlandse bronbelasting.
- **Terug te vorderen voorheffing** binnen de vrijstelling voor gewone aandelen, met de
  opbouw erbij: wat komt in aanmerking, wat valt binnen de schijf, wat is er ingehouden,
  en wat telt niet mee omdat het fondsen of ETF's zijn.
- **FBB** voor Franse dividenden, wanneer die instelling aan staat.
- **Meerwaardebelasting**, met de volledige opbouw van gerealiseerd naar verschuldigd.

Elke regel is uitklapbaar tot op de onderliggende dividendlijnen, zodat je elk bedrag kunt
narekenen tegen je rekeninguittreksels. Bovenaan staat wat je totaal moet aangeven
tegenover wat je kunt terugvorderen — dat laatste is geld dat je laat liggen als je het
niet invult.

Twee dingen bewust níét gedaan. De **vakcodes staan als instelling in de database**, niet
vast in de code: ze wijzigen van jaar tot jaar, en de app kan het formulier van dit jaar
niet kennen. Codes waarvan de app niet zeker is, zijn als zodanig gemarkeerd. En er is
een expliciete lijst van **wat de app niet voor je kan invullen**: buitenlandse rekeningen
(vak XIII), de taks op effectenrekeningen, en alles buiten deze portefeuille.

### 🔓 Deblokkeringskalender (op de portefeuillepagina)

Onder de open posities staat nu een tijdlijn: wanneer komt hoeveel geblokkeerd kapitaal
vrij, en wat is het vandaag waard. Met een grafiek per datum plus de cumulatieve lijn, een
tabel met het aantal dagen tot elke datum, en een uitklapbaar detail per lot. Voor wie
meerdere jaargangen uit een werkgeversplan aanhoudt, is dat de vraag die er echt toe doet.

De waarde is de huidige marktwaarde van die stukken, uitdrukkelijk geen prognose. Is er
voor een activum geen koers, dan valt de kalender terug op de kostbasis en zegt ze dat
erbij — een verzonnen marktwaarde zou hier erger zijn dan een eerlijk cijfer met een
kanttekening.

Nieuw in `belgian_tax.py`: `unlock_schedule()` en `declaration_lines()`.

## 1.5.0
Opschoning onder de motorkap. Aan wat je op het scherm ziet, verandert niets — dit gaat
over hoe de code in elkaar zit, zodat elke volgende wijziging goedkoper en veiliger
wordt.

### `app.py` opgesplitst: van 6.414 naar 141 regels

De volledige interface zat in één bestand, met pagina's van 700 tot 900 regels. Elke
pagina heeft nu een eigen module in `views/`:

```
app.py                 opzet, zijbalk, doorgeven aan de gekozen pagina   (141)
views/common.py        gedeeld fundament: opmaak, gecachet overzicht,   (1018)
                       blijvende filters, herberekeningen, widgets
views/assets.py        (950)   views/settings.py     (870)
views/dividends.py     (762)   views/transactions.py (731)
views/portfolio.py     (475)   views/dashboard.py    (437)
views/ai.py            (370)   views/evolution.py    (272)
views/status.py        (236)   views/tax.py          (217)
views/simulation.py    (165)   views/docs.py         (148)
views/cash.py          (135)
```

Twee bewuste keuzes daarbij:

- **De map heet `views`, niet `pages`.** Streamlit bouwt uit een map met de naam
  `pages` automatisch een eigen navigatiemenu, wat zou botsen met de zijbalk die de app
  zelf opbouwt. Het lag voor de hand om `pages` te kiezen — en het zou stilletjes een
  tweede menu hebben opgeleverd.
- **De afhankelijkheid loopt één kant op.** Pagina's gebruiken `views/common.py`, maar
  `common` kent geen enkele pagina en pagina's kennen elkaar niet. Dat is nagemeten,
  niet aangenomen: geen enkele pagina gebruikte een functie van een andere pagina, wat
  de opsplitsing mechanisch en risicoloos maakte.

De code zelf is niet herschreven: functies zijn als exacte tekstblokken verplaatst.
Gecontroleerd is dat alle 61 functies precies één keer voorkomen, dat elke module elke
naam die ze gebruikt ook echt kent, en dat de app en alle dertien pagina's foutloos
renderen.

### Vier bijna-identieke dividendberekeningen samengevoegd

Het netto- en cashbedrag van een dividend werd op vier plaatsen berekend
(`dividend_net_eur` en een lokale `_neur` in `app.py`, `_div_net_eur` en `_div_cash_eur`
in `database.py`). Ze waren al uit elkaar gegroeid: één ving geen `None`-waarden op en
één kende de 'geen cash'-regel voor stockdividenden niet. Zulke kopieën leveren vroeg of
laat een ander cijfer op de ene pagina dan op de andere.

Er is nu één bron in `database.py`: `dividend_gross_eur()`, `dividend_net_eur()`,
`dividend_cash_eur()` en `dividends_net_eur()`, elk in de veiligste variant van de vier.
De oude interne namen blijven als verwijzing bestaan, dus bestaande aanroepen werken
gewoon door.

### Blokkering verhuisd naar het gecachete overzicht

`locked_summary()` deed een volledige extra FIFO-pass over alle transacties, ongecacht,
bij élke render van zowel het dashboard als de portefeuille — precies het werk dat de
cache van `get_overview()` moest vermijden. Het resultaat zit nu in dat gecachete
overzicht (`overview["locked"]`), met dezelfde rekeningfilter als de rest. De
waarschuwing in het verkoopformulier rekent nog wel apart: die kijkt naar een specifieke
datum en kan dus niet uit de cache komen.

## 1.4.2
Draait een overbodige wijziging uit 1.3.1 terug die de add-on sinds 1.4.0 onbouwbaar
maakte.

De Dockerfile bevatte deze regel:

```dockerfile
RUN mkdir -p /app/.streamlit && cp /app/config.toml /app/.streamlit/config.toml
```

Die faalde met `cp: cannot stat '/app/config.toml'`, en daarmee de volledige build.
De aanname erachter was fout. `config.toml` staat in deze repo op
`portfolio_tracker/.streamlit/config.toml` — dus al precies waar Streamlit kijkt.
`COPY . .` zet het bestand meteen goed op `/app/.streamlit/config.toml`, er valt niets
te verplaatsen, en de kopieerregel zocht naar een bestand dat er terecht niet was.

De regel is vervangen door een controle die het pad in het bouwlogboek afdrukt en
nooit kan mislukken. De gelijkaardige toevoeging in `start.bat` is volledig
teruggedraaid: op Windows draait Streamlit al vanuit de app-map, dus ook daar wordt
`.streamlit\config.toml` gewoon gevonden.

**Twee eerdere mededelingen die hiermee vervallen:**

- De waarschuwing bij 1.3.1 dat het uiterlijk kon veranderen. `config.toml` werd altijd
  al gelezen; het donkere thema was nooit weg.
- De bewering dat het bestand genegeerd werd. Dat was verkeerd, en het is precies
  daarom een goede zaak dat de XSRF-instelling van 1.3.1 óók in `config.toml` staat:
  die werd dus wel degelijk toegepast.

Geen enkele wijziging aan de toepassing zelf; 1.4.0 kwam simpelweg nooit voorbij stap 9
van de build.

## 1.4.0
De app maakt vanaf nu zelf back-ups, en de OpenAI-sleutel kan buiten de database
gehouden worden.

### 💾 Back-up en herstel

Tot nu toe bestond er geen enkele back-upvoorziening: één corrupte SQLite of een
verkeerde handeling en jaren fiscale historiek was weg. Nieuw blok onder
**⚙️ Instellingen → 🗃️ Data**:

- **Automatisch**, op twee momenten: elke nacht om 02:30, en telkens wanneer de app
  start. Dat tweede moment is het belangrijkste — het gebeurt vlak vóór een nieuwe
  versie de database bijwerkt, precies wanneer je terug zou willen kunnen. Beide zijn
  uit te schakelen; het aantal te bewaren kopieën is instelbaar (standaard veertien,
  de oudste worden opgeruimd).
- **Handmatig**, met de knop *Nu back-uppen*.
- **Downloaden** van elke kopie naar je eigen toestel. Een back-up die naast het
  origineel staat, helpt niet bij een defecte schijf.
- **Herstellen** vanaf een bewaarde kopie of een geüpload bestand, met een
  validatiestap (is dit wel een portfolio-database?), een vergelijking van de inhoud
  met je huidige database, een expliciete bevestiging, en een automatische
  veiligheidskopie vooraf — zodat ook een verkeerd herstel terug te draaien is.

Technisch gebruikt de back-up `VACUUM INTO` in plaats van een bestandskopie. Bij een
draaiende WAL-database is een gewone kopie onbetrouwbaar: de recentste wijzigingen
staan in een apart `-wal`-bestand en je kunt halverwege een transactie vallen.
`VACUUM INTO` laat SQLite zelf een consistente, compacte kopie wegschrijven terwijl
alles doordraait, en levert één bestand op dat je meteen kunt openen.

Nieuw in `database.py`: `create_backup()`, `list_backups()`, `delete_backup()`,
`prune_backups()`, `validate_database_file()`, `restore_backup()`, `database_size()`.
Nieuwe scheduler-job `daily_backup`. Mislukt de automatische back-up, dan verschijnt
dat als waarschuwing op de statuspagina — een stille faalmodus is hier het gevaarlijkst.

Het verwijderen van een back-up accepteert alleen bestandsnamen uit de back-upmap met
het verwachte voor- en achtervoegsel, dus een pad als `../portfolio.db` doet niets.

### 🔐 De API-sleutel hoeft niet meer in de database

De add-on heeft nu een configuratieoptie `openai_api_key` van het type `password`:
Home Assistant toont ze gemaskeerd en bewaart ze in de privéopslag van de add-on, niet
in `/share`. `run.sh` zet ze om in de omgevingsvariabele `OPENAI_API_KEY`, die in de
app voorrang krijgt op de opgeslagen waarde. Op Windows doe je hetzelfde met een regel
in `config.bat`.

Waarom dit uitmaakt: `portfolio.db` staat in `/share`, en die map is gedeeld met andere
add-ons. Een API-sleutel is geld. Het stappenplan staat in hoofdstuk 11.2 van de
handleiding — inclusief de volgorde die ertoe doet: eerst instellen en controleren dat
de AI antwoordt, en **pas daarna** de oude sleutel uit de app wissen.

### Overige

- De datapagina toont nu ook de grootte van de database.
- Back-upnamen krijgen een volgnummer als er al één met dezelfde tijdstempel bestaat
  (`VACUUM INTO` overschrijft nooit een bestaand bestand — terecht).

## 1.3.1
Een beveiligingsronde plus vier correcties die uit een volledige doorlichting van de
codebase kwamen. **Lees het eerste punt: het raakt iedereen die de add-on draait.**

### 🔴 De app hing onbeveiligd aan je thuisnetwerk

`config.yaml` publiceerde poort 8501 rechtstreeks op de host:

```yaml
ports:
  8501/tcp: 8501
```

Daardoor was de app bereikbaar op `http://<ip-van-je-server>:8501`, **buiten de
aanmelding van Home Assistant om**. De app zelf heeft geen login, dus iedereen op
hetzelfde netwerk — een gast op de wifi, een slecht beveiligd IoT-apparaat — kon de
volledige portefeuille lezen én bewerken. Het `ports`-blok is verwijderd; de app loopt
nu uitsluitend via ingress, dat wél achter de authenticatie van Home Assistant zit.
Wie bewust rechtstreekse toegang wil, voegt de poort zelf toe in de
add-on-configuratie.

Daarbij hoorde ook `--server.enableXsrfProtection=false`. Zonder die bescherming kan
een kwaadaardige pagina in je browser meeliften op je geopende sessie. Ze staat nu
aan, in `run.sh` én `config.toml`. Loopt de bulk-import daardoor vast op een
403-fout, dan kan je ze tijdelijk terugzetten met de omgevingsvariabele
`XSRF_PROTECTION=false` — liefst niet permanent.

### 🔴 De OpenAI-sleutel was uitleesbaar in de browser

Het invoerveld kreeg de opgeslagen sleutel als beginwaarde mee. `type="password"`
maskeert enkel visueel: de echte waarde reisde mee naar de browser en stond daar
gewoon in de paginastatus, klaar om gekopieerd te worden. Het veld start nu leeg
(leeg laten = sleutel ongewijzigd); je ziet alleen nog een herkenningsvorm
(`sk-pro••••••••••••abcd`), met een aparte knop om de sleutel te wissen.

Nieuw is ook `OPENAI_API_KEY` als omgevingsvariabele. Die krijgt voorrang op de
instelling in de app, waardoor de sleutel helemaal buiten `portfolio.db` kan blijven —
dat bestand staat in `/share` en is voor andere add-ons leesbaar. De instellingenpagina
zegt het wanneer de variabele actief is.

### Verkeerde beurskalender voor effecten zonder beurssuffix

`market_of()` gaf **US** terug voor elke ticker zonder punt en zonder ingevulde beurs,
óók bij een EUR-notering. Alles wat je zelf een naam gaf — werkgeversfondsen, warrants,
niet-genoteerde stukken — werd dus tegen de kalender van de NYSE gehouden. Gevolg:
een vals *geen koersbeweging*-alarm op 1 mei en Paasmaandag, en een echt stilstaande
koers die op Thanksgiving ten onrechte werd weggemasseerd. Een Europese munt (EUR,
GBP, CHF, SEK, NOK, DKK, PLN, CZK) telt nu als bewijs voor de Europese kalender; een
kale ticker zonder munt en zonder beurs blijft US, want dat is dan de waarschijnlijkste
lezing.

### Statuscontrole bevroeg activa die per definitie nergens noteren

De dagelijkse controle van 22:45 deed een volledige online probe voor élke open
positie, ook voor activa met een **afgeleide koers** of op **enkel handmatig**. Voor
zulke ISIN's is elke bron bij voorbaat blind: dat leverde alleen netwerkcalls en
logruis op, met het risico op een valse *tickerwijziging* uit een toevallige
naamgelijkenis. Die activa worden nu overgeslagen (het onderliggende activum wordt wél
gewoon gecontroleerd), en eerder geopende netwerkmeldingen worden netjes gesloten.

### Stockdividend en aanwastransactie horen nu echt bij elkaar

De aanwastransactie van een stockdividend werd los geboekt: verwijderde je het
dividend, dan bleven de stukken in je positie staan zonder aanleiding, en faalde de
tweede helft van de boeking, dan bleef de eerste als wees achter. Nieuwe kolom
`linked_txn_id` op `dividends` en een nieuwe functie `add_stock_dividend()` die beide
helften als één geheel boekt, met terugdraaien bij een fout. Verwijder je het dividend,
dan verdwijnt de gekoppelde transactie mee — de verwijderlijst zegt dat er ook op.

### Overige

- `config.toml` werd stilzwijgend genegeerd: Streamlit leest die alleen uit
  `.streamlit/config.toml`, en het bestand stond in de repowortel. De Dockerfile en
  `start.bat` zetten het nu op de juiste plek, waardoor het donkere thema en de
  uploadlimiet effectief worden. **Let op:** het uiterlijk kan hierdoor voor het eerst
  wijzigen (donker thema) — dat is de instelling die al die tijd bedoeld was.
- `add_transaction()` en `add_dividend()` geven voortaan het nieuwe ID terug.

## 1.3.0
Werkgeversfondsen (FCPE, zoals de Amundi/ENGIE Link-fondsen) worden nu volwaardig
ondersteund via drie nieuwe bouwstenen: afgeleide koersen, stockdividenden en
blokkeringsperiodes.

### Afgeleide koers: waarde volgt een onderliggend activum

FCPE-fondsen (QS-ISIN's) noteren nergens publiek — geen enkele koersbron kent ze, en
Amundi publiceert de VL enkel achter een JavaScript-gedreven pagina. Scrapen zou
fragiel zijn én overbodig: voor 1:1-fondsen zoals Link Classic/Liberty is de koers
per definitie die van het ENGIE-aandeel, dat de app al perfect ophaalt.

Een activum kan daarom gekoppeld worden aan een **onderliggende waarde** (nieuwe
uitklapper **🧮 Afgeleide koers** op de Activa-pagina, sectie Overzicht):

    koers = basis + multiplicator × (koers onderliggend − referentiekoers)

optioneel met een **ondergrens** op de basis (kapitaalgarantie van hefboomfondsen
zoals Link Multiple). 1:1-fonds: basis 0, multiplicator 1, referentie 0.

- `get_current_price`, `get_close_on_date` (fotomoment 31/12/2025!) en
  `get_market_state` volgen automatisch de onderliggende waarde. De koershistoriek
  (dagresultaat) loopt gewoon mee via de scheduler.
- De hele bronnenketen wordt voor zo'n activum overgeslagen: geen nutteloze
  netwerkcalls, geen logruis, en de **faalteller loopt nooit op** — een falende
  onderliggende koers blijft een fout van het onderliggende activum, met zijn eigen
  teller en log.
- Ketens van afgeleide activa mogen, maar stoppen na 3 stappen — dat vangt ook
  circulaire verwijzingen af (getest).
- Laatste redmiddel blijft de handmatige koers; er is géén stille terugval.
- Nieuw in `database.py`: `set_derived_pricing()`, `clear_derived_pricing()`,
  `get_derived_pricing()`; nieuw in `market_data.py`: `derived_value()`.

### Stockdividend: kapitalisatie uitgekeerd in aandelen

Nieuwe optie **📦 Uitgekeerd in aandelen** in het dividendformulier (beide
invoerwijzen): aantal toegekende stukken × waarde per stuk voedt de volledige
fiscale keten (bronbelasting, RV, €833-vrijstelling) zoals elk dividend, maar:

- **Cash-boeking = geen** (nieuw cash_basis-type `none`): er beweegt niets in het
  cash-grootboek, ook niet na een herberekening. Beide herberekenpaden zijn expliciet
  beveiligd tegen de valkuil dat 0,0 'falsy' is en stilzwijgend door het netto
  vervangen zou worden.
- Tegelijk wordt automatisch een **gekoppelde aanwastransactie** geboekt
  (`is_stock_dividend=1`): brutowaarde als kostbasis, geen cash-effect, geen TOB,
  optioneel meteen geblokkeerd (zie hieronder). In het cash-grootboek verschijnt ze
  als 'Stockdividend' à €0, analoog aan toekenningen.
- De vlag staat bewust los van `is_performance_share`, zodat de
  vesting-zienswijzen (personenbelasting als kost/investering) er niet door
  vervuild raken.
- Zonder wisselkoers wordt de boeking geweigerd — nooit stilzwijgend koers 1,0.
- In de dividendtabel toont de Cash-kolom '📦 In aandelen (geen cash)'.

### Blokkering: vrij vs. niet vrij verhandelbaar kapitaal

Aankooploten kunnen een **'vrij vanaf'-datum** krijgen (op de datum zelf al vrij):

- In het transactieformulier (vinkje '🔒 (Nog) niet vrij verhandelbaar'), in de
  inline-transactietabel (nieuwe kolom **Vrij vanaf**, JJJJ-MM-DD of leeg) en in de
  bulk-import (nieuwe optionele kolom `vrij_vanaf`).
- De blokkering reist mee met de FIFO-loten (`lock_until` in `_fifo_core`); nieuw in
  `belgian_tax.py`: `locked_summary()` — het geblokkeerde restant per positie, met de
  eerstvolgende deblokkeringsdatum.
- De **portefeuillepagina** toont per positie de kolommen Vrij / 🔒 Geblokkeerd /
  🔓 Vrij vanaf (enkel als er effectief iets geblokkeerd is) plus het geblokkeerde
  en vrij beschikbare kapitaal onder de totalen. Het **dashboard** toont het
  geblokkeerde totaal naast de beschikbare cash.
- Het **verkoopformulier waarschuwt** (maar blokkeert niet — detectie zonder
  automatische toepassing) wanneer een verkoop aan geblokkeerde stukken zou raken:
  in de praktijk wijst dat op een vergeten of verouderde 'vrij vanaf'-datum.
- FIFO zelf blijft ongewijzigd: bij werkgeversplannen komen de oudste toekenningen
  het eerst vrij, dus FIFO-volgorde en deblokkeringsvolgorde lopen gelijk.

### Migraties (automatisch, idempotent)

`assets`: `pricing_mode`, `underlying_ticker`, `derived_multiplier`, `derived_base`,
`derived_ref_price`, `derived_floor`. `transactions`: `lock_until`,
`is_stock_dividend`. `dividends`: `paid_in_shares`, `shares_received`.

Alles functioneel getest tegen een echte SQLite-database (afgeleide koersen incl.
hefboom/ondergrens/circulaire keten, blokkering incl. FIFO-verkoop en deblokkering,
stockdividend incl. cash-invariantie) en de gewijzigde pagina's gerenderd via
Streamlit AppTest, inclusief de nieuwe vinkjes aangevinkt.

## 1.2.0
Drie punten: het beheer van de sectoren verhuist naar een volwaardige plek, dividenden
krijgen dezelfde bescherming van je eigen wisselkoers als transacties, en de
handleiding is voortaan bereikbaar vanuit de app zelf.

### Sectoren beheer je nu in de instellingen

Het sectorblok stond weggestopt in een uitklapper op de Activa-pagina. Het staat nu
onder **⚙️ Instellingen → 🏭 Sectoren**, met twee mogelijkheden die er nog niet waren.

**Rubriek hernoemen.** Zet de naam in één keer om in de keuzelijst én op elk activum
dat ze gebruikt. Zonder die knop was hernoemen een reeks losse handelingen — nieuwe
rubriek maken, activa één voor één omzetten, oude weggooien — waarbij één vergeten
activum al volstaat om je taartdiagram twee bijna-identieke punten te geven. Nieuw in
`database.py`: `rename_sector()`.

**Toewijzen in bulk.** Een tabel met al je activa en een vinkje *toon enkel activa
zonder sector*, zodat je de gaten in één beweging vult in plaats van activum per
activum. De kolom *Bron* laat zien wat online opgehaald is en wat je zelf hebt gezet.

Verder: kerncijfers bovenaan (rubrieken, toegewezen, nog open), de lijst met per
rubriek hoeveel activa ze gebruiken, verwijderen van ongebruikte rubrieken, en het
online ophalen. Op de Activa-pagina blijft de kolom *Sector* staan voor losse
correcties, met een knop die rechtstreeks naar de nieuwe sectie springt.

### Eigen wisselkoers bij dividenden

Keert een aandeel uit in een vreemde munt, dan rekent je broker om tegen zijn eigen
koers, vaak met een wisselmarge erin verwerkt. Tot nu kon je die enkel bij transacties
vastleggen; bij dividenden gebruikte de app altijd de historische marktkoers, en dan
klopte het euro-bedrag niet met je afschrift.

Nieuw in de database: `dividends.fx_manual`. Nieuw in de app: het blok
**💱 Eigen wisselkoers gebruiken** in beide invoerwijzen, met de afwijking ten opzichte
van de marktkoers erbij, en de kolommen *FX-koers* en *FX eigen* in het overzicht — de
koers aanpassen zet het vinkje automatisch, net als bij transacties.

**De herberekening past dezelfde les toe als bij de TOB in 1.1.0.** Lijnen met een
eigen koers worden niet overgeslagen: jouw koers blijft staan, maar de bedragen en hun
EUR-tegenwaarde worden wél opnieuw berekend. Beschermd tegen overschrijven is niet
hetzelfde als uitgesloten van controle. Ze zijn met 💱 gemarkeerd, wat iets anders
betekent dan de bestaande 🔒: die staat voor "de bedragen zijn van mij, blijf van deze
lijn", 💱 enkel voor "de koers is van mij". Twee beloftes, twee symbolen.

`backfill_eur()` respecteert de eigen koers ook bij een geforceerde omrekening.

### De handleiding zit nu in de app

**Het probleem.** In Home Assistant deed een klik op `HANDLEIDING.md` niets. HA rendert
markdown in zijn eigen frontend, waar een relatief pad naar een ander bestand in de
repository nergens naartoe wijst.

**Nieuwe pagina 📖 Handleiding.** De volledige handleiding, de changelog, de
Windows-installatie en de README, elk met een zoekveld over de hele tekst en een
keuzelijst per hoofdstuk. Onderaan een downloadknop. De bestanden worden van de schijf
naast de code gelezen — de Dockerfile kopieert ze al mee, dus er was niets extra voor
nodig.

Absolute links naar GitHub zouden het klikprobleem oplossen maar niet het echte
probleem: een handleiding op GitHub beschrijft de nieuwste versie terwijl jij misschien
nog een oudere draait, en ze werkt niet zonder internet. De documentatie in de app
hoort per definitie bij de versie die je gebruikt.

**Nieuw bestand `DOCS.md`** voor het Documentatie-tabblad van de add-on: een korte
kennismaking, de installatie, de eerste stappen en de belangrijkste waarschuwingen —
zonder links die in HA toch niet werken.

**Beide README-bestanden gebruiken nu absolute GitHub-URL's.** Daarbij kwam een tweede
fout aan het licht: de README in de repository-root linkte naar `HANDLEIDING.md` en
`CHANGELOG.md`, maar die staan in `portfolio_tracker/`. Die links waren dus niet enkel
in Home Assistant stuk, maar ook op GitHub zelf — ze gaven een 404.

De root-README was bovendien een kopie van de add-on-README. Dat is nu een echte
repository-readme geworden: hoe je de repository aan Home Assistant toevoegt, wat de
add-on doet, en hoe de mappen ingedeeld zijn. De add-on-README blijft de kennismaking
met de app zelf.

De links gebruiken `/blob/HEAD/` in plaats van `/blob/main/`. HEAD wijst altijd naar
de standaardbranch, dus ze blijven werken als die ooit hernoemd wordt — en de
repository heeft momenteel zowel `main` als `master` met identieke inhoud.

`config.yaml` kreeg een `url:`, die HA als klikbare link op de add-on-pagina toont.

## 1.1.0
Vijf verbeteringen die elk een plek raken waar de app iets toonde dat niet
overeenkwam met de werkelijkheid, plus een nieuwe spreidingsanalyse per sector.

**Dagresultaat houdt rekening met de transacties van vandaag.** De oude formule was
`(koers nu − vorige slotkoers) × aantal`. Koop je vandaag bij, dan rekent die ook
voor de nieuwe stukken de beweging aan die vóór jouw aankoop plaatsvond — winst of
verlies dat je nooit gemaakt hebt. `daily_pl()` werkt nu als een echte
kasstroomredenering: eindwaarde − beginwaarde − aankopen van vandaag + verkopen van
vandaag, waarbij het aantal bij opening uit het huidige aantal afgeleid wordt. Dat
klopt ook bij méérdere transacties op één dag, elk tegen zijn eigen prijs. Een
positie die je vandaag volledig nieuw opbouwt krijgt nu ook een dagresultaat
(referentie = je aankoopprijs) in plaats van uit de tabel te verdwijnen. De functie
volgt voortaan ook de rekeningfilter van de pagina.

**Twee kolommen bij in de dagresultaattabel.** *Gem. waarde (€)* toont de
gemiddelde aankoopwaarde per stuk (FIFO-kostbasis in euro), zodat je de dagbeweging
naast je totale instappositie ziet. *Referentie* toont de koers waartegen de
dagwinst effectief gemeten wordt: zonder transacties de vorige slotkoers, en anders
het gewogen gemiddelde van die slotkoers en de prijs van elke transactie van vandaag.
Een extra kolom *Vandaag* markeert met 📥/📤/🔁 welke posities verhandeld zijn.

**Portefeuillepagina: open posities staan nu bovenaan**, gevolgd door de nieuwe
sectorspreiding en pas daarna het totaal per activum.

**Nieuw: spreiding per domein/sector.** Een taartdiagram met de verdeling van de
portefeuille over sectoren, op huidige waarde of op geïnvesteerd kapitaal, met een
tabel met de gewichten ernaast en een waarschuwing zodra één sector 40% of meer
weegt. De toewijzing gebeurt via een uitbreidbare keuzelijst: dertien
GICS-hoofdsectoren in het Nederlands worden standaard meegeleverd, en je kan er zelf
rubrieken aan toevoegen (`sector_list` in de instellingen). Nieuw in de database:
`assets.sector` en `assets.sector_source`. Bij het aanmaken van een activum wordt de
sector automatisch opgehaald bij Yahoo Finance en vertaald naar de Nederlandstalige
lijst; op de pagina Activa staat een kolom *Sector*, een blok om de lijst te beheren,
en een knop om sectoren voor alle activa in één keer online op te halen. Een
handmatige toewijzing wordt nooit door een automatische overschreven.

**Dividenden volgen nu de rekeningfilter in de tabel met open posities.** Had je
hetzelfde aandeel op twee rekeningen en is er één gesloten, dan bleven de dividenden
van die gesloten rekening meetellen in de kolom *Dividend*. Ze horen bij een positie
die er niet meer is en verdwijnen nu mee met de filter.

**TOB wordt herberekend bij een eigen wisselkoers.** `_recompute_tob_preview()` sloeg
lijnen met `fx_manual` volledig over. Bedoeling was jouw koers te beschermen, maar
daardoor werd ook de TOB nooit meer nagekeken — terwijl de beurstaks een percentage
van de EUR-tegenwaarde is en dus per definitie meebeweegt met de koers. Zulke lijnen
worden nu wél gecontroleerd, mét behoud van jouw koers: enkel de EUR-tegenwaarde en
de TOB worden erop hertekend. Ze zijn in het overzicht gemarkeerd met 💱. Lijnen met
een handmatige TOB en toekenningen blijven zoals voorheen ongemoeid. In het
transactieformulier verschijnt bovendien een melding wanneer een handmatig ingevulde
TOB niet meer overeenkomt met de berekende waarde.

**AI-marktopportuniteiten: minstens één niet-Amerikaanse naam per categorie.** De
prompt stelt dit nu als harde voorwaarde, met de reden erbij: een portefeuille die
enkel Amerikaanse namen voorgeschoteld krijgt, bouwt ongemerkt een dollar- en
concentratierisico op. Wordt er in een categorie tóch enkel Amerikaans voorgesteld,
dan wordt dat gemeld in plaats van stilgezwegen — weggooien zou een lege categorie
opleveren. Niet-Amerikaanse noteringen zijn met 🌍 gemarkeerd.

**Aandelen die je al bezit verdwijnen uit de suggesties.** Een koopidee voor een
positie die al in de portefeuille zit, is geen idee maar ruis, en het verdringt een
suggestie die je wél iets bijbrengt. Ideeën worden nu geweerd bij het opslaan én bij
het weergeven — dus ook een aandeel dat je pas ná het advies gekocht hebt, verdwijnt
uit de lijst en uit de opvolgingstabel. De vergelijking gebeurt op ticker, ISIN en
basissymbool, zodat BMW.DE en BMW.F als hetzelfde bedrijf gelden.

**Statuspagina: archief voor afgevinkte meldingen.** Alles wat je met '✓ Gezien'
markeert — een split die je bewust niet registreert, bijvoorbeeld — verhuist naar
een archiefsectie die standaard dichtgeklapt staat. De melding blijft bestaan (de
toestand is immers niet opgelost), maar verdringt de openstaande punten niet meer.

**Sluitingsdagen geven geen valse waarschuwingen meer.** De planner haalt élke vijf
minuten koersen op, ook in het weekend en op feestdagen; die leveren dan allemaal
dezelfde slotkoers op, en dat werd als 'geen koersbeweging' gemeld. Nieuw in
`database.py` is een volledig offline berekende beurskalender: de Paasformule plus de
Euronext-sluitingsdagen (Nieuwjaar, Goede Vrijdag, Paasmaandag, 1 mei, Kerstmis,
tweede kerstdag) en de NYSE-kalender met de 'observed'-regel voor vaste feestdagen in
het weekend. `detect_flat_prices()` kijkt enkel nog naar dagen waarop de beurs voor
dát activum open was, en `detect_stale_prices()` telt de leeftijd van een koers in
béúrsdagen in plaats van kalenderdagen — zo geeft een lang kerstweekend geen golf
waarschuwingen. Bovenop de kalender staat een marktbrede terugval: staan álle activa
van eenzelfde markt (vanaf drie) op dezelfde dag stil, dan lag de handel stil en is
dat een marktfeit, geen datafout. Die vangt ook lokale sluitingen op die de kalender
niet kent, zoals 21 juli of een halve handelsdag op kerstavond.

**Waarom een kalender en geen online bron.** Een beurskalender-API zou een extra
afhankelijkheid, een extra faalpunt en een extra netwerkcall per controle betekenen,
voor gegevens die jaren vooruit exact berekenbaar zijn. De feestdagen liggen vast en
Pasen volgt uit een formule van drie regels.

## 1.0.0
Eerste stabiele versie. De app is functioneel compleet voor het doel waarvoor ze
gebouwd is, draait op twee platformen, en is nu ook gedocumenteerd.

**Nieuw: HANDLEIDING.md.** Een volledige handleiding in twaalf hoofdstukken: de
basiswerking (FIFO per rekening, euro als rekeneenheid, fotomoment, cash-afleiding,
koersbronnen), een stappenplan voor een verse installatie, uitleg per pagina over
alle twaalf schermen, de mogelijkheden van de Streamlit-schil zelf (sorteren,
CSV-export, bewerkbare tabellen, grafiekwerkbalk, het menu rechtsboven), de
achtergrondtaken, de fiscale motor, de AI-luiken, en probleemoplossing.

**Nieuw hoofdstuk: ontwerpkeuzes.** Twaalf keuzes met hun motivering vastgelegd,
zodat later te beoordelen valt of een wijziging een verbetering is of het ongedaan
maken van een bewuste beslissing. Onder meer: waarom cash afgeleid wordt in plaats
van geboekt, waarom detectie en toepassing gescheiden zijn bij splits en
herberekeningen, waarom de FIFO per rekening loopt terwijl de vrijstelling per
persoon telt, waarom er nooit stilzwijgend op wisselkoers 1,0 teruggevallen wordt,
waarom fiscale parameters instellingen zijn en geen code, en waarom de Windows-versie
geen fork is.

**README.md** vervangen door een echte inhoudsopgave die naar de handleiding en de
Windows-installatie verwijst.

Geen functionele wijzigingen aan de code in deze versie.

## 0.47.0
Nieuw: de app kan nu ook als zelfstandige toepassing op een Windows-PC draaien,
los van Home Assistant. Er is bewust geen aparte versie van de code gemaakt: het
is dezelfde codebase, met een aparte opstartlaag in de nieuwe map `windows/`.

**Waarom dit kon.** In de Python-code zat geen enkele afhankelijkheid van Home
Assistant: geen Supervisor-API, geen ingress-logica, geen HA-tokens. Ingress is
enkel een proxy voor de Streamlit-poort, en alle instellingen (ook de OpenAI-sleutel)
zitten in de database, niet in de add-on-configuratie. De koppeling bestond dus
alleen uit `run.sh` (bash) en het datapad `/share/portfolio_tracker`.

**Nieuw in `windows/`:** `setup.bat` (virtuele omgeving, pakketten, database),
`start.bat` (scheduler op de achtergrond, Streamlit op de voorgrond), `stop.bat`,
`config.bat` met overschrijfbestand `config.local.bat`, `requirements-windows.txt`
en `INSTALL_WINDOWS.md`.

**Aanpassing in `database.py`.** `DATA_DIR` valt nu terug op een platformafhankelijke
standaard via de nieuwe functie `default_data_dir()`. De omgevingsvariabele `DATA_DIR`
wint zoals voorheen, dus voor de add-on verandert er niets: die blijft
`/share/portfolio_tracker` gebruiken. Zonder deze splitsing zou een start op Windows
zonder die variabele naar `C:\\app\\data` schrijven.

**Aanpassing in `market_data.py`.** `_fsma_cache_path()` gebruikt dezelfde functie,
zodat de FSMA-cache altijd bij de rest van de data staat.

**Twee vallen die opgevangen zijn.** Windows heeft geen systeembrede tijdzonedatabank,
waardoor `ZoneInfo("Europe/Brussels")` in `scheduler.py` zou falen; daarom staat
`tzdata` in `requirements-windows.txt`. En `setup.bat` weigert Python 3.13 of hoger,
omdat numpy 1.x daar geen wielen voor heeft en de installatie dan zou proberen te
compileren.

**Let op bij gebruik.** Laat de Windows-versie en de add-on nooit gelijktijdig op
dezelfde database werken: SQLite in WAL-modus verwacht een enkele schrijver.

## 0.46.0
Fix: het ophalen van de FSMA-lijsten leverde 0 namen op.

**Oorzaak.** De downloads en het lezen van de PDF's lukten wel (vandaar geen foutmelding en
niets in de log), maar de naamherkenning niet. De parser vereiste dat elke regel begon met het
opsommingsteken '\u25a0' of '\u2022'. Hoe die tekens uit een PDF komen hangt echter af van de
tekstextractie: pypdf geeft ze soms als een ander glyph terug, en soms helemaal niet. Daardoor
herkende de parser geen enkele regel als naam.

**Opgelost.** De opsommingstekens worden nu enkel nog AFGEPELD, niet vereist. De filtering
gebeurt op inhoud: kop-, voetnoot-, land-, adres-, beheerder- en sectieregels vallen weg, de
rest is een fonds- of compartimentsnaam. Bijkomend wordt bij te weinig tekst automatisch de
layout-modus van pypdf geprobeerd, die de opmaak beter bewaart.

**Zichtbaar gemaakt.** Nieuw blokje '🔧 Diagnose van het inlezen' toont per lijst het aantal
pagina's, hoeveel tekst eruit kwam, hoeveel namen herkend werden, en een staal van de ruwe
tekst. Er wordt nu ook naar de log geschreven (aantal pagina's/tekens/namen per lijst, en een
waarschuwing met staal als er 0 namen uitkomen). Zo is dit nooit meer een zwarte doos.

Getest op echte FSMA-tekst in drie varianten - met opsommingstekens, zonder, en met een
afwijkend glyph - telkens met hetzelfde resultaat en zonder ruis (landkoppen, adressen en
kopteksten worden geweerd).

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.45.0
Drie correcties aan de koersdoelen en aan het tijdstip in het dashboard.

**1. Dashboard toont het GEMIDDELDE van de laatste 9 AI-koersdoelen.** De AI mag nog altijd
koersdoelen bepalen bij het portefeuilleadvies, maar het dashboard middelt voortaan de laatste
9 bepalingen (of minder als er minder zijn) in plaats van enkel het allerlaatste te tonen. Dat
dempt uitschieters van één adviesronde. Een HANDMATIG koersdoel heeft altijd voorrang: eerst
het doel op het activum, anders dat van de laatste transactie. Pas als er geen handmatig doel
is, geldt het AI-gemiddelde. De tooltip op de kolom 'Koersdoel' legt dit uit.

**2. Koersdoelen van 0 worden overal geweerd.** Een 0 betekent 'niet bepaald' en vertekende
zowel de grafiek als het gemiddelde. Voortaan:
- worden nulwaarden niet meer in de koersdoel-historiek opgeslagen;
- verdwijnen ze uit de tijdlijn en de grafiek op de pagina Evolutie;
- tellen ze niet mee in het gemiddelde van de laatste 9;
- wordt een handmatig koersdoel van 0 behandeld als 'geen handmatig doel' (dan geldt het
  AI-gemiddelde);
- worden bestaande nulrijen bij de eerste start eenmalig opgeruimd.

**3. Dashboardkolom toont nu de laatste ECHTE koerswijziging.** De kolom heette 'Laatste update'
en toonde het moment van de laatste OPHALING - daardoor stond er ook in het weekend een tijdstip
van vandaag, terwijl de koers al sinds vrijdag niet meer bewoog. De kolom heet nu 'Koers
gewijzigd' en toont het moment waarop de koers voor het laatst effectief veranderde. Technisch:
de app zoekt het begin van de huidige reeks identieke koersen in price_history, zodat ophalingen
bij gesloten markt het tijdstip niet meer verschuiven.

Getest: het gemiddelde over 9 (met nullen ertussen die correct genegeerd worden), de voorrang
van handmatige doelen, en het weekendscenario - een koers die vrijdag 17:30 laatst bewoog en
daarna zaterdag drie keer identiek werd opgehaald, toont nu correct vrijdag 17:30.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.44.0
Punt 9, tweede bron: de officiële FSMA-lijsten van in België openbaar aangeboden fondsen, als
aanvulling op de XBRU-controle van 0.43.

**Wat er is toegevoegd.** Op de Activa-pagina, onder de XBRU-knop: '📋 Tweede bron: FSMA-lijst
van in België aangeboden fondsen'. De app haalt vier officiële FSMA-lijsten op (ICB's en hun
compartimenten, naar Belgisch én buitenlands recht), leest de namen eruit en koppelt ze aan je
fondsen/ETF's met een gelijkenisscore. Je krijgt per fonds de beste match plus alternatieven.
De lijsten worden lokaal gecachet en wekelijks ververst.

Dit vult precies het gat van de XBRU-controle: fondsen die in Amsterdam of Parijs noteren maar
wél in België worden aangeboden (het IWDA-geval) staan hier wel in.

**Bewuste beperking: advies, geen automatisme.** De FSMA-lijsten bevatten GEEN ISIN's, enkel
namen. Koppelen kan dus alleen op naam en is nooit sluitend. Daarom toont de app een voorstel
met een score en zet JIJ het BE-vinkje aan via een bevestigingsselectie. Net als in 0.43 wordt
er niets automatisch afgezet. Reden blijft dezelfde: het BE-vinkje bepaalt de TOB voor fondsen
(1,32% / 0,12% / 0,35%), dus een foute automatische omzetting kost of bespaart je echt geld.
Scores onder ~85 zijn het nakijken waard; een hoge score is een aanwijzing, geen bewijs.

Bronnen (officiële FSMA-PDF's, wekelijks bijgewerkt): lijst van de compartimenten en van de
ICB's naar buitenlands recht (art. 149 ICBE-wet) en dezelfde twee naar Belgisch recht.

Nieuwe afhankelijkheid: pypdf (zuiver Python, geen systeempakketten) om de lijsten te lezen.
Getest: het inlezen van de lijstopmaak en de naamkoppeling zijn gevalideerd op echte
FSMA-tekst (o.a. 'iShares Euro Dividend UCITS ETF EUR Dist' koppelt correct op 100), en de
app blijft netjes werken als de lijsten niet bereikbaar zijn.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.43.0
Punt 9: de Belgische notering (FSMA) automatisch laten bepalen via Euronext, plus uitleg bij
het BE-vinkje over waarom dit fiscaal telt.

**Nieuw op de Activa-pagina: '🇧🇪 Belgische notering (FSMA) automatisch bepalen'.** Controleert
per ISIN bij Euronext (nu de ontsleuteling werkt) of het effect op de Belgische
gereglementeerde markt noteert - Euronext Brussel, MIC XBRU. Je krijgt een tabel met per
activum de gevonden handelsplaats en de uitslag.

**BELANGRIJKE VEILIGHEID: het vinkje wordt enkel AANGEZET, nooit automatisch afgezet.** Reden:
XBRU-notering bewijst dat een effect op de Belgische gereglementeerde markt verhandeld wordt,
maar het ONTBREKEN ervan bewijst niet dat een fonds niet in België wordt aangeboden. Veel in
België geregistreerde ETF's noteren in Amsterdam of Parijs (het klassieke voorbeeld: IWDA op
XAMS). Zou de app die automatisch afzetten, dan zou ze de TOB verkeerd berekenen: 0,35% i.p.v.
1,32% op een kapitaliserende ETF. Effecten die niet op XBRU noteren worden dus gerapporteerd,
maar ongemoeid gelaten.

**Uitleg bij het BE-vinkje (tooltip).** Het vinkje stuurt de TOB voor FONDSEN en ETF's:
- in België aangeboden + KAPITALISEREND -> 1,32% (max 4.000 EUR)
- in België aangeboden + UITKEREND -> 0,12% (max 1.300 EUR)
- NIET in België aangeboden -> 0,35% (max 1.600 EUR)
Voor gewone aandelen verandert het vinkje niets (altijd 0,35%). Op de roerende voorheffing
heeft het GEEN invloed: die 30% hangt af van de aard van de inkomsten en van je tussenpersoon,
niet van de FSMA-registratie. Op een ETF-aankoop van 10.000 EUR is dat het verschil tussen
132 EUR en 35 EUR TOB - vandaar de voorzichtige aanpak hierboven.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

## 0.42.0
Euronext-ontsleuteling CORRECT gemaakt. In 0.41 zat de aanname fout; met de brondata die je
bezorgde (ajax_secure + cryptojs-aes-format.js) ligt het schema nu exact vast.

**Wat er fout was in 0.41.** Ik ging uit van een vaste AES-sleutel + vaste IV in de JS-bundel.
Het is in werkelijkheid de Drupal-module 'ajax_secure' met het CryptoJS-AES-JSON-formaat van
brainfoolong: per antwoord een WILLEKEURIGE salt en IV, waaruit sleutel (32 B) en IV (16 B)
worden afgeleid met OpenSSL's EVP_BytesToKey (MD5, 1 iteratie) uit één vast WACHTWOORD. Er valt
dus geen vaste sleutel te vinden - dat is waarom het automatisch opbouwen niets vond.
Bijkomend: de diagnose kapte de body af op 2500 tekens, waardoor enkel het veld 'ct' zichtbaar
was en de velden 'iv' en 's' (die achteraan staan) gemist werden.

**Nu correct geimplementeerd:**
- envelope {"ct","iv","s"} wordt geparst; sleutel+IV worden per antwoord afgeleid uit het
  wachtwoord + de meegestuurde salt (EVP_BytesToKey/MD5), daarna AES-256-CBC/PKCS7;
- de ontsleutelde tekst is JSON.stringify'd en wordt nog één keer door json.loads gehaald;
- het wachtwoord komt uit drupalSettings.ajax_secure.kye van de live pagina, met de
  ingebouwde terugval '24ayqVo7yJma' uit hun eigen JS. Zonder instellingen werkt het dus al.

**Wachtwoordwijziging: detectie + zelfherstel.** 'Wachtwoord opnieuw bepalen' op de
statuspagina leest het wachtwoord uit de live pagina en VALIDEERT het tegen een vers
versleuteld staal voor het wordt opgeslagen. Werkt het niet meer, dan volgt een duidelijke
waarschuwing; de dagelijkse statuscontrole (22:45) herstelt een wijziging automatisch en logt
de nieuwe afdruk. Handmatig instellen kan nog steeds (nu één veld: het wachtwoord, geen
sleutel/IV meer).

**Diagnose verbeterd.** '🔧 Euronext-respons inspecteren' toont nu ook de envelope-velden, de
ontsleutelstatus, het begin van de ONTSLEUTELDE inhoud en de staart van de ruwe respons (waar
iv en s staan) - zodat een volgende wijziging meteen zichtbaar is.

Getest: het volledige schema is lokaal end-to-end gevalideerd tegen een nagebootst Euronext-
antwoord - ontsleuteling, doorstroming naar de bestaande tabelparser (koers 72,50 EUR correct
geëxtraheerd), en het zelfherstel na een gewijzigd wachtwoord.

Herbouwen (niet enkel herstarten) via de knop "Herbouwen" in Home Assistant.

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