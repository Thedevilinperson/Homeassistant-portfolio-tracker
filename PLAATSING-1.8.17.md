# Plaatsing 1.8.17

Fonds transfereren: een nieuwe sectie op de Transacties-pagina voor een
fondsfusie of klasse-omzetting (bv. kapitalisatie → distributie van hetzelfde
fonds, of een ISIN-wijziging bij een fusie zoals bij het ENGIE-FCPE-fonds).
Economisch dezelfde belegging → geen verkoop, geen beurstaks, geen gerealiseerde
meer- of minwaarde. Kostbasis + oorspronkelijke aankoopdatum per lot verhuizen
mee.

## Wat er in dit pakket zit

| Bestand | Waarom |
|---|---|
| `portfolio_tracker/database.py` | Nieuwe kolommen `is_transfer`/`transfer_group`/`origin_date`; `execute_fund_transfer()`, `get_fund_transfers()`; `compute_cash_positions()`/`cash_ledger()` cash-neutraal voor transfers |
| `portfolio_tracker/belgian_tax.py` | `plan_transfer_lots()`, `available_quantity()`; `_fifo_core()` behandelt een transfer als niet-belastbaar en gebruikt `origin_date` voor de fotomoment-grens |
| `portfolio_tracker/views/transactions.py` | Nieuwe sectie **🔀 Fonds transfereren**: bron/bestemming kiezen, voorbeeld van de meeverhuizende loten, uitvoeren, logboek + ongedaan maken |
| `portfolio_tracker/views/common.py` | Dag-P&L-berekening sluit transferbenen uit (net als toekenningen/stockdividenden) |
| `portfolio_tracker/views/tax.py` | Transferregels in het jaaroverzicht gelabeld als 🔀 Transfer i.p.v. Verkoop |
| `portfolio_tracker/config.yaml` | Versie → 1.8.17 |
| `portfolio_tracker/CHANGELOG.md` | Rubriek 1.8.17 |

## Plaatsen

1. Kopieer alle bestanden hierboven naar hun overeenkomstige locatie in
   `portfolio_tracker/` (let op: `common.py`, `tax.py` en `transactions.py` gaan
   in `portfolio_tracker/views/`).
2. Commit en push naar `main` en `master`.
3. In Home Assistant: Instellingen → Add-ons → Portfolio Tracker → **Herbouwen**
   (niet enkel herstarten, wegens Docker-laagcaching).

De nieuwe kolommen worden bij de eerste start automatisch aan de bestaande
`transactions`-tabel toegevoegd (idempotente migratie). Er wordt niets aan
bestaande transacties gewijzigd — alle nieuwe kolommen staan standaard op
leeg/0 voor bestaande rijen.

## Gebruik

Ga naar **➕ Transacties → 🔀 Fonds transfereren**:

1. **Bestemmingsfonds eerst toevoegen** via 🏢 Activa, als dat nog niet bestaat
   — de transfer vereist een al geregistreerd doelactivum.
2. Kies het bronfonds + rekening. Het beschikbare aantal stuks verschijnt eronder.
3. Kies het bestemmingsfonds + rekening (standaard dezelfde rekening).
4. Vul het aantal in (of klik 'Alles'), de transferdatum en eventueel een notitie.
5. Bekijk het voorbeeld: welke loten (met hun oorspronkelijke datum en kostbasis)
   meeverhuizen. Is een deel nog geblokkeerd (werkgeversplan/FCPE), dan zie je dat
   hier met een waarschuwing — de blokkering verhuist gewoon mee.
6. Klik **🔀 Transfer uitvoeren**.

**Wat er daarna te zien is:**

- 📋 Overzicht: de bronregel toont 🔀 Transfer-uit, de bestemmingsregel(s) 🔀
  Transfer-in — één per meegenomen lot, elk met de oorspronkelijke datum in de
  notitie.
- 🧮 Belasting: de transfer verschijnt in het jaaroverzicht als 🔀 Transfer, altijd
  met €0 winst/verlies.
- 💰 Cashpositie/-grootboek: geen wijziging, met een aparte €0-regel
  "Transfer uit"/"Transfer naar" voor transparantie.
- Onderaan de sectie: een logboek van alle transfers, met een knop om er één
  ongedaan te maken (verwijdert beide benen samen; via de bestaande
  prullenbak-/undo-knop meteen weer terug te zetten).

## Een kanttekening over de datums

De transacties op het bestemmingsfonds tonen als **datum de transferdatum** (niet
de oorspronkelijke aankoopdatum) — dat is bewust zo, want die datum bepaalt de
FIFO-volgorde en de plaats in de portefeuille-evolutiegrafiek, en moet dus
chronologisch correct blijven staan tussen eventuele andere transacties op dat
fonds. De **oorspronkelijke aankoopdatum** staat apart vermeld in de notitie én
telt intern mee voor de fotomoment-grens van het meerwaarderegime — dat is waar
het voor de fiscale kostbasis daadwerkelijk toe doet.

## Getest

- End-to-end: kostbasis en oorspronkelijke lotdatums blijven exact behouden op het
  bestemmingsfonds; 0 gerealiseerde/belastbare winst ondanks een reële ingebedde
  meerwaarde; cashpositie verandert niet; geblokkeerde loten verhuizen correct mee.
- Foutafhandeling: te weinig stukken, onbestaand doelfonds, identieke
  bron/bestemming — telkens een duidelijke foutmelding, niets geschreven.
- Undo: verwijderen + herstellen van een volledige transfer (beide benen) via het
  bestaande prullenbak-mechanisme.
- Regressie: een gewone verkoop (geen transfer) geeft exact dezelfde
  winst/verlies-berekening als vóór deze wijziging.
- `py_compile` op het volledige project, `pyflakes` schoon (op één
  pre-bestaande waarschuwing na, ongewijzigd), geen smart quotes/NBSP, geen
  niet-ASCII identifiers.
