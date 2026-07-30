# Portfolio Tracker — documentatie

> **De volledige handleiding staat in de app zelf.** Start de add-on, klik op
> **OPEN WEB UI** en kies in het linkermenu **📖 Handleiding**. Daar vind je alle
> twaalf hoofdstukken, met een zoekveld en een keuzelijst per hoofdstuk.
>
> Waarom daar en niet hier: Home Assistant toont dit tekstbestand in zijn eigen
> scherm, waar links naar andere bestanden in de repository niet werken. De
> handleiding in de app hoort bovendien altijd bij de versie die je effectief
> draait, en ze werkt zonder internetverbinding.

---

## Wat deze add-on doet

Een zelfgehoste portefeuillebeheerder voor de Belgische particuliere belegger:

- **Transacties** met FIFO-kostbasis per rekening, in euro, met de wisselkoers van
  de transactiedatum voorgoed bewaard.
- **Belgische fiscaliteit**: beurstaks (TOB), roerende voorheffing, buitenlandse
  bronbelasting met FBB, en de meerwaardebelasting met fotomoment op 31/12/2025.
- **Dividenden** met de volledige keten van bruto tot netto, per rekening.
- **Cash** afgeleid uit je transacties, stortingen en opnames.
- **Koersen** automatisch elke vijf minuten, via Yahoo Finance, onvista, Euronext,
  Tradegate en Deutsche Börse, met de ISIN als sleutel.
- **AI-advies** over je eigen posities en over kansen in de bredere markt
  (optioneel, vereist een eigen OpenAI-sleutel).

## Installatie

1. Voeg deze repository toe onder **Instellingen → Add-ons → Add-on store →
   ⋮ → Repositories**.
2. Installeer **Portfolio Tracker** en start de add-on.
3. Klik op **OPEN WEB UI**.

De database komt in `/share/portfolio_tracker/portfolio.db` en blijft dus bewaard
bij een herinstallatie van de add-on.

## Eerste stappen

1. **⚙️ Instellingen → 🏦 Rekeningen** — voeg je effectenrekeningen toe
   (bv. Bolero, Degiro, Saxo).
2. **⚙️ Instellingen → 🔑 API-sleutel** — enkel als je de AI-functies wil gebruiken.
3. **🏢 Activa** — voeg je effecten toe. Vul het ticker in en klik op
   *🔍 Info ophalen*: naam, munt, type, beurs, ISIN en sector worden ingevuld.
4. **➕ Transacties** — voer je aankopen en verkopen in. Voor bestaande portefeuilles
   kan dat ook in bulk via Excel (**⚙️ Instellingen → 🗃️ Data**).
5. **💶 Cash** — voer je stortingen en opnames in, dan klopt je cashsaldo.

Uitgebreid stappenplan: hoofdstuk 2 van de handleiding in de app.

## Bijwerken

Na een nieuwe versie: **Herbouwen** (niet enkel herstarten). Door de laagcaching van
Docker pikt een gewone herstart de gewijzigde bestanden niet op.

## Belangrijk

- **De app heeft geen eigen login.** Ze draait via ingress en zit dus achter de
  aanmelding van Home Assistant. Er wordt bewust geen poort gepubliceerd: dat zou de
  app rechtstreeks op je thuisnetwerk zetten, buiten die aanmelding om, en dan kan
  iedereen op hetzelfde netwerk je portefeuille lezen én bewerken.
- **De OpenAI-sleutel** staat standaard in `portfolio.db`, in `/share` — waar ook
  andere add-ons bij kunnen. Wil je dat vermijden, zet dan de omgevingsvariabele
  `OPENAI_API_KEY`: die krijgt voorrang en houdt de sleutel buiten de database.
- **Draai nooit twee instanties tegen dezelfde database.** SQLite is niet gemaakt
  voor twee schrijvers; je riskeert gegevensverlies. Gebruik de add-on óf de
  Windows-versie, niet allebei op dezelfde databank.
- **Maak een back-up** van `/share/portfolio_tracker/` voor je een grote wijziging
  doorvoert. Hoofdstuk 11 van de handleiding beschrijft hoe.
- Deze app is een hulpmiddel voor je eigen administratie. Ze is **geen
  aangiftesoftware en geen beleggingsadvies**. Controleer fiscale cijfers voor je
  ze gebruikt.

## Hulp nodig?

Hoofdstuk 11.4 van de handleiding (**📖 Handleiding → 11. Onderhoud, back-up en
probleemoplossing**) behandelt de veelvoorkomende situaties: een positie zonder
koers, een TOB die niet klopt met je afschrift, een negatief cashsaldo, een AI die
niet antwoordt, en meer.

Voor koersproblemen is **🩺 Status** het beginpunt: die pagina toont verouderde
koersen, tickerwijzigingen, niet-geregistreerde splitsingen en naamsafwijkingen.
