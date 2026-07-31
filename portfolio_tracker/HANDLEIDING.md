# Portfolio Tracker - Handleiding

Versie 1.4.2

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

### 3.10 Werkgeversfondsen (FCPE): afgeleide koers, stockdividend en blokkering

Fondsen uit aandelenplannen van je werkgever — zoals de Amundi/ENGIE Link-fondsen
(Classic, Liberty, Multiple) — gedragen zich op drie punten anders dan gewone
effecten, en de app heeft voor elk punt een eigen bouwsteen.

**Ze noteren nergens.** Hun QS-ISIN staat bij geen enkele koersbron; Amundi
publiceert de waarde enkel op zijn eigen portaal. Maar de waarde ís een formule op
een gewoon beursgenoteerd aandeel. Koppel het fonds daarom aan een **onderliggende
waarde** via `🏢 Activa → Overzicht → 🧮 Afgeleide koers`:

    koers = basis + multiplicator × (koers onderliggend − referentiekoers)

Voor een 1:1-fonds (Classic, Liberty: één deelbewijs = één aandeel ENGIE) is dat
basis 0, multiplicator 1, referentie 0. Voor een hefboomfonds (Multiple) haal je de
parameters uit je plandocumentatie: het gegarandeerde bedrag per deelbewijs als
basis, de hefboomfactor als multiplicator, de referentiekoers van het plan, en de
ondergrens aangevinkt zodat de koers nooit onder de garantie zakt. Het onderliggende
activum moet in de app bestaan; heb je het losse aandeel niet in portefeuille, voeg
het dan gewoon toe zonder transacties. Vanaf dan volgen de actuele koers, het
dagresultaat, de koershistoriek én de fotomomentwaarde automatisch de onderliggende
waarde — zonder één netwerkcall voor het fonds zelf.

**Ze keren dividenden uit in deelbewijzen.** De kapitalisatie van het onderliggende
dividend is fiscaal gewoon een dividend (roerende voorheffing, €833-vrijstelling),
maar er komt geen cent cash binnen: je krijgt er stukken bij. Vink daarvoor in het
dividendformulier **📦 Uitgekeerd in aandelen** aan en geef het aantal toegekende
stukken en de waarde per stuk in. De app rekent de volledige fiscale keten, boekt
niets in het cash-grootboek, en maakt automatisch een gekoppelde aanwastransactie
aan: brutowaarde als kostbasis, geen cash, geen TOB, en desgewenst meteen
geblokkeerd.

**Delen ervan zijn nog geblokkeerd.** Geef een aankooplot een **'vrij vanaf'-datum**
mee (vinkje in het transactieformulier, kolom *Vrij vanaf* in de transactietabel, of
kolom `vrij_vanaf` in de bulk-import). Op de datum zelf telt het lot al als vrij. De
portefeuillepagina splitst elke positie dan in vrij en geblokkeerd (met de
eerstvolgende deblokkeringsdatum) en toont het geblokkeerde kapitaal onder de
totalen; het dashboard toont hetzelfde totaal naast de beschikbare cash. Het
verkoopformulier waarschuwt als een verkoop aan geblokkeerde stukken zou raken, maar
houdt je niet tegen — de app detecteert, jij beslist. Bij werkgeversplannen komen de
oudste toekenningen het eerst vrij, waardoor de deblokkeringsvolgorde vanzelf
samenvalt met de FIFO-volgorde van de verkopen.

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
slotkoers van gisteren.

De tabel bevat per positie:

| Kolom | Wat het is |
|---|---|
| Aantal | Het aantal stuks dat je nu aanhoudt |
| Gem. waarde (€) | Je gemiddelde aankoopwaarde per stuk (FIFO-kostbasis, in euro) |
| Vorige slot | De laatst vastgelegde koers van de vorige beursdag (native munt) |
| Referentie | De koers waartegen de dagwinst effectief gemeten wordt (native munt) |
| Koers nu | De actuele koers (native munt) |
| Δ vandaag (%) | Het verschil tussen 'Koers nu' en 'Referentie' |
| Dag-P/L (€) | De winst of het verlies van vandaag, in euro |
| Vandaag | 📥 bijgekocht, 📤 verkocht, 🔁 allebei — met de aantallen |
| Koers gewijzigd | Wanneer de koers voor het laatst *effectief veranderde* |

Let op het verschil tussen **Gem. waarde** en **Referentie**. De eerste is je
kostprijs over de hele looptijd van de positie en staat in euro; ze zegt hoe ver je
in het totaal boven of onder water staat. De tweede is enkel het startpunt van
vandaag en staat in de native munt.

**Transacties van vandaag tellen correct mee.** Koop je vandaag bij, dan mag de app
je voor die nieuwe stukken niet de beweging aanrekenen die vóór jouw aankoop
plaatsvond — die heb je nooit gemaakt. Daarom wordt het dagresultaat opgebouwd als
een kasstroomredenering:

```
dag-P/L = eindwaarde − beginwaarde − aankopen vandaag + verkopen vandaag
```

waarbij de beginwaarde het aantal stuks bij opening is, tegen de vorige slotkoers.
De kolom *Referentie* is het resultaat daarvan, herrekend naar één stuk: zonder
transacties valt ze samen met de vorige slotkoers, en anders is ze het gewogen
gemiddelde van die slotkoers en de prijs van elke transactie van vandaag. Dat werkt
ook bij **meerdere transacties op één dag**: elke aankoop telt aan zijn eigen prijs,
elke verkoop aan de zijne.

*Voorbeeld.* Je had 10 stuks, de vorige slotkoers was 100. Vandaag koop je er 5 bij
aan 110, en de koers staat nu op 120. Het dagresultaat is 250: de 10 oude stuks
deden 10 × 20 = 200, de 5 nieuwe deden 5 × 10 = 50. De referentie is
(10 × 100 + 5 × 110) ÷ 15 = 103,33.

