# Portfolio Tracker - Handleiding

Versie 1.0.0

---

## Inhoud

1. [Wat deze app doet](#1-wat-deze-app-doet)
2. [Snel starten: een lege portefeuille opzetten](#2-snel-starten-een-lege-portefeuille-opzetten)
3. [De basiswerking](#3-de-basiswerking)
4. [De interface: wat Streamlit zelf kan](#4-de-interface-wat-streamlit-zelf-kan)
5. [De pagina's een voor een](#5-de-paginas-een-voor-een)
6. [Wat er op de achtergrond draait](#6-wat-er-op-de-achtergrond-draait)
7. [De fiscale motor in detail](#7-de-fiscale-motor-in-detail)
8. [De AI-adviseur](#8-de-ai-adviseur)
9. [Data invoeren en corrigeren](#9-data-invoeren-en-corrigeren)
10. [Ontwerpkeuzes](#10-ontwerpkeuzes)
11. [Onderhoud, back-up en probleemoplossing](#11-onderhoud-back-up-en-probleemoplossing)
12. [Bijlagen](#12-bijlagen)

---

## 1. Wat deze app doet

Portfolio Tracker houdt een beleggingsportefeuille bij vanuit het standpunt van een
Belgische particuliere belegger. Het verschil met een gewone koersvolger zit in drie
dingen.

**Fiscaal correct.** De app rekent de taks op beursverrichtingen (TOB) per transactie,
de roerende voorheffing en de buitenlandse bronbelasting per dividend, en de
meerwaardebelasting volgens het stelsel dat vanaf 2026 geldt, inclusief het fotomoment
van 31 december 2025. Ze doet dat niet als schatting achteraf maar als onderdeel van
elke boeking.

**Alles in euro, op transactiedatum.** Een aankoop in dollar wordt omgerekend met de
wisselkoers van die dag, en die koers wordt bewaard. Zo blijft je kostbasis stabiel,
ook als de dollar later beweegt.

**Per rekening.** Heb je effecten bij twee of drie brokers, dan houdt de app die
strikt gescheiden voor de FIFO-berekening. Loten op rekening A voeden geen verkoop
op rekening B. Voor de fiscus is de belasting globaal per persoon; voor je
administratie is de scheiding per rekening wat je nodig hebt om je brokerafschriften
te kunnen aflezen.

Daarbovenop komt een AI-adviseur die dagelijks je bestaande posities beoordeelt en
apart daarvan koopideeën aandraagt uit de bredere markt.

### Wat de app niet is

Geen boekhoudpakket en geen aangiftesoftware. De cijfers zijn bedoeld om te weten waar
je staat en om je aangifte voor te bereiden, niet om ze blind over te nemen. Ze zijn
ook geen beleggingsadvies: de AI-luiken zijn een gesprekspartner, geen adviseur.

---

## 2. Snel starten: een lege portefeuille opzetten

Voor een verse installatie (bijvoorbeeld de Windows-versie voor een tweede,
onafhankelijke portefeuille) is dit de kortste weg naar een werkend geheel.

**Stap 1: rekeningen aanmaken.**
Ga naar `⚙️ Instellingen` → `🏦 Rekeningen`. Zet hier je brokers neer: Bolero, Degiro,
Saxo, wat je ook gebruikt. Doe dit eerst, want elke transactie vraagt een rekening.
Per rekening kun je ook een beleggingsprofiel instellen, dat de AI later gebruikt.

**Stap 2: fiscale instellingen nakijken.**
`⚙️ Instellingen` → `🧾 Meerwaardebelasting` en `🏛️ TOB & bronbelasting`. De standaarden
kloppen voor de meeste mensen (10 procent meerwaardebelasting, 10.000 euro vrijstelling
per persoon, 0,35 procent TOB op aandelen, 30 procent roerende voorheffing), maar
controleer je huwelijksstelsel en je dividendvrijstelling.

**Stap 3: activa aanmaken.**
`🏢 Activa` → `➕ Activum toevoegen`. Vul een ticker in en klik op
`🔍 Info ophalen via Yahoo Finance`. Naam, munt, beurs, ISIN en type worden dan meestal
vanzelf ingevuld. Controleer vooral drie velden, want die bepalen je belasting:
het **type** (aandeel, ETF, obligatie), bij een ETF het **subtype** (distribuerend of
kapitaliserend), en **in België aangeboden ja of nee**. Die drie samen bepalen het
TOB-tarief.

**Stap 4: transacties ingeven.**
`➕ Transacties` → `📝 Nieuwe transactie`. Aantal, prijs per stuk, munt, datum,
rekening. De TOB en de EUR-tegenwaarde rekent de app zelf uit; je ziet het resultaat
voor je bevestigt. Heb je veel historiek, sla dan door naar stap 4b.

**Stap 4b: of importeer in bulk.**
`⚙️ Instellingen` → `🗃️ Data` → `📥 Bulk-import via Excel`. Download de template, vul
ze in, upload ze terug. Je krijgt eerst een voorbeeld met de fouten per rij; pas na je
bevestiging wordt er iets weggeschreven.

**Stap 5: stortingen registreren.**
`💶 Cash` → `➕ Storting / opname`. Enkel echte geldstortingen en -opnames. Aankopen,
verkopen, dividenden en kosten leidt de app zelf af. Zonder je stortingen komt je
beschikbare cash negatief uit.

**Stap 6: fotomomenten ophalen.**
Heb je effecten van voor 2026? Ga dan naar `🏢 Activa` → `📋 Overzicht` en klik op
`📸 Fotomoment ophalen`. De app haalt de slotkoers van 31/12/2025 op. Zonder die
waarde kan de meerwaardebelasting op oude loten niet correct berekend worden.

**Stap 7: dividenden bijhouden.**
`💰 Dividenden`. Voor Belgische aandelen volstaat de eenvoudige invoer. Voor
buitenlandse dividenden gebruik je de gedetailleerde modus, waarin je de
bronbelasting en de Belgische voorheffing apart ziet.

**Stap 8: optioneel de AI activeren.**
`⚙️ Instellingen` → `🔑 API-sleutel`. Zonder sleutel werkt alles behalve de
AI-luiken gewoon.

Na deze acht stappen toont het dashboard een volledig beeld en begint de scheduler
elke vijf minuten koersen weg te schrijven.

---

## 3. De basiswerking

### 3.1 De vier bouwstenen

De hele app draait op vier soorten records in een SQLite-database.

**Activa** zijn de effecten zelf: ticker, naam, ISIN, munt, type, land van herkomst.
De ticker is de sleutel binnen de app; de ISIN is de sleutel naar de buitenwereld.

**Transacties** zijn aankopen en verkopen: datum, aantal, prijs, munt, rekening,
kosten en TOB. Elke transactie bewaart ook zijn eigen wisselkoers en EUR-bedrag.

**Dividenden** (en interest en securities lending) zijn inkomsten, met hun eigen
keten van bruto naar netto.

**Cashbewegingen** zijn stortingen en opnames. Alle andere geldstromen worden
afgeleid, niet geboekt.

Daarnaast bewaart de app koershistoriek, AI-adviezen, statusmeldingen,
koersdoelhistoriek en instellingen.

### 3.2 FIFO per rekening

Verkoop je 50 stukken die je in drie keer gekocht hebt, dan gaan de oudste er het
eerst uit. Dat is de standaardmethode en ze bepaalt je kostbasis, en dus je
belastbare meerwaarde.

De app past FIFO toe per combinatie van **activum en rekening**. Koop je hetzelfde
aandeel bij twee brokers, dan zijn dat twee aparte voorraden. Verkoop je bij broker B,
dan wordt de kostbasis van broker B gebruikt, niet de goedkopere loten van broker A.
Dat komt overeen met wat je broker zelf rapporteert.

De app weigert een verkoop waarvoor er op die rekening op die datum onvoldoende
stukken zijn. Dat is een bewuste rem: zo'n verkoop zou verderop een negatieve positie
of een onmogelijke kostbasis geven.

### 3.3 Euro als rekeneenheid

Alles wordt bijgehouden in euro, omgerekend op de datum van de verrichting. De
wisselkoers van die dag wordt mee opgeslagen, zodat de omrekening reproduceerbaar
blijft.

Er wordt nooit stilzwijgend teruggevallen op koers 1,0. Lukt de historische koers
niet, dan gebruikt de app de koers van vandaag en zegt dat er ook bij. Lukt ook dat
niet, dan vraagt ze je om je eigen koers in te vullen en weigert ze de transactie
zolang die ontbreekt. Dit is geen overdreven voorzichtigheid: een stille terugval op
1,0 betekende ooit dat de TOB op een dollarbedrag berekend werd alsof het euro's waren.

Heb je het afschrift van je broker, gebruik dan de knop om je **eigen wisselkoers**
in te geven. Dat is altijd nauwkeuriger dan een dagkoers uit een externe bron, omdat
je broker een eigen moment en een eigen marge hanteert.

### 3.4 Kosten, TOB en belasting: drie aparte dingen

De app houdt ze bewust uit elkaar.

**Transactiekosten** zijn wat je broker aanrekent. Ze verlagen je rendement maar zitten
niet in de meerwaardeberekening.

**TOB** is de taks op beursverrichtingen, verschuldigd bij aankoop en verkoop. Het
tarief hangt af van het producttype en er geldt een plafond per verrichting.

**Meerwaardebelasting** wordt pas bij verkoop berekend, op het niveau van je hele
persoon en niet per transactie.

In de cash-berekening tellen kosten en TOB wel gewoon mee: je hebt dat geld
daadwerkelijk betaald. Daarom komt het bedrag onder "Aankopen" in het cash-overzicht
hoger uit dan aantal maal prijs, en klopt het exact met je brokerafschrift.

### 3.5 Het fotomoment

Voor stukken die je voor 2026 gekocht hebt, geldt als fiscale instapprijs de hoogste
van twee waarden: je werkelijke aankoopprijs, of de slotkoers op 31 december 2025.
Die tweede waarde noemt de app het **fotomoment**.

Concreet, met S de verkoopopbrengst, C je werkelijke kostprijs en F de fotomomentwaarde:

- Ligt S boven F, dan is de belastbare meerwaarde S min F. Lag je aankoopprijs C hoger
  dan F, dan mag je tot en met boekjaar 2030 de gunstiger historische kostprijs
  gebruiken, met een ondergrens van nul (historische minderwaarden zijn niet aftrekbaar).
- Ligt S onder F, dan heb je een minderwaarde na het fotomoment, en die is wel aftrekbaar.

Vanaf boekjaar 2031 telt altijd de fotomomentwaarde.

Voor alles wat je vanaf 2026 koopt, speelt het fotomoment niet. Die stukken volgen
gewoon hun werkelijke kostprijs. Zet je een nieuwe portefeuille op met uitsluitend
recente aankopen, dan kun je de hele fotomoment-machinerie negeren.

### 3.6 Waar de koersen vandaan komen

De ISIN is het startpunt, niet de ticker. Een ISIN is uniek en ondubbelzinnig; een
tickersymbool met beurssuffix is dat niet.

De volgorde is: eerst de ISIN vertalen naar een Yahoo-symbool (dat resultaat wordt
gecacht op het activum), dan de externe bronnen op ISIN in de volgorde onvista,
Euronext, Tradegate, Deutsche Börse Live, dan de opgeslagen ticker rechtstreeks op
Yahoo, en als laatste redmiddel de handmatige koers.

Drie mechanismen houden dit betaalbaar:

- Faalden zonet alle bronnen voor een effect, dan worden ze dertig minuten overgeslagen.
- Effecten die je op "enkel handmatig" zet, worden nooit online opgezocht.
- Na tien mislukte pogingen op rij stopt de app met proberen voor dat effect, tot je
  de teller terugzet op de Activa-pagina of een handmatige koers instelt.

Dat laatste is geen fout maar een oplossing. Sommige effecten, zoals een
niet-beursgenoteerde warrant, staan nergens publiek genoteerd. Een handmatige koers
is dan het juiste antwoord.

### 3.7 Snelheid: de app kijkt in de database, niet op het internet

Het scherm laadt uit `price_history`, de tabel die de scheduler elke vijf minuten
bijwerkt. Tijdens het renderen worden geen netwerkcalls gedaan, behalve voor effecten
zonder koers van de laatste twintig minuten. De knop `Ververs prijzen` forceert wel
een volledig live rondje.

Daarbovenop zit een cache van zestig seconden op het portefeuilleoverzicht. Zonder die
cache zou elke klik de volledige FIFO-berekening opnieuw doen.

### 3.8 De cash-berekening

Beschikbare cash is stortingen min opnames, plus verkopen, min aankopen, plus
dividenden, min rekeningkosten. Alleen de eerste twee geef je in; de rest volgt uit
wat er al in de database staat.

Komt je beschikbare cash negatief uit, dan ontbreken er stortingen. Dat is de
gebruikelijke oorzaak, niet een rekenfout.

### 3.9 Performance shares

Aandelen die je gekregen hebt in plaats van gekocht (RSU's, warrants, gratis aandelen)
werken anders: geen aankoopprijs, geen TOB, wel personenbelasting op de waarde bij
toekenning. Vink bij zo'n transactie **performance share** aan en vul de betaalde
personenbelasting in.

Omdat er geen enkel juist antwoord bestaat op de vraag wat zulke aandelen je nu
"gekost" hebben, laat de app je kiezen tussen drie zienswijzen op het dashboard:

| Zienswijze | Kostbasis | Bedoeld voor |
|---|---|---|
| Personenbelasting als investering | de betaalde belasting | wat het je echt gekost heeft |
| Personenbelasting als kost | nul (aandelen gratis) | zelfde netto, andere opsplitsing |
| Personenbelasting negeren | de toekenningswaarde | zuivere koersprestatie |

De eerste twee geven hetzelfde nettoresultaat; ze verschillen alleen in hoe het
uitgesplitst wordt. De keuze verschijnt alleen als je zulke producten hebt.

---

## 4. De interface: wat Streamlit zelf kan

De app is gebouwd op Streamlit. Een deel van de bruikbaarheid komt niet uit de app
maar uit dat framework, en die mogelijkheden zijn niet altijd zichtbaar.

### 4.1 De zijbalk

Links staan het menu, je totale portefeuillewaarde met winst of verlies, de
cumulatieve AI-kosten, en de datum. De zijbalk kan ingeklapt worden met het pijltje
bovenaan; op een smal scherm gebeurt dat vanzelf. Klik je hem weg, dan wordt de
grafiekruimte merkbaar breder.

### 4.2 Het menu rechtsboven

Achter de drie puntjes zitten enkele functies die van pas komen:

- **Rerun** herlaadt het script. Handig als je vermoedt dat je naar oude cijfers kijkt.
- **Settings** bevat het thema (licht of donker) en **Wide mode**. De app staat al op
  breed, maar de instelling kan per browser afwijken.
- **Print** maakt een afdruk van de huidige pagina, bruikbaar als pdf-export.

### 4.3 Tabellen kunnen meer dan ze tonen

Elke tabel in de app is een Streamlit-dataframe, en die kan:

- **Sorteren** door op een kolomkop te klikken. Bedragen zijn intern getallen gebleven
  en geen opgemaakte tekst, precies zodat sorteren numeriek werkt en niet alfabetisch.
- **Zoeken** met het vergrootglas dat verschijnt als je over de tabel gaat.
- **Downloaden als CSV** met het downloadicoon in dezelfde hoek. Dit is de snelste weg
  naar Excel; er is geen aparte exportknop nodig.
- **Schermvullend tonen** met het pijltje in de rechterbovenhoek.
- **Kolommen verslepen en versmallen** door de scheidingslijn in de kop te verplaatsen.

### 4.4 Bewerkbare tabellen

De overzichten van transacties, dividenden, activa en rekeningkosten zijn geen gewone
tabellen maar **editors**. Je typt rechtstreeks in een cel, en de wijziging wordt pas
weggeschreven als je op `💾 Wijzigingen opslaan` klikt. Tot dan kun je met Ctrl+Z terug.

Meerdere rijen tegelijk aanpassen kan met kopiëren en plakken vanuit Excel, zolang de
kolomvolgorde overeenkomt.

### 4.5 Grafieken

De grafieken zijn Plotly-figuren. Boven elke grafiek verschijnt bij het zweven een
werkbalk met zoom, pan, en **download als PNG**. Slepen in de grafiek zoomt in;
dubbelklikken zet terug. In de legende klik je een reeks aan of uit, en met een
dubbelklik isoleer je er een.

### 4.6 Formulieren

Waar je iets toevoegt, zit dat in een formulier: de app rekent pas als je op de knop
drukt, niet bij elke toetsaanslag. Enter in een tekstveld bevestigt het formulier.

### 4.7 Wat de app zelf toevoegt

Twee gedragingen zijn met opzet anders dan standaard Streamlit.

**Secties in plaats van tabbladen.** Bovenaan verschillende pagina's staan
keuzeknoppen die eruitzien als tabbladen. Het zijn er geen. Echte tabbladen springen
terug naar het eerste tabblad bij elke herberekening; deze onthouden je keuze, ook na
een volledige herlaad van de app.

**Filters die blijven staan.** Rekeningfilters, periodekeuzes en zienswijzen worden in
de database bewaard. Sluit je de browser en kom je morgen terug, dan staat de app nog
zoals je ze verliet.

---

## 5. De pagina's een voor een

### 5.1 📊 Dashboard

Het overzicht. Bovenaan kies je de periode (dit jaar of sinds het begin) en filter je
op rekening. Beide keuzes werken door in alles wat eronder staat.

**Kerncijfers.** Huidige waarde, geïnvesteerd kapitaal, ongerealiseerde en
gerealiseerde winst of verlies, dividenden en kosten.

**Dagresultaat vandaag.** Wat je positie sinds de vorige beursdag gedaan heeft. De
referentie is de laatste koers uit de database van voor vandaag, dus in de praktijk de
slotkoers van gisteren. Nieuwe posities verschijnen hier pas na een dag.

**Samenstelling.** Een taartdiagram dat je kunt omschakelen tussen huidige waarde en
geïnvesteerd kapitaal. Het verschil tussen beide vertelt welke posities zwaarder zijn
gaan wegen dan je inleg.

**Belasting van het jaar.** Je netto gerealiseerde resultaat, hoeveel vrijstelling je
verbruikt hebt en wat er eventueel verschuldigd is.

**AI-kooptips en gerealiseerde historiek** sluiten de pagina af.

### 5.2 💼 Portefeuille

De detailweergave van je posities.

**Open posities** toont per effect het aantal, de gemiddelde aankoopprijs, de huidige
koers, de waarde en het resultaat, met de bron en het tijdstip van de koers.

**Totaal resultaat per activum** telt alles samen: ongerealiseerd, gerealiseerd,
dividenden en kosten. Dit is de eerlijkste maatstaf per effect, want ze bevat ook
posities die je intussen volledig verkocht hebt.

**AI-advies** toont de rating per positie, met een pijl als het advies gewijzigd is
sinds de vorige ronde. De volledige tekst zit in een uitklapbaar blok.

**Prijsgeschiedenis** tekent de koers van een gekozen positie over een instelbaar
aantal dagen, opgebouwd uit wat de scheduler verzameld heeft.

### 5.3 💶 Cash

Drie secties: **posities** (het saldo per rekening met de opbouw), **storting of
opname** (het enige wat je hier handmatig ingeeft), en **bewegingen** (het volledige
grootboek met een lopend saldo).

In het grootboek zie je stortingen en opnames naast de automatisch afgeleide
bewegingen. Alleen handmatige bewegingen kun je verwijderen; de afgeleide verdwijnen
vanzelf als je de onderliggende transactie aanpast.

### 5.4 📈 Evolutie

Reconstrueert de waarde van je portefeuille door de tijd, per rekening, op basis van
je transacties en historische koersen. Twee grafieken: de absolute waarde in euro en
de procentuele meerwaarde tegenover je aankoopprijs. Je kiest welke rekeningen je
vergelijkt en over welke periode, van een maand tot vijf jaar.

Deze pagina doet echt werk (historische koersen ophalen en de portefeuille dag per dag
opnieuw opbouwen) en is daarom trager dan de rest. Het resultaat wordt gecacht tot je
transacties wijzigen.

Onderaan staat de **koersdoel-historiek**: hoe je koersdoelen, handmatig of door de AI
bepaald, in de tijd geëvolueerd zijn.

### 5.5 🏢 Activa

**Activum toevoegen.** Ticker invullen, info ophalen, controleren, bewaren. De knop
`🤖 Bepaal via AI` kan een koersdoel voorstellen. Bij een ISIN die Yahoo niet kent,
probeert de app de externe bronnen en zegt ze welke bron werkt.

**Overzicht.** Alle activa in een bewerkbare tabel, met een filter op naam of ticker.
Hier zitten ook de gereedschappen:

- `📸 Fotomoment ophalen` voor de slotkoers van 31/12/2025.
- `🔬 Bronnen diagnose` als een koers niet gevonden wordt: dit test elke bron apart en
  toont wat er precies terugkomt.
- De FSMA-lijst van in België aangeboden fondsen, om het TOB-tarief van je fondsen
  correct te zetten. Let op: die lijsten bevatten namen en geen ISIN's, dus de
  koppeling gebeurt op naam en vraagt je bevestiging.
- `🔧 Ticker corrigeren` verhuist alle transacties, dividenden en koersen mee.
- Koersophaling opnieuw activeren voor effecten waarvoor de app het opgegeven had.

**Splitsingen.** Een aandelensplitsing registreer je hier. De app past die niet
automatisch toe, ook al detecteert ze er een: dat zou je kostbasis wijzigen zonder je
medeweten. Pas na je bevestiging worden de transacties en de kostbasis aangepast.

### 5.6 ➕ Transacties

**Nieuwe transactie.** Het belangrijkste formulier van de app. Naast de gewone velden:

- **Eigen wisselkoers**: gebruik die van je brokerafschrift als je hem hebt.
- **TOB manueel aanpassen**: als je broker een ander bedrag aanrekende dan de
  berekening geeft. Een handmatig ingestelde TOB wordt door latere herberekeningen
  met rust gelaten.
- **Performance share**: voor toegekende in plaats van gekochte stukken.
- **Koersdoel**: optioneel, handmatig of via AI.

De app waarschuwt als ze de historische wisselkoers niet vindt, en weigert de
transactie als er helemaal geen koers beschikbaar is.

**Overzicht.** Bewerkbare tabel van alles wat je ingaf. Het blok
`🔄 TOB en EUR-tegenwaarde controleren` zoekt transacties waarvan de berekening niet
meer klopt met je huidige instellingen, toont eerst wat er zou wijzigen, en voert pas
uit na je expliciete bevestiging. Handmatige aanpassingen blijven daarbij gespaard.

**Rekeningkosten.** Kosten die niet aan één transactie hangen: bewaarloon,
abonnementen, jaarlijkse kosten. Ze verlagen je cash en tellen mee in je nettoresultaat.

### 5.7 💰 Dividenden

**Toevoegen** kan voor drie soorten inkomsten: dividend, interest en securities
lending. Alleen dividenden volgen de fiscale keten; de andere twee hebben eigen regels.

Er zijn twee invoerwijzen. **Eenvoudig** vraagt het bruto bedrag en de ingehouden
voorheffing. **Gedetailleerd** toont de volledige keten:

| | Betekenis |
|---|---|
| A | bruto voor buitenlandse bronbelasting |
| B | buitenlandse bronbelasting |
| C | bruto na bronbelasting, voor Belgische roerende voorheffing (A min B) |
| D | Belgische roerende voorheffing |
| netto | C min D |

Je vult in wat je op je afschrift ziet; de app leidt de rest af en waarschuwt als de
onderdelen elkaar tegenspreken.

**Overzicht** toont alle inkomsten in een bewerkbare tabel, met bovenaan hoeveel je via
je aangifte fiscaal kunt recupereren. De **herberekening** werkt zoals bij transacties:
eerst een voorbeeld van wat zou wijzigen, dan pas uitvoeren, en handmatig aangepaste
lijnen blijven ongemoeid.

### 5.8 🧮 Simulatie

Speeltuin zonder gevolgen. Je vult per positie in hoeveel je zou verkopen en eventueel
meteen zou terugkopen, kiest een datum, en de app rekent uit wat dat fiscaal betekent:
welke loten er uitgaan, welke meerwaarde belastbaar is, hoeveel vrijstelling er
overblijft en wat er te betalen valt. Het fotomoment wordt mee verrekend.

Er wordt niets opgeslagen en niets uitgevoerd. Dit is het gereedschap voor de vraag
"kan ik dit jaar nog iets verkopen zonder belasting te betalen".

### 5.9 🧾 Belgische Belasting

Het fiscale jaaroverzicht, per boekjaar te kiezen.

- **Vrijstellingsgebruik**: hoeveel van je jaarlijkse vrijstelling verbruikt is en wat
  er verschuldigd is.
- **Totale portefeuille**: waarde, kostbasis, ongerealiseerd en totaal resultaat.
- **Gerealiseerde transacties** van het jaar, lot per lot.
- **TOB betaald** in het jaar, met detail per transactie.
- **Dividendfiscaliteit**: wat er ingehouden werd en wat je via je aangifte kunt
  terugkrijgen, inclusief het forfaitair gedeelte buitenlandse belasting voor Franse
  aandelen als je dat ingeschakeld hebt.
- Een uitklapbaar blok met de wetgeving zoals de app ze toepast.

### 5.10 🤖 AI Advisor

Drie secties, die overeenkomen met drie verschillende opdrachten. Zie hoofdstuk 8.

### 5.11 🩺 Status

De gezondheid van je koersdata op één plek. De controle draait elke nacht om 22:45 en
kan hier met een knop meteen uitgevoerd worden. Ze meldt:

- koersen die al dagen niet meer ververst zijn,
- koersen die verdacht stil liggen,
- tickerwijzigingen of meerdere producten onder één ISIN,
- niet-geregistreerde aandelensplitsingen,
- naamsafwijkingen die op een fusie of rebranding kunnen wijzen.

Elke melding kun je afvinken. Splitsingen worden gemeld maar nooit automatisch
toegepast. Verder staan hier twee diagnosegereedschappen voor de Euronext-bron.

### 5.12 ⚙️ Instellingen

Vijf secties.

**🔑 API-sleutel.** Je OpenAI-sleutel, welk model elk van de drie AI-taken gebruikt,
een kostenraming per model, je geschatte investeringsvolume, en de privacymodus.

**🏦 Rekeningen.** Je rekeningen en hun beleggingsprofiel.

**🧾 Meerwaardebelasting.** Tarief, jaarlijkse vrijstelling en je huwelijksstelsel.

**🏛️ TOB & bronbelasting.** De TOB-tarieven en -plafonds per producttype, het
tarief roerende voorheffing, en de buitenlandse bronbelasting per land **per jaar**.
Die jaartabellen erven vooruit: stel je 2026 in, dan geldt dat ook voor 2027 en later,
tot je voor een later jaar iets anders instelt. Zo blijven oude dividenden berekend
volgens de tarieven die toen golden.

**🗃️ Data.** Bulk-import via Excel, koersen handmatig ophalen, en het overzicht van de
EUR-omrekening.

---

## 6. Wat er op de achtergrond draait

Naast de webinterface draait een tweede proces met de geplande taken.

| Wanneer | Wat |
|---|---|
| elke 5 minuten | koersen van de open posities opslaan |
| werkdag 07:45 | marktopportuniteiten zoeken (luik 2) |
| werkdag 18:00 | portefeuilleadvies genereren (luik 1) |
| dagelijks 22:30 | koers opvolgen van eerder voorgestelde aandelen |
| dagelijks 22:45 | statuscontrole |
| 1e van de maand 07:30 | AI-modelprijzen verversen |
| 1e van de maand 08:00 | belastingoptimalisatieadvies |

Die vijfminutenjob is de reden dat de app zo snel opent: het scherm leest wat dit
proces al verzameld heeft.

In de Home Assistant add-on start dit proces mee met de container. Op Windows leeft het
zolang `start.bat` openstaat. Sluit je dat venster, dan stoppen ook de achtergrondtaken.

---

## 7. De fiscale motor in detail

### 7.1 TOB

Het tarief hangt af van wat je verhandelt, en er geldt een plafond per verrichting.
De standaardwaarden in de app:

| Product | Tarief | Plafond |
|---|---|---|
| aandelen | 0,35 % | 1.600 euro |
| ETF distribuerend | 0,12 % | 1.300 euro |
| ETF kapitaliserend | 1,32 % | 4.000 euro |

Het onderscheid tussen distribuerend en kapitaliserend, en of het fonds in België
aangeboden wordt, maakt hier het grootste verschil. Vandaar dat de Activa-pagina daar
zoveel aandacht aan geeft: een verkeerd vinkje geeft een tarief dat een factor tien
kan schelen.

### 7.2 Meerwaardebelasting

Tien procent op je netto gerealiseerde meerwaarden, met een jaarlijkse vrijstelling
per belastingplichtige. Minwaarden worden verrekend met meerwaarden binnen hetzelfde
boekjaar. De belasting geldt vanaf boekjaar 2026.

De vrijstelling is per persoon, niet per rekening. De app houdt daarom een globale
teller bij, ook als je op rekening filtert. Je huwelijksstelsel bepaalt of er een of
twee vrijstellingen zijn.

### 7.3 Dividenden

De keten A tot D uit paragraaf 5.7 is het hart. Wat je fiscaal kunt recupereren komt
uit twee bronnen: de vrijstelling voor dividenden in je personenbelasting (een bedrag
per persoon per jaar), en voor Franse aandelen eventueel het forfaitair gedeelte
buitenlandse belasting.

De bronbelastingtarieven staan per land en **per jaar** ingesteld, omdat
dubbelbelastingverdragen wijzigen. Ontbreekt een jaar, dan erft het van het vorige.

### 7.4 Wat de app niet doet

Ze vult geen aangifte in, houdt geen rekening met je persoonlijke aftrekposten, en kent
de details van uitzonderingsregimes niet. Bij een grote of ongewone verrichting blijft
een boekhouder de juiste gesprekspartner.

---

## 8. De AI-adviseur

### 8.1 Drie opdrachten

**Luik 1, portefeuilleadvies.** Elke werkdag om 18:00 krijgt het model je bestaande
posities voorgelegd, met het beleggingsprofiel van de rekening waarop ze staan, en
geeft het een rating per positie plus een onderbouwing. Het kijkt uitsluitend naar wat
je al hebt.

**Luik 2, marktopportuniteiten.** Elke werkdag om 07:45, en dit kijkt juist buiten je
portefeuille: zes koopideeën, twee defensieve, twee matig speculatieve en twee sterk
speculatieve. Staat live websearch aan, dan zoekt het model actuele koersen en
berichtgeving op. Staat die uit, dan put het enkel uit zijn trainingskennis en kent
het het nieuws van vandaag niet.

De koers van elk voorgesteld aandeel wordt daarna ongeveer honderd dagen opgevolgd, zodat
je achteraf kunt zien of de suggesties iets waard waren.

**Belastingoptimalisatie.** Maandelijks: waar zit ruimte in je vrijstelling, welke
posities zouden fiscaal interessant zijn om te bewegen.

Daarnaast kan de AI op verzoek een koersdoel voor één effect voorstellen, met een apart
in te stellen (goedkoper) model.

### 8.2 Privacy

Drie standen:

- **Uit**: volledige data, tickers en bedragen.
- **Bedragen verbergen**: enkel gewichten in procent, tickers blijven.
- **Volledig anoniem**: ook tickers en namen vervangen door POS1, POS2 en zo verder.

Bij volledig anoniem krijgt het model enkel type, profiel en gewicht. Het advies blijft
bruikbaar maar wordt minder specifiek; de ratings worden achteraf weer aan je echte
posities gekoppeld.

### 8.3 Kosten

Elke oproep wordt geregistreerd met zijn tokengebruik. De zijbalk toont het totaal, de
AI-pagina de uitsplitsing per functie en per maand. De raming per model wordt
maandelijks automatisch bijgewerkt, maar de echte factuur staat op je OpenAI-dashboard.

Wil je de kosten drukken: zet een goedkoper model voor de koersdoelen, schakel luik 2
of de websearch uit, of zet de dagelijkse luiken helemaal af en genereer handmatig
wanneer je iets nodig hebt.

---

## 9. Data invoeren en corrigeren

### 9.1 Bulk-import

De Excel-template heeft drie databladen (Transacties, Dividenden, Kosten) en een blad
met instructies. Onbekende tickers worden automatisch als activum aangemaakt op basis
van de optionele kolommen; vul naam, type en ETF-subtype in, anders klopt de
TOB-berekening niet.

Het proces is altijd tweetraps: eerst inlezen en valideren, met een overzicht van de
overgeslagen rijen en waarom, en pas na je bevestiging effectief invoeren.

### 9.2 Corrigeren

Vrijwel alles is achteraf aanpasbaar via de bewerkbare tabellen. Vier bijzondere
gevallen:

- **Verkeerde ticker**: gebruik `🔧 Ticker corrigeren` op de Activa-pagina, dan
  verhuist de historiek mee.
- **Aandelensplitsing**: registreer ze op de Activa-pagina; de transacties en kostbasis
  worden dan aangepast.
- **Verkeerde wisselkoers of TOB**: gebruik de herberekening op de Transacties-pagina,
  of pas de waarde handmatig aan (waarna herberekeningen die lijn met rust laten).
- **Effect zonder koers**: stel een handmatige koers in.

### 9.3 Exporteren

Elke tabel heeft rechtsboven een downloadicoon voor CSV. Voor een volledige back-up
kopieer je gewoon het databasebestand; zie hoofdstuk 11.

---

## 10. Ontwerpkeuzes

Dit hoofdstuk legt vast waarom de app werkt zoals ze werkt. Het is bedoeld voor later:
om te kunnen beoordelen of een verandering een verbetering is of het ongedaan maken van
een bewuste keuze.

### 10.1 SQLite als enige bron van waarheid

Eén bestand, geen server, geen migratieframework. Het schema evolueert via idempotente
controles bij het opstarten: bestaat een kolom niet, dan wordt ze toegevoegd. Daardoor
kan een oude database altijd door een nieuwe versie geopend worden zonder aparte
migratiestap, en is een back-up één bestand kopiëren.

De prijs is dat SQLite één schrijver verwacht. Twee instanties op dezelfde database
over een netwerkschijf is geen ondersteund scenario.

### 10.2 Alles in euro, met de koers van de dag bewaard

De alternatieven waren omrekenen op het moment van weergave (wat je kostbasis laat
bewegen met de wisselkoers, en dus historische cijfers laat veranderen) of in de
oorspronkelijke munt bewaren en pas bij de belastingberekening omrekenen (wat elke
optelling over munten heen onmogelijk maakt).

De gekozen weg legt de omrekening vast op het moment van de verrichting. Een boeking
uit 2023 blijft daarmee zeggen wat ze in 2023 zei.

Daaruit volgt de strengheid rond ontbrekende wisselkoersen. Een stille terugval op 1,0
is voor geen enkele munt verdedigbaar, en heeft in een eerdere versie geleid tot TOB
berekend op dollarbedragen. Liever een geweigerde invoer dan een fout cijfer.

### 10.3 FIFO per rekening, belasting per persoon

Dit lijkt tegenstrijdig maar volgt uit twee verschillende gebruikers van hetzelfde
cijfer. Je broker rapporteert per rekening; je aangifte is per persoon. De app doet
allebei: de loten worden per rekening bijgehouden, de vrijstelling wordt globaal
geteld. Filter je op rekening, dan verandert je positieoverzicht wel maar je
vrijstellingsteller niet.

### 10.4 Cash wordt afgeleid, niet geboekt

Een volwaardig dubbel boekhoudsysteem zou elke geldstroom expliciet laten boeken. Dat
is nauwkeuriger en veel meer werk, en het introduceert een tweede plek waar dezelfde
waarheid staat, met de bijhorende kans dat de twee uit elkaar lopen.

Daarom geef je enkel echte stortingen en opnames in. Aankopen, verkopen, dividenden en
kosten worden uit de bestaande records afgeleid. Een negatieve cash is dan geen fout
maar een signaal: er ontbreekt een storting.

Dat de post "Aankopen" ook TOB en kosten bevat, is om dezelfde reden bewust: dat is het
bedrag dat effectief van je rekening ging, en het reconcilieert exact met je
brokerafschrift.

### 10.5 Automatisch detecteren, handmatig toepassen

Splitsingen, tickerwijzigingen en naamsafwijkingen worden gedetecteerd en gemeld, maar
nooit automatisch doorgevoerd. Een split toepassen wijzigt je kostbasis, en dus je
belastbare meerwaarde. Zoiets hoort niet 's nachts te gebeuren zonder dat je het weet.

Dezelfde logica geldt voor de herberekeningen van TOB en dividendketens: eerst een
voorbeeld van wat zou wijzigen, dan pas uitvoeren, en handmatig ingestelde waarden
blijven altijd gespaard. Als jij een bedrag hebt overschreven, weet jij iets wat de app
niet weet.

### 10.6 De database als koersbron voor het scherm

De app had bij elke paginaweergave live koersen kunnen ophalen. Dat geeft de meest
actuele cijfers en een trage, kwetsbare interface: elke klik in Streamlit voert het
script opnieuw uit.

De gekozen splitsing (achtergrondproces schrijft, interface leest) maakt het scherm
vrijwel instant en werkt door als een bron tijdelijk onbereikbaar is. De prijs is dat
een koers tot vijf minuten oud kan zijn. Voor een portefeuillebeheerder is dat geen
bezwaar; voor een daghandelaar wel, maar die is de doelgroep niet.

### 10.7 De ISIN als sleutel naar de buitenwereld

Tickers zijn dubbelzinnig: hetzelfde aandeel heeft een ander symbool per beurs en per
databron, en symbolen wijzigen. De ISIN is uniek en stabiel. Daarom draait de
koersopzoeking op ISIN, met het gevonden Yahoo-symbool als cache op het activum.

De keten van bronnen loopt van snelste naar traagste. Bronnen die structureel
onbetrouwbaar bleken staan achteraan of zijn verdwenen. Een effect dat nergens
publiek genoteerd staat krijgt een handmatige koers: dat is geen tekortkoming van de
app maar een eigenschap van het product.

De faalgrens van tien pogingen bestaat omdat de logs anders volliepen met vijf
mislukte netwerkcalls per effect per vijf minuten, voor een koers die er toch niet is.

### 10.8 Fiscale parameters zijn instellingen, geen code

Tarieven, plafonds, vrijstellingen en bronbelastingen staan in de database, niet in de
broncode. Wetgeving verandert, en dan mag er geen nieuwe versie nodig zijn.

De bronbelastingtarieven gaan een stap verder en staan per jaar, met vooruit erven.
Een dividend uit 2026 moet berekend blijven volgens de tarieven van 2026, ook nadat een
verdrag in 2028 wijzigt.

### 10.9 Secties in plaats van tabbladen, filters die blijven

Streamlit voert bij elke interactie het volledige script opnieuw uit. Echte tabbladen
springen daardoor terug naar het eerste tabblad zodra je een filter aanpast, en
session_state overleeft geen herlaad van de pagina.

Beide zijn opgelost door de keuze in de database te bewaren. Het kost een schrijfactie
per wijziging, maar het maakt het verschil tussen een app die je gebruikt en een app
die je bij elke klik corrigeert.

### 10.10 Getallen tonen wat ze zijn

Bedragen blijven intern getallen en worden pas bij weergave opgemaakt. Daardoor sorteert
een klik op een kolomkop numeriek. Overbodige nullen achter de komma worden weggelaten:
100 euro en niet 100,00 euro. En overal maximaal twee decimalen, behalve waar meer
precisie echt nodig is, zoals wisselkoersen.

### 10.11 Uitleg in de app, niet enkel in de handleiding

Bijna elk scherm bevat een korte tekst die zegt wat je ziet en waarom. Dat is bewust
redundant met dit document. Een handleiding wordt gelezen bij het begin; het bijschrift
onder een tabel wordt gelezen op het moment dat de vraag opkomt.

### 10.12 Dezelfde codebase op twee platformen

De Windows-versie is geen fork. De Python-code bevat geen enkele afhankelijkheid van
Home Assistant, en de verschillen zitten volledig in de opstartlaag en één
omgevingsvariabele voor de datamap. Een fork zou betekenen dat elke correctie twee keer
gemaakt moet worden, en dat er na een halfjaar twee verschillende apps bestaan.

---

## 11. Onderhoud, back-up en probleemoplossing

### 11.1 Back-up

De volledige toestand zit in `portfolio.db` in je datamap. Dat ene bestand kopiëren is
een volledige back-up. Doe het bij voorkeur met de app gesloten; anders bestaan er ook
`-wal` en `-shm` bestanden die je mee moet nemen.

Waar die datamap staat:

| Omgeving | Pad |
|---|---|
| Home Assistant add-on | `/share/portfolio_tracker` |
| Windows | `%LOCALAPPDATA%\PortfolioTracker\data`, of wat je in `config.bat` instelde |

Terugzetten is het bestand terugkopiëren en de app starten. Het schema wordt bij het
opstarten automatisch bijgewerkt, dus een oudere back-up openen met een nieuwere versie
werkt.

### 11.2 Twee installaties, twee databases

Wil je een tweede portefeuille volledig gescheiden houden, geef die installatie dan een
eigen datamap. Dat is de bedoelde manier om met de Windows-versie een zuivere tweede
portefeuille te draaien.

Wat je niet moet doen: twee installaties op dezelfde database laten werken via een
netwerkschijf.

### 11.3 Veelvoorkomende situaties

**Een positie heeft geen koers.** Kijk eerst op `🩺 Status`, gebruik dan
`🔬 Bronnen diagnose` op de Activa-pagina. Werkt geen enkele bron, dan is een
handmatige koers het juiste antwoord. Gaf de app het op na tien pogingen, dan
heractiveer je het ophalen op dezelfde pagina.

**De TOB klopt niet met mijn afschrift.** Controleer eerst het type en het
ETF-subtype van het activum, en of het in België aangeboden wordt. Klopt dat, pas dan
de TOB handmatig aan; die aanpassing blijft daarna behouden.

**Mijn cash staat negatief.** Er ontbreken stortingen. Vul ze aan op de Cash-pagina.

**Het dashboard toont oude cijfers.** Er zit een cache van zestig seconden op.
Gebruik `Ververs prijzen` of Rerun in het menu rechtsboven.

**De AI antwoordt niet.** Controleer je API-sleutel, en of het luik ingeschakeld staat
in de instellingen. Was het antwoord afgekapt, dan meldt de app dat expliciet.

### 11.4 Bijwerken

Home Assistant: de nieuwe bestanden in de repo zetten en de add-on **herbouwen**, niet
herstarten. Een herstart alleen gebruikt de oude Docker-laag.

Windows: de nieuwe bestanden overschrijven en `start.bat` opnieuw draaien. Wijzigde
`requirements.txt`, draai dan eerst `setup.bat` opnieuw.

---

## 12. Bijlagen

### 12.1 Woordenlijst

| Term | Betekenis |
|---|---|
| TOB | taks op beursverrichtingen, bij aankoop en verkoop |
| RV | roerende voorheffing, de Belgische inhouding op dividenden |
| Bronbelasting | de buitenlandse inhouding voor een dividend je land uit gaat |
| FBB | forfaitair gedeelte buitenlandse belasting, recupereerbaar voor onder meer Franse aandelen |
| Fotomoment | de slotkoers van 31/12/2025 als fiscale instapprijs voor oudere stukken |
| FIFO | first in, first out: de oudste loten worden het eerst verkocht |
| Kostbasis | wat een positie je gekost heeft, inclusief eerdere aankopen volgens FIFO |
| Performance share | een toegekend in plaats van gekocht aandeel, belast bij toekenning |
| Vesting | het moment waarop een toegekend aandeel je toekomt |
| Ongerealiseerd | winst of verlies op een positie die je nog hebt |
| Gerealiseerd | winst of verlies op een positie die je verkocht hebt |

### 12.2 Bestandsindeling

| Bestand | Rol |
|---|---|
| `app.py` | de volledige webinterface |
| `database.py` | opslag, schema, migraties, statuscontroles |
| `belgian_tax.py` | FIFO, TOB, meerwaardebelasting, dividendketen |
| `market_data.py` | koersen, wisselkoersen, bronnen, FSMA-lijsten |
| `ai_advisor.py` | de OpenAI-integratie |
| `scheduler.py` | de geplande achtergrondtaken |
| `bulk_import.py` | de Excel-import |
| `config.yaml` | add-on-definitie en versienummer |
| `windows/` | de opstartlaag voor Windows |

### 12.3 Verder lezen

- `windows/INSTALL_WINDOWS.md` voor de installatie op Windows.
- `CHANGELOG.md` voor wat er per versie gewijzigd is en waarom.