Posities die je **vandaag volledig nieuw** opgebouwd hebt, verschijnen meteen in de
tabel: er is dan geen vorige slotkoers, dus je aankoopprijs is de referentie.
Posities zonder koershistoriek én zonder transactie van vandaag verschijnen pas na
een dag; ze worden onder de tabel opgesomd.

Het dagresultaat volgt de **rekeningfilter** bovenaan de pagina: filter je op één
rekening, dan tellen enkel de transacties van die rekening mee.

**Samenstelling.** Een taartdiagram dat je kunt omschakelen tussen huidige waarde en
geïnvesteerd kapitaal. Het verschil tussen beide vertelt welke posities zwaarder zijn
gaan wegen dan je inleg.

**Belasting van het jaar.** Je netto gerealiseerde resultaat, hoeveel vrijstelling je
verbruikt hebt en wat er eventueel verschuldigd is.

**AI-kooptips en gerealiseerde historiek** sluiten de pagina af.

### 5.2 💼 Portefeuille

De detailweergave van je posities, in deze volgorde: open posities, spreiding per
sector, totaal per activum, gerealiseerde historiek, AI-synthese en prijsgeschiedenis.

**Open posities** staat bovenaan en toont per effect het aantal, de gemiddelde
aankoopprijs, de huidige koers, de waarde, het resultaat, de sector en de ontvangen
dividenden.

> De kolom *Dividend* volgt de rekeningfilter. Had je hetzelfde aandeel op twee
> rekeningen en heb je er één verkocht, dan tellen enkel nog de dividenden van de
> rekening(en) die je geselecteerd hebt. Anders zou een gesloten positie dividenden
> blijven aanbrengen bij een positie waar ze niet bij horen.

**Spreiding per domein / sector** is een taartdiagram van de verdeling over sectoren,
met een tabel met de gewichten ernaast. Je kunt schakelen tussen huidige waarde en
geïnvesteerd kapitaal; het verschil laat zien welke sectoren zwaarder zijn gaan wegen
dan je oorspronkelijke inleg. Weegt één sector 40% of meer, dan verschijnt er een
opmerking over concentratierisico — dat is een vaststelling, geen advies.

Activa zonder toegewezen sector belanden samen onder *Niet toegewezen*, met een lijst
eronder zodat je weet welke dat zijn. Toewijzen doe je op de pagina Activa; zie
[5.5](#55--activa).

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

Bij het ophalen van de info wordt ook het **domein/sector** meegenomen. Yahoo
classificeert aandelen volgens een GICS-achtige indeling; de app vertaalt die naar de
Nederlandstalige rubriek en vult het veld alvast in. Je kunt de keuze altijd
overschrijven — jouw toewijzing heeft voorrang en wordt nooit door een automatische
overschreven.

**Overzicht.** Alle activa in een bewerkbare tabel, met een filter op naam of ticker.
Hier zitten ook de gereedschappen:

- De kolom **Sector** met een keuzelijst. `—` betekent nog niet toegewezen.
- `🏭 Sectoren beheren en in één keer ophalen`, zie hieronder.
- `📸 Fotomoment ophalen` voor de slotkoers van 31/12/2025.
- `🧮 Afgeleide koers` voor effecten zonder eigen notering waarvan de waarde een
  formule op een ander activum is (werkgeversfondsen/FCPE); zie
  [3.10](#310-werkgeversfondsen-fcpe-afgeleide-koers-stockdividend-en-blokkering).
- `🔬 Bronnen diagnose` als een koers niet gevonden wordt: dit test elke bron apart en
  toont wat er precies terugkomt.
- De FSMA-lijst van in België aangeboden fondsen, om het TOB-tarief van je fondsen
  correct te zetten. Let op: die lijsten bevatten namen en geen ISIN's, dus de
  koppeling gebeurt op naam en vraagt je bevestiging.
- `🔧 Ticker corrigeren` verhuist alle transacties, dividenden en koersen mee.
- Koersophaling opnieuw activeren voor effecten waarvoor de app het opgegeven had.

**Sectoren beheren.** Het blok `🏭 Sectoren beheren en in één keer ophalen` doet drie
dingen:

1. **De keuzelijst uitbreiden.** De app levert dertien rubrieken mee: de elf
   GICS-hoofdsectoren in het Nederlands, plus *Gediversifieerd (index/fonds)* en
   *Overige*. Je kunt er zelf rubrieken aan toevoegen, bijvoorbeeld *Defensie* of
   *Waterstof*, zonder dat er iets in de code moet veranderen.
2. **Rubrieken verwijderen.** Alleen rubrieken die aan géén enkel activum hangen
   kunnen weg. Zo kan een toewijzing nooit stilzwijgend verdwijnen doordat de lijst
   ingekort wordt. De tabel toont per rubriek hoeveel activa ze gebruiken.
3. **Sectoren online ophalen.** Vraagt per activum de sector op bij Yahoo Finance —
   eerst via het ticker, en anders via de ISIN, wat vaak wél lukt bij .BR-noteringen.
   Standaard worden enkel activa zónder sector ingevuld. Wil je ook eerder automatisch
   toegekende sectoren vernieuwen, dan vink je dat apart aan; sectoren die jíj gezet
   hebt blijven hoe dan ook ongemoeid.

Fondsen en trackers krijgen bij Yahoo meestal **geen** sector. Dat is geen fout: een
brede indextracker zit in alle sectoren tegelijk. Zet die op *Gediversifieerd
(index/fonds)*, anders lijkt je portefeuille geconcentreerder dan ze is.

**Splitsingen.** Een aandelensplitsing registreer je hier. De app past die niet
automatisch toe, ook al detecteert ze er een: dat zou je kostbasis wijzigen zonder je
medeweten. Pas na je bevestiging worden de transacties en de kostbasis aangepast.

### 5.6 ➕ Transacties

**Nieuwe transactie.** Het belangrijkste formulier van de app. Naast de gewone velden:

- **Eigen wisselkoers**: gebruik die van je brokerafschrift als je hem hebt. De TOB
  wordt meteen op die koers herberekend — de beurstaks is immers een percentage van
  de EUR-tegenwaarde, dus een andere koers betekent per definitie een ander bedrag.
- **TOB manueel aanpassen**: als je broker een ander bedrag aanrekende dan de
  berekening geeft. Een handmatig ingestelde TOB wordt door latere herberekeningen
  met rust gelaten. Wijzig je daarna nog de wisselkoers, dan volgt het TOB-veld niet
  meer mee — het is dan jouw waarde. De app toont in dat geval wat de berekening zou
  geven, zodat je bewust kunt kiezen.
- **Performance share**: voor toegekende in plaats van gekochte stukken.
- **🔒 (Nog) niet vrij verhandelbaar**: geef een aankooplot een 'vrij vanaf'-datum
  mee (werkgeversplannen/FCPE). Het lot telt tot die datum als geblokkeerd kapitaal;
  zie [3.10](#310-werkgeversfondsen-fcpe-afgeleide-koers-stockdividend-en-blokkering).
  In de overzichtstabel is dit de kolom **Vrij vanaf** (JJJJ-MM-DD, leeg = nooit
  geblokkeerd).
- **Koersdoel**: optioneel, handmatig of via AI.

De app waarschuwt als ze de historische wisselkoers niet vindt, en weigert de
transactie als er helemaal geen koers beschikbaar is.

**Overzicht.** Bewerkbare tabel van alles wat je ingaf. Het blok
`🔄 TOB en EUR-tegenwaarde controleren` zoekt transacties waarvan de berekening niet
meer klopt, toont eerst wat er zou wijzigen, en voert pas uit na je expliciete
bevestiging.

Welke koers gebruikt de herberekening?

| Situatie | Wisselkoers | TOB |
|---|---|---|
| Gewone lijn | De historische marktkoers van de transactiedatum | Herberekend |
| Eigen wisselkoers (`FX eigen`) | **Jouw** koers blijft behouden | Herberekend op jouw koers, met 💱 gemarkeerd |
| Handmatige TOB (`TOB eigen`) | Ongemoeid | Ongemoeid |
| Toekenning (performance share) | Ongemoeid | Geen TOB van toepassing |

Lijnen met een eigen wisselkoers werden vroeger volledig overgeslagen. De bedoeling
was jouw koers te beschermen, maar daardoor werd ook de TOB nooit meer nagekeken.
Nu blijft de koers even goed beschermd, maar wordt de beurstaks er wél op hertekend.

Een 🚩 in de tabel betekent dat de opgeslagen TOB exact overeenkomt met het tarief
toegepast op het bedrag in **vreemde munt**. Dat is de oude fout uit versies waarin
de wisselkoers stilzwijgend op 1,0 kon blijven staan.

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

**Uitgekeerd in aandelen (stockdividend).** Voor kapitalisaties die als extra stukken
worden toegekend in plaats van cash (bv. FCPE-werkgeversfondsen): vink
**📦 Uitgekeerd in aandelen** aan en geef het aantal stukken en de waarde per stuk in.
De fiscale keten loopt zoals bij elk dividend, maar er wordt niets in het
cash-grootboek geboekt en er verschijnt automatisch een gekoppelde aanwastransactie
(brutowaarde als kostbasis, geen cash, geen TOB, desgewenst meteen geblokkeerd). Zie
[3.10](#310-werkgeversfondsen-fcpe-afgeleide-koers-stockdividend-en-blokkering).

**Eigen wisselkoers.** Keert een aandeel uit in een vreemde munt, dan rekent je broker
om tegen *zijn* koers — vaak met een wisselmarge erin verwerkt. Vink
**💱 Eigen wisselkoers gebruiken** aan en vul de koers van je afschrift in; de app
toont meteen hoeveel die afwijkt van de marktkoers van die dag. Die koers blijft
daarna voorgoed bij de lijn hangen: geen enkele herberekening vervangt ze nog door de
marktkoers. Precies dezelfde werking als bij transacties.

> In de gedetailleerde invoer geldt één eigen koers voor de hele keten. Staan er
> uitzonderlijk twee verschillende vreemde munten in dezelfde keten, dan zegt de app
> dat één koers daar niet voor kan gelden — voer zulke gevallen beter als aparte
> lijnen in.

**Overzicht** toont alle inkomsten in een bewerkbare tabel, met bovenaan hoeveel je via
je aangifte fiscaal kunt recupereren. De kolommen **FX-koers** en **FX eigen** werken
zoals bij transacties: pas je de koers aan, dan wordt het vinkje automatisch gezet.

De **herberekening** werkt zoals bij transacties: eerst een voorbeeld van wat zou
wijzigen, dan pas uitvoeren.

| Situatie | Wisselkoers | Bedragen |
|---|---|---|
| Gewone lijn | De historische marktkoers van de dividenddatum | Herberekend |
| Eigen wisselkoers (💱) | **Jouw** koers blijft behouden | Herberekend op jouw koers |
| Handmatig gecorrigeerd (🔒) | Ongemoeid | Ongemoeid, tenzij je uitdrukkelijk kiest voor overschrijven |

Let op het verschil tussen de twee markeringen. 🔒 betekent dat je de **bedragen** hebt
aangepast en dat de hele lijn met rust gelaten wordt. 💱 betekent enkel dat de
**koers** van jou is: de bedragen worden dan wél netjes herrekend. Beschermd tegen
overschrijven is niet hetzelfde als uitgesloten van controle.

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

**Twee knoppen per melding.**

- `✓ Gezien` verplaatst de melding naar het **archief** onderaan de pagina, een blok
  dat standaard dichtgeklapt staat. De melding blijft bestaan — de toestand is
  immers niet opgelost — maar ze verdringt de openstaande punten niet meer. Dat is
  vooral nuttig voor een gedetecteerde splitsing die je bewust *niet* registreert,
  bijvoorbeeld omdat je broker de stukken al aangepast heeft. Zonder archief zou die
  melding elke dag opnieuw bovenaan staan.
- `Sluiten` laat de melding helemaal verdwijnen. Blijft de toestand bestaan, dan
  komt ze bij de volgende controle terug.

Splitsingen worden gemeld maar nooit automatisch toegepast. Verder staan hier twee
diagnosegereedschappen voor de Euronext-bron.

**Sluitingsdagen geven geen valse waarschuwingen.** De achtergrondplanner haalt élke
vijf minuten koersen op, ook in het weekend en op feestdagen. Op zo'n dag levert
iedere bron netjes dezelfde slotkoers terug — en dan lijkt het alsof de koers "niet
beweegt", terwijl er gewoon niet gehandeld werd. De app houdt daarom een beurskalender
bij:

| Markt | Sluitingsdagen |
|---|---|
| Euronext en Xetra | Nieuwjaar, Goede Vrijdag, Paasmaandag, 1 mei, Kerstmis, tweede kerstdag |
| NYSE en Nasdaq | Nieuwjaar, MLK Day, Washington's Birthday, Goede Vrijdag, Memorial Day, Juneteenth, 4 juli, Labor Day, Thanksgiving, Kerstmis |

Voor Amerikaanse feestdagen geldt de *observed*-regel: valt een vaste feestdag op
zaterdag, dan sluit de beurs de vrijdag ervoor; valt ze op zondag, dan de maandag
erna. Welke kalender voor een activum geldt, leidt de app af uit de beurs, het
beurssuffix in het ticker en de munt. Bij twijfel geldt de Europese kalender, want
dan wordt er hooguit één dag te weinig als sluitingsdag gezien.

Dat werkt op twee plaatsen door:

- **Geen koersbeweging** wordt enkel nog gemeld voor dagen waarop de beurs voor dát
  activum effectief open was.
- **Verouderde koers** telt de leeftijd in *beursdagen* in plaats van kalenderdagen.
  Een lang kerstweekend levert dus geen golf waarschuwingen meer op.

Daarbovenop staat een marktbrede terugval. Staan **alle** activa van eenzelfde markt
(vanaf drie stuks) op dezelfde dag stil, dan lag de handel stil: dat is een
marktfeit, geen datafout, en de melding wordt onderdrukt. Zo vangt de app ook
sluitingen op die de kalender niet kent — 21 juli in Brussel, of een halve
handelsdag op kerstavond.

De kalender wordt volledig **offline** berekend. Een beurskalender-API zou een extra
afhankelijkheid, een extra faalpunt en een netwerkcall per controle betekenen, voor
gegevens die jaren vooruit exact berekenbaar zijn: de feestdagen liggen vast en
Pasen volgt uit een formule van een paar regels.

### 5.12 ⚙️ Instellingen

Zes secties.

**🔑 API-sleutel.** Je OpenAI-sleutel, welk model elk van de drie AI-taken gebruikt,
een kostenraming per model, je geschatte investeringsvolume, en de privacymodus.

**🏦 Rekeningen.** Je rekeningen en hun beleggingsprofiel.

**🏭 Sectoren.** De volledige beheerplek voor de domeinen/sectoren die het
taartdiagram *Spreiding per domein* voeden. Vijf blokken:

1. **Kerncijfers** — hoeveel rubrieken er zijn, hoeveel activa er een sector hebben,
   en hoeveel er nog niet toegewezen zijn.
2. **Rubriek toevoegen** — de app levert de elf GICS-hoofdsectoren mee, aangevuld met
   *Gediversifieerd (index/fonds)* en *Overige*. Voeg toe wat je nodig hebt, bv.
   *Defensie* of *Waterstof*.
3. **Rubriek hernoemen** — zet de naam in één keer om in de lijst **én** op elk
   activum dat ze gebruikt. Zonder deze knop zou hernoemen betekenen: nieuwe rubriek
   maken, elk activum apart omzetten en de oude weggooien — waarbij één vergeten
   activum al genoeg is om je taart twee bijna-identieke punten te geven.
4. **De lijst + verwijderen** — met per rubriek hoeveel activa ze gebruiken en of ze
   standaard of eigen is. Alleen ongebruikte rubrieken kunnen weg; zo verdwijnt een
   toewijzing nooit stilzwijgend.
5. **Toewijzen in bulk** — een tabel met al je activa en een vinkje *toon enkel activa
   zonder sector*, zodat je de gaten in één beweging kunt vullen. Sneller dan activum
   per activum via de Activa-pagina.
6. **Online ophalen** — vraagt de sector op bij Yahoo Finance (via het ticker, en
   anders via de ISIN) en vertaalt ze naar je rubrieken. Standaard worden enkel activa
   zónder sector ingevuld; wat jíj hebt toegewezen blijft hoe dan ook ongemoeid.

Op de Activa-pagina blijft de kolom *Sector* staan voor losse correcties, met een knop
die rechtstreeks naar deze sectie springt.

**🧾 Meerwaardebelasting.** Tarief, jaarlijkse vrijstelling en je huwelijksstelsel.

**🏛️ TOB & bronbelasting.** De TOB-tarieven en -plafonds per producttype, het
tarief roerende voorheffing, en de buitenlandse bronbelasting per land **per jaar**.
Die jaartabellen erven vooruit: stel je 2026 in, dan geldt dat ook voor 2027 en later,
tot je voor een later jaar iets anders instelt. Zo blijven oude dividenden berekend
volgens de tarieven die toen golden.

**🗃️ Data.** Bulk-import via Excel, koersen handmatig ophalen, en het overzicht van de
EUR-omrekening.

### 5.13 📖 Handleiding

Deze handleiding, in de app zelf. Ook de changelog, de Windows-installatie en de
README staan er, elk met een zoekveld en een keuzelijst per hoofdstuk. Onderaan kun je
het document downloaden.

**Waarom in de app.** Home Assistant toont het README-bestand van een add-on in zijn
eigen scherm, en daar werkt een verwijzing naar een ander bestand in de repository
niet: klikken doet gewoon niets. De documentatie meeleveren in de app lost dat op en
heeft twee bijkomende voordelen. Ze werkt zonder internetverbinding, en ze hoort
altijd bij de versie die je effectief draait — een handleiding op GitHub loopt voor op
een add-on die je nog niet herbouwd hebt.

De bestanden worden gelezen van de schijf naast de code (`/app` in de container). Zie
je hier een melding dat een bestand ontbreekt, dan is de installatie onvolledig:
herbouw de add-on, en herstart ze niet enkel.

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

Twee regels bewaken de bruikbaarheid van die ideeën:

- **Minstens één niet-Amerikaanse naam per categorie.** Dat staat als harde
  voorwaarde in de opdracht aan het model, met de reden erbij: een portefeuille die
  enkel Amerikaanse namen voorgeschoteld krijgt, bouwt ongemerkt een dollar- en
  concentratierisico op. Niet-Amerikaanse noteringen zijn met 🌍 gemarkeerd. Houdt
  het model zich er in een categorie tóch niet aan, dan wordt dat gemeld in plaats
  van stilgezwegen — de ideeën weggooien zou een lege categorie opleveren, en dat is
  erger dan een eerlijke waarschuwing.
- **Aandelen die je al bezit vallen weg.** Een koopidee voor een positie die al in de
  portefeuille zit, is geen idee maar ruis, en het verdringt een suggestie die je wél
  iets bijbrengt. Ze worden geweerd bij het opslaan én bij het weergeven — dus ook een
  aandeel dat je pas *na* het advies gekocht hebt, verdwijnt uit de lijst en uit de
  opvolgingstabel. De vergelijking gebeurt op ticker, ISIN en basissymbool (het stuk
  vóór het beurssuffix), zodat BMW.DE en BMW.F als hetzelfde bedrijf gelden.

De koers van elk voorgesteld aandeel wordt daarna ongeveer honderd dagen opgevolgd, zodat
je achteraf kunt zien of de suggesties iets waard waren. De historiek blijft altijd in
de database staan; het wegfilteren gebeurt enkel in de weergave.

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

### 10.13 Het dagresultaat is een kasstroom, geen koersverschil

De voor de hand liggende formule voor een dagresultaat is
`(koers nu − vorige slotkoers) × aantal`. Die is fout zodra je op dezelfde dag koopt
of verkoopt: voor de stukken die je vandaag pas verworven hebt, rekent ze ook de
beweging aan die vóór jouw aankoop plaatsvond. Bij een aandeel dat 's ochtends 3%
steeg en dat je 's middags kocht, zou de app je die 3% cadeau doen.

Daarom wordt het dagresultaat opgebouwd als een kasstroomredenering: eindwaarde min
beginwaarde, gecorrigeerd voor alles wat er die dag in of uit ging. Die vorm heeft
een eigenschap die de eenvoudige formule mist — ze klopt automatisch bij een
willekeurig aantal transacties op één dag, elk tegen zijn eigen prijs, zonder dat er
een speciaal geval bijgeschreven moet worden.

De prijs is dat de kolom *Referentie* geen echte koers meer is maar een gewogen
gemiddelde. Dat is bewust zichtbaar gemaakt in een aparte kolom naast *Vorige slot*,
in plaats van stilzwijgend een ander getal onder dezelfde kolomtitel te zetten.

### 10.14 De sectorlijst staat in de database, niet in de code

Sectoren hadden een aparte tabel met een vreemde sleutel kunnen zijn. In plaats
daarvan is het een tekstveld op het activum, met een keuzelijst ernaast die als
instelling bewaard wordt. Dat is dezelfde redenering als bij de fiscale parameters
(zie 10.8): je kunt een rubriek toevoegen of hernoemen zonder migratie en zonder
nieuwe versie.

Het heeft ook een praktisch voordeel. Een activum met een rubriek die niet meer in de
lijst staat, blijft gewoon bestaan met zijn toewijzing intact — bij een vreemde
sleutel zou dat een gebroken verwijzing zijn. De keuzelijst vult zichzelf zelfs weer
aan met rubrieken die nog in gebruik zijn, zodat een toewijzing nooit uit beeld
verdwijnt. Om diezelfde reden kan een rubriek die nog gebruikt wordt niet verwijderd
worden.

De automatische toewijzing en de jouwe worden apart bijgehouden (`sector_source`),
zodat een online ophaalronde nooit jouw keuze overschrijft. Hetzelfde principe als
bij de eigen wisselkoers en de handmatige TOB: wat jij expliciet gezet hebt, wint.

### 10.15 Beschermen mag niet betekenen: niet meer nakijken

De TOB-controle sloeg transacties met een eigen wisselkoers volledig over. De
bedoeling was goed — die koers komt van je brokerafschrift en mag nooit door een
marktkoers vervangen worden — maar het gevolg was dat de beurstaks op die lijnen ook
nooit meer nagekeken werd. En de TOB is een percentage van de EUR-tegenwaarde, dus
ze beweegt per definitie mee met de koers.

De les die hier vastligt: "beschermd tegen overschrijven" en "uitgesloten van
controle" zijn twee verschillende dingen, en ze mogen niet met één vinkje geregeld
worden. De koers blijft nu beschermd, de afgeleide berekening wordt wél hertekend.

Diezelfde vraag is daarna gesteld bij de **dividenden**, waar een eigen wisselkoers
sindsdien op precies dezelfde manier werkt: jouw koers blijft, de bedragen en hun
EUR-tegenwaarde worden herrekend. Daar is het onderscheid ook zichtbaar gemaakt in de
markering — 🔒 voor "de bedragen zijn van mij, blijf van deze lijn" en 💱 voor "enkel
de koers is van mij". Twee verschillende beloftes verdienen twee verschillende
symbolen.

### 10.16 Documentatie hoort bij de versie, niet bij de repository

De handleiding stond in de repository, met een link vanuit het README-bestand. In Home
Assistant deed die link niets: HA rendert markdown in zijn eigen frontend, waar een
relatief pad naar een ander bestand nergens naartoe wijst.

Absolute links naar GitHub lossen het klikprobleem op, maar niet het echte probleem.
Een handleiding op GitHub beschrijft de nieuwste versie, terwijl jij misschien nog een
oudere draait — en ze werkt niet als je add-on geen internet heeft. Daarom staat de
documentatie nu ook **in de app**, gelezen van de schijf naast de code. Ze is per
definitie de handleiding van de versie die je op dat moment gebruikt.

De drie plaatsen vullen elkaar aan: `DOCS.md` is de korte versie voor het
Documentatie-tabblad van HA, `README.md` bevat de absolute links voor wie op GitHub
kijkt, en de pagina **📖 Handleiding** is de volledige tekst voor wie de app openheeft.

Bij het opzoeken van de juiste URL's kwam nog een tweede fout boven. De README in de
repository-root was een kopie van de add-on-README, inclusief haar relatieve links naar
`HANDLEIDING.md` — maar dat bestand staat in `portfolio_tracker/`. Vanuit de root gaven
die links dus een 404, ook op GitHub zelf. Twee bestanden met dezelfde inhoud op twee
verschillende plaatsen in de boom kunnen niet allebei kloppen met relatieve paden; ze
hebben nu elk hun eigen rol, en absolute links.

De links wijzen naar `/blob/HEAD/` en niet naar `/blob/main/`. HEAD volgt de
standaardbranch, dus ze blijven werken als die ooit hernoemd wordt.

### 10.17 De beurskalender wordt berekend, niet opgehaald

Weekends en feestdagen zijn de reden dat koersen stilstaan, en dat mag geen
waarschuwing geven. De voor de hand liggende oplossing is een beurskalender-API, maar
dat betekent een extra afhankelijkheid, een extra faalpunt en een netwerkcall bij elke
controle — voor gegevens die jaren vooruit exact berekenbaar zijn.

De vaste feestdagen liggen vast, en Pasen volgt uit de anonieme Gregoriaanse formule
van een paar regels. Het enige wat niet berekenbaar is, zijn lokale of onverwachte
sluitingen. Daarvoor is er een tweede, empirische controle: staan álle activa van
eenzelfde markt op dezelfde dag stil, dan lag de handel stil. Die redenering heeft
geen kalender nodig en dekt automatisch elke sluiting die niemand voorzien had.

---

## 11. Onderhoud, back-up en probleemoplossing

### 11.1 Toegang en veiligheid

De app heeft **geen eigen login**. Wie de pagina kan openen, kan alles zien en wijzigen.
Dat is een bewuste keuze — het is een persoonlijk instrument op je eigen hardware — maar
het betekent dat de toegang van buitenaf geregeld moet zijn.

**Home Assistant.** De add-on draait via *ingress*: je opent hem vanuit het HA-paneel en
je bent dus al aangemeld bij Home Assistant. Er wordt bewust **geen poort gepubliceerd**.
Een `ports:`-blok in `config.yaml` zou de app rechtstreeks op je thuisnetwerk zetten,
buiten die aanmelding om — dan kan iedereen op hetzelfde netwerk je portefeuille lezen
en bewerken. Voeg zo'n poort alleen toe als je precies weet waarom, en zet er dan zelf
iets voor.

**Windows.** `config.bat` zet `BIND_ADDRESS` standaard op `127.0.0.1`: alleen bereikbaar
op die PC. Zet je dat op `0.0.0.0` om vanaf je telefoon te kijken, dan geldt hetzelfde
voorbehoud — iedereen op je netwerk kan dan mee. Stel de app nooit rechtstreeks open op
het internet via een poortdoorschakeling.

**De OpenAI-sleutel.** Die wordt na het opslaan niet meer teruggetoond: je ziet alleen
nog een herkenningsvorm zoals `sk-pro••••••••••••abcd`. Het invoerveld leeg laten
betekent "ongewijzigd".

Er zijn drie plekken waar de sleutel kan staan, in volgorde van veiligheid:

| Plek | Wie kan erbij | Aanrader |
|---|---|---|
| Add-on-configuratie (HA) of `config.bat` (Windows) | alleen deze add-on / deze PC | ✅ beste keuze |
| Omgevingsvariabele `OPENAI_API_KEY` | het proces zelf | ✅ gelijkwaardig |
| Instellingen in de app (`portfolio.db`) | elke add-on die bij `/share` kan | ⚠️ standaard, minder afgeschermd |

De eerste twee komen op hetzelfde neer: de add-on-configuratie wordt door `run.sh`
omgezet in die omgevingsvariabele. Staat er een sleutel in de omgeving, dan krijgt die
altijd voorrang op wat in de app is opgeslagen, en zegt de instellingenpagina dat ook.
Het stappenplan om over te schakelen staat hieronder.

### 11.2 De API-sleutel afschermen — stap voor stap

Vijf minuten werk. Sla dit over als je de AI-functies niet gebruikt.

**Home Assistant**

1. Open **Instellingen → Add-ons → Portfolio Tracker** en ga naar het tabblad
   **Configuratie**.
2. Plak je sleutel in het veld **openai_api_key**. Home Assistant toont dat veld
   gemaskeerd, want het is als wachtwoordveld gedefinieerd.
3. Klik **Opslaan**. Home Assistant vraagt om de add-on te herstarten — doe dat.
4. Open de app en ga naar **⚙️ Instellingen → 🔑 API-sleutel**. Staat er een blauw
   bericht *"Er staat een sleutel in de omgevingsvariabele OPENAI_API_KEY"*, dan werkt
   het.
5. Controleer dat de AI ook echt antwoordt: klik op **🤖 Bepaal via AI** bij een
   activum, of genereer een advies op de portefeuillepagina.
6. **Pas daarna** wis je de oude sleutel uit de database, met de knop
   **🗑️ Verwijderen** naast de gemaskeerde sleutel. Niet eerder — anders sta je zonder
   werkende sleutel als er in stap 3 iets misging.

**Windows**

1. Open `config.bat` (of `config.local.bat`) in Kladblok.
2. Voeg onderaan een regel toe: `set "OPENAI_API_KEY=sk-jouw-sleutel"`
3. Bewaar en start de app opnieuw met `start.bat`.
4. Volg dan stap 4 tot en met 6 hierboven.

> Zet `config.bat` met je sleutel erin niet in een publieke Git-repository. Gebruik
> `config.local.bat`, dat niet mee gecommit wordt.

**Waarom dit uitmaakt.** De database staat bij Home Assistant in `/share`. Die map is
gedeeld: elke andere add-on die je installeert, kan er in principe in lezen. Een
API-sleutel is geld — wie hem heeft, verbruikt op jouw rekening. De add-on-configuratie
zit daarentegen in de privéopslag van deze add-on.

**Vermoed je dat de sleutel gelekt is?** Ga naar `platform.openai.com/api-keys`,
verwijder de oude sleutel daar en maak een nieuwe aan. Dat is het enige wat echt
afdoende is; hem uit de app halen volstaat niet, want een kopie werkt gewoon verder.

### 11.3 Back-up en herstel

De volledige toestand zit in één bestand, `portfolio.db`, in je datamap:

| Omgeving | Pad |
|---|---|
| Home Assistant add-on | `/share/portfolio_tracker` |
| Windows | `%LOCALAPPDATA%\PortfolioTracker\data`, of wat je in `config.bat` instelde |

De app maakt daar zelf kopieën van, in de submap `backups`. Je regelt alles via
`⚙️ Instellingen → 🗃️ Data → 💾 Back-up en herstel`.

**Wanneer er automatisch een kopie gemaakt wordt.** Elke nacht om 02:30, én telkens
wanneer de app start. Dat tweede moment is het belangrijkste: het gebeurt vlak vóór
een nieuwe versie de database bijwerkt, dus precies wanneer je terug zou willen kunnen.
Je stelt in hoeveel kopieën bewaard blijven (standaard veertien); de oudste worden
opgeruimd, zodat je datamap niet volloopt.

**Waarom geen gewone bestandskopie.** De app gebruikt WAL-journaling: de recentste
wijzigingen staan tijdelijk in een apart `-wal`-bestand. Kopieer je `portfolio.db`
terwijl de app draait, dan mis je die wijzigingen, of erger, je vangt een halve
transactie. De app gebruikt daarom `VACUUM INTO`: SQLite schrijft zelf een consistente,
compacte kopie weg terwijl alles gewoon doordraait. Het resultaat is één bestand dat je
meteen kunt openen — geen losse `-wal` of `-shm` nodig.

**Kopieën van de server af halen.** Met de knop `⬇️` download je een back-up naar je PC
of telefoon. Doe dat af en toe: een back-up die naast het origineel staat, helpt je niet
wanneer de schijf van je server het begeeft. Vijftien seconden werk, en het is het enige
wat je beschermt tegen hardwarepech.

**Herstellen.** Onder `♻️ Herstellen vanaf een back-up` kies je een bewaarde kopie, of
je uploadt een bestand dat je eerder gedownload hebt. De app controleert eerst of het
wel een geldige portfolio-database is, toont hoeveel activa, transacties en dividenden
erin zitten naast wat je nu hebt, en vraagt om een expliciete bevestiging. Vóór het
overschrijven maakt ze automatisch een veiligheidskopie van je huidige toestand
(`voor-herstel`), zodat ook een verkeerd herstel terug te draaien is.

> **Herstart de add-on na een herstel.** De draaiende app en de achtergrondplanner
> hebben de oude database nog open. Zonder herstart kan je een mengeling van beide te
> zien krijgen.

Een oudere back-up openen met een nieuwere versie van de app werkt: het schema wordt
bij het opstarten automatisch bijgewerkt.

### 11.4 Twee installaties, twee databases

Wil je een tweede portefeuille volledig gescheiden houden, geef die installatie dan een
eigen datamap. Dat is de bedoelde manier om met de Windows-versie een zuivere tweede
portefeuille te draaien.

Wat je niet moet doen: twee installaties op dezelfde database laten werken via een
netwerkschijf.

### 11.5 Veelvoorkomende situaties

**Een positie heeft geen koers.** Kijk eerst op `🩺 Status`, gebruik dan
`🔬 Bronnen diagnose` op de Activa-pagina. Werkt geen enkele bron, dan is een
handmatige koers het juiste antwoord. Gaf de app het op na tien pogingen, dan
heractiveer je het ophalen op dezelfde pagina.

**De TOB klopt niet met mijn afschrift.** Controleer in deze volgorde:

1. Het **type** en het **ETF-subtype** van het activum, en of het in België aangeboden
   wordt (het BE-vinkje). Die drie bepalen samen het tarief.
2. De **EUR-tegenwaarde**. De TOB is een percentage daarvan, dus een verkeerde
   wisselkoers geeft altijd een verkeerde TOB. Draai `🔄 TOB en EUR-tegenwaarde
   controleren` op de Transacties-pagina: die toont eerst wat er zou wijzigen.
3. Klopt alles en rekende je broker toch iets anders aan, pas de TOB dan handmatig
   aan. Die aanpassing blijft daarna behouden.

**Ik heb mijn eigen wisselkoers aangepast, maar de TOB bleef gelijk.** Dat gebeurde in
versies vóór 1.1.0: lijnen met een eigen koers werden bij de herberekening volledig
overgeslagen. Draai de TOB-controle nu opnieuw — lijnen met een eigen koers zijn er
met 💱 gemarkeerd, en hun TOB wordt herrekend terwijl jouw koers behouden blijft.
Staat er ook `TOB eigen` aan, dan blijft de lijn wél ongemoeid: zet dat vinkje eerst
uit als je de berekende waarde wil.

**Mijn dividenden kloppen niet bij een gefilterde rekening.** Sinds 1.1.0 volgt de
kolom *Dividend* in de tabel met open posities de rekeningfilter. Zie je nog oude
cijfers, ververs dan de pagina; er zit zestig seconden cache op.

**Een aandeel staat op 0% dagwinst.** Kijk naar de kolom *Koers gewijzigd*. Is die
recent, dan is 0% normaal — de markt was gesloten of de koers bewoog echt niet. Staat
ze dagen terug terwijl de beurs open was, dan verschijnt er een waarschuwing op de
statuspagina.

**De statuspagina meldt 'geen koersbeweging' op een feestdag.** Dat hoort niet meer te
gebeuren sinds 1.1.0. Gaat het om een lokale sluitingsdag die de kalender niet kent
(21 juli bijvoorbeeld) en heb je minder dan drie activa op die markt, dan kan de
marktbrede terugval niet werken — vink de melding dan af met `✓ Gezien`, zodat ze in
het archief belandt.

**Mijn sectordiagram zit vol 'Niet toegewezen'.** Ga naar
`⚙️ Instellingen → 🏭 Sectoren` en klik op `🔎 Ophalen`. Wat daarna nog leeg blijft,
zijn meestal fondsen en trackers: die krijgen bij de bron geen sector. Vul die in het
blok *Sectoren toewijzen* in, met het vinkje *toon enkel activa zonder sector* aan —
dan zie je precies de gaten.

**Mijn dividend in dollar klopt niet met mijn afschrift.** Je broker rekende
waarschijnlijk om tegen zijn eigen koers, inclusief wisselmarge. Vink bij het invoeren
`💱 Eigen wisselkoers gebruiken` aan, of zet de koers achteraf in de kolom *FX-koers*
in het overzicht — het vinkje *FX eigen* gaat dan automatisch aan. Vanaf dan blijft
jouw koers behouden bij elke herberekening.

**Ik klik in Home Assistant op HANDLEIDING.md en er gebeurt niets.** Dat klopt voor
versies vóór 1.2.0: HA toont dat bestand in zijn eigen scherm, waar een relatieve
verwijzing naar een ander bestand in de repository niet werkt. Sinds 1.2.0 zijn die
links absoluut. Maar het eenvoudigste blijft: open de app en kies **📖 Handleiding**
in het linkermenu. Daar staat dezelfde tekst, doorzoekbaar, zonder internetverbinding,
en horend bij precies de versie die je draait.

**Mijn cash staat negatief.** Er ontbreken stortingen. Vul ze aan op de Cash-pagina.

**Het dashboard toont oude cijfers.** Er zit een cache van zestig seconden op.
Gebruik `Ververs prijzen` of Rerun in het menu rechtsboven.

**De AI antwoordt niet.** Controleer je API-sleutel, en of het luik ingeschakeld staat
in de instellingen. Was het antwoord afgekapt, dan meldt de app dat expliciet.

### 11.6 Bijwerken

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
| Referentiekoers | het startpunt van het dagresultaat: de vorige slotkoers, gewogen met je transacties van vandaag |
| GICS | de internationale sectorindeling die Yahoo en de meeste fondsbeheerders gebruiken |
| Sector | het domein waarin een activum actief is, bepalend voor de spreidingsanalyse |
| Beursdag | een dag waarop de betrokken beurs open was: geen weekend, geen feestdag |
| Observed | de Amerikaanse regel die een feestdag in het weekend naar de vrijdag of maandag verschuift |
| Basissymbool | het deel van een ticker vóór het beurssuffix (BMW.DE → BMW) |
| Eigen wisselkoers | de koers die je broker effectief gebruikte, bewaard bij de lijn en nooit door de marktkoers vervangen |
| Wisselmarge | het verschil tussen de brokerkoers en de marktkoers, vaak al in de koers verwerkt (auto-FX) |

### 12.2 Bestandsindeling

De repository is een **Home Assistant add-on-repository**: de add-on zelf zit in de map
`portfolio_tracker/`, met daarnaast een `repository.yaml` en een README in de root die
beschrijven hoe je de repository aan Home Assistant toevoegt.

```
repository.yaml          definitie van de add-on-repository
README.md                hoe je de repository toevoegt, wat erin zit
portfolio_tracker/       de add-on zelf (alles hieronder)
```

Binnen `portfolio_tracker/`:

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
| `HANDLEIDING.md` | dit document, ook getoond op de pagina 📖 Handleiding |
| `DOCS.md` | de korte versie voor het Documentatie-tabblad van Home Assistant |
| `README.md` | kennismaking en links, voor wie op GitHub kijkt |
| `CHANGELOG.md` | wat er per versie veranderd is, en waarom |
| `windows/` | de opstartlaag voor Windows |

### 12.3 Verder lezen

- `windows/INSTALL_WINDOWS.md` voor de installatie op Windows.
- `CHANGELOG.md` voor wat er per versie gewijzigd is en waarom.
