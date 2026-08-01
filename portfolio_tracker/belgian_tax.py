"""
belgian_tax.py — Belgische meerwaardebelasting (opt-out stelsel)

Regels (De Wever-hervorming, 10% CGT):
  • 10% meerwaardebelasting op gerealiseerde nettomeerwaarden
  • Jaarlijkse vrijstelling per belastingplichtige (standaard €10.000)
  • Minwaarden verrekend met meerwaarden binnen hetzelfde boekjaar
  • FIFO-methode, PER (ticker, rekening) — loten van rekening A voeden geen
    verkoop op rekening B
  • Alle bedragen in EUR (omgerekend op transactiedatum)
  • Transactiekosten worden APART bijgehouden (niet in de meerwaardeberekening)
  • TOB apart berekend per transactie
"""
from __future__ import annotations

from datetime import datetime
import logging
import database as db
import market_data

logger = logging.getLogger(__name__)


# ── Fotomoment (referentiewaarde 31/12/2025) ──────────────────────────────────
# Voor stukken gekocht vóór de start van het stelsel geldt als fiscale instapprijs
# de hoogste van (a) de werkelijke aankoopprijs of (b) de slotkoers op 31/12/2025
# ("fotomoment"). De keuze voor de (hogere) historische aankoopprijs is mogelijk
# t/m boekjaar 2030; vanaf 2031 telt altijd de fotomomentwaarde.
SNAPSHOT_DATE     = "2025-12-31"   # fotomoment
OPT_IN_UNTIL_YEAR = 2030           # historische kostprijs claimbaar t/m dit boekjaar


def fotomoment_taxable(sell_proceeds: float, cost_basis: float,
                       snapshot_value: float, sell_year: int,
                       opt_in_until: int = OPT_IN_UNTIL_YEAR) -> float:
    """Belastbare meer-/minwaarde voor een vóór-2026 verworven schijf.

    S = verkoopopbrengst, C = werkelijke kostprijs, F = fotomomentwaarde (alle EUR,
    voor de verkochte hoeveelheid).
      • S >= F : meerwaarde = S - F. Ligt C hoger dan F (en t/m 2030), dan mag de
        gunstigere historische kostprijs gebruikt worden: max(0, S - C) — naar
        beneden begrensd op 0 (historische minderwaarden zijn niet aftrekbaar).
      • S <  F : dit is een minderwaarde ná het fotomoment (S - F < 0), aftrekbaar.
    """
    gain_vs_f = sell_proceeds - snapshot_value
    if gain_vs_f >= 0:
        taxable = gain_vs_f
        if cost_basis > snapshot_value and sell_year <= opt_in_until:
            taxable = max(0.0, sell_proceeds - cost_basis)
        return taxable
    return gain_vs_f


def resolve_dividend_chain(a, b, c, d, rv_rate: float | None = None,
                           wht_rate: float | None = None):
    """Leid ontbrekende waarden af in de dividendketen (zelfde munt verondersteld).

      A = bruto vóór buitenlandse bronbelasting
      B = buitenlandse bronbelasting
      C = bruto na bronbelasting / vóór Belgische RV   (= A - B)
      D = netto na alle voorheffingen
      RV = Belgische roerende voorheffing               (= C - D)

    None = leeg. Vult de A/B/C-driehoek aan (twee gekend -> derde) en berekent RV.
    Optioneel:
      wht_rate (bv. 0.15): als B leeg is maar A gekend -> B = A × wht_rate.
      rv_rate  (bv. 0.30): als D leeg is maar C gekend (of afleidbaar) -> D = C × (1 − rv_rate);
                           als C leeg is maar D gekend -> C = D / (1 − rv_rate).
    """
    # Buitenlandse bronbelasting uit het tarief (vóór de driehoek, zodat C volgt)
    if b is None and a is not None and wht_rate is not None:
        b = round(a * wht_rate, 4)
    for _ in range(2):
        if c is None and a is not None and b is not None: c = a - b
        if a is None and b is not None and c is not None: a = b + c
        if b is None and a is not None and c is not None: b = a - c
    # Belgische RV uit het tarief
    if rv_rate is not None and 0 <= rv_rate < 1:
        if d is None and c is not None:
            d = round(c * (1 - rv_rate), 4)
        elif c is None and d is not None:
            c = round(d / (1 - rv_rate), 4)
            # driehoek opnieuw proberen nu C bekend is
            if a is None and b is not None: a = b + c
            if b is None and a is not None: b = a - c
    rv = (c - d) if (c is not None and d is not None) else None
    return {"a": a, "b": b, "c": c, "d": d, "rv": rv}


def verify_dividend_chain(a, b, c, d, tol: float = 0.02) -> list[str]:
    """Omgekeerde controle (④ → ③ → ② → ①) met tolerantie voor afrondingsfouten.
    Werkt op de (aangevulde) keten; geeft een lijst afwijkingen terug (leeg = OK)."""
    issues = []
    rv = (c - d) if (c is not None and d is not None) else None
    # stap ④ -> ③ : D + RV moet C geven
    if d is not None and rv is not None and c is not None:
        back_c = d + rv
        if abs(back_c - c) > tol:
            issues.append(f"④ netto + RV = {back_c:,.2f} wijkt af van ③ ({c:,.2f})")
    # stap ③ -> ① : C + B moet A geven
    if c is not None and b is not None and a is not None:
        back_a = c + b
        if abs(back_a - a) > tol:
            issues.append(f"③ + ② bronbelasting = {back_a:,.2f} wijkt af van ① ({a:,.2f})")
    # sanity: B mag niet groter zijn dan A; D niet groter dan C
    if a is not None and b is not None and b > a + tol:
        issues.append("② bronbelasting is groter dan ① bruto")
    if c is not None and d is not None and d > c + tol:
        issues.append("④ netto is groter dan ③ bruto na bronbelasting")
    return issues


# ── Buitenlandse bronbelasting per land ───────────────────────────────────────
# Indicatieve standaardtarieven op dividenden voor een Belgische particulier
# (verdragstarieven kunnen afwijken; bewerkbaar via ⚙️ Instellingen).
DEFAULT_WHT_RATES = {
    "BE": 0.0,   "US": 15.0, "NL": 15.0, "FR": 25.0, "DE": 26.375,
    "CH": 35.0,  "GB": 0.0,  "IE": 25.0, "LU": 15.0, "ES": 19.0,
    "IT": 26.0,  "PT": 28.0, "DK": 27.0, "SE": 30.0, "NO": 25.0,
    "FI": 35.0,  "AT": 27.5, "CA": 25.0, "JP": 15.315, "AU": 30.0,
}

COUNTRY_NAMES = {
    "BE": "België", "US": "Verenigde Staten", "NL": "Nederland", "FR": "Frankrijk",
    "DE": "Duitsland", "CH": "Zwitserland", "GB": "Verenigd Koninkrijk", "IE": "Ierland",
    "LU": "Luxemburg", "ES": "Spanje", "IT": "Italië", "PT": "Portugal",
    "DK": "Denemarken", "SE": "Zweden", "NO": "Noorwegen", "FI": "Finland",
    "AT": "Oostenrijk", "CA": "Canada", "JP": "Japan", "AU": "Australië",
}


def _year_rate_table() -> dict[int, dict[str, float]]:
    """De opgeslagen tarieventabel per jaar: {jaar: {landcode: percentage}}.

    Opslag: setting 'foreign_wht_rates_by_year' (JSON). Enkel jaren die je
    effectief hebt ingesteld staan erin; de rest volgt uit doorschuiving (zie
    get_wht_rates)."""
    import json as _json
    out: dict[int, dict[str, float]] = {}
    try:
        stored = db.get_setting("foreign_wht_rates_by_year", "")
        if stored:
            for yr, rates in _json.loads(stored).items():
                try:
                    y = int(yr)
                except (TypeError, ValueError):
                    continue
                out[y] = {str(k).upper(): float(v) for k, v in (rates or {}).items()}
    except Exception as exc:
        logger.warning(f"_year_rate_table: kon de jaartabel niet lezen ({exc})")
    return out


def save_year_rates(year: int, rates: dict[str, float]):
    """Bewaar de tarieven voor één specifiek jaar."""
    import json as _json
    tbl = _year_rate_table()
    tbl[int(year)] = {str(k).upper(): float(v) for k, v in rates.items()}
    db.set_setting("foreign_wht_rates_by_year",
                   _json.dumps({str(y): r for y, r in sorted(tbl.items())}))


def delete_year_rates(year: int):
    """Wis de tarieven van één jaar; dat jaar volgt dan weer het vorige jaar."""
    import json as _json
    tbl = _year_rate_table()
    tbl.pop(int(year), None)
    db.set_setting("foreign_wht_rates_by_year",
                   _json.dumps({str(y): r for y, r in sorted(tbl.items())}))


def configured_years() -> list[int]:
    """Jaren waarvoor expliciet tarieven zijn ingesteld (oplopend)."""
    return sorted(_year_rate_table().keys())


def get_wht_rates(year: int | None = None) -> dict[str, float]:
    """Tarieven buitenlandse bronbelasting (% per landcode) voor een BEPAALD JAAR.

    Bronbelastingtarieven wijzigen over de jaren (verdragen, nationale hervormingen),
    en een dividend moet belast worden tegen het tarief dat gold OP DAT MOMENT — niet
    tegen het tarief van vandaag. Daarom:

      1. Basis = de ingebouwde standaardtarieven.
      2. Daarop de oude, jaarloze instelling ('foreign_wht_rates'), voor compatibiliteit
         met wat je vóór deze versie had ingesteld.
      3. Daarop het meest recente INGESTELDE jaar dat <= 'year' ligt. Tarieven schuiven
         dus door: stel je 2024 in, dan geldt dat ook voor 2025 en 2026 tot je voor een
         van die jaren iets anders instelt. Zo hoef je enkel de WIJZIGINGEN te registreren.

    year=None -> het huidige jaar (het tarief dat vandaag geldt).
    Voor een jaar VÓÓR het vroegst ingestelde jaar gelden stap 1+2 (de standaardtarieven),
    want er is dan geen historische tabel om op terug te vallen.
    """
    rates = dict(DEFAULT_WHT_RATES)
    # (2) legacy, jaarloze override
    try:
        import json as _json
        stored = db.get_setting("foreign_wht_rates", "")
        if stored:
            for k, v in _json.loads(stored).items():
                rates[str(k).upper()] = float(v)
    except Exception:
        pass
    # (3) jaartabel met doorschuiving
    y = int(year) if year else datetime.now().year
    tbl = _year_rate_table()
    applicable = [yy for yy in tbl if yy <= y]
    if applicable:
        rates.update(tbl[max(applicable)])
    return rates


def get_wht_rate(country: str | None, year: int | None = None) -> float:
    """Tarief (fractie, bv. 0.15) voor een landcode IN EEN BEPAALD JAAR;
    0.0 indien onbekend of België. year=None -> het tarief van vandaag."""
    if not country:
        return 0.0
    return get_wht_rates(year).get(country.upper(), 0.0) / 100.0


def year_of(date_str: str | None) -> int | None:
    """Jaartal uit een 'YYYY-MM-DD'-datum; None als dat niet lukt."""
    try:
        return int(str(date_str)[:4])
    except (TypeError, ValueError):
        return None


# ── Dividendfiscaliteit (Belgische personenbelasting) ─────────────────────────

def dividend_tax_benefit(year: int | None = None, accounts=None) -> dict:
    """Bereken het fiscale voordeel op dividenden voor de Belgische personenbelasting:

      1) Vrijstelling roerende voorheffing: de eerste schijf (standaard €833) 'gewone'
         aandelendividenden per belastingplichtige is vrijgesteld -> je recupereert de
         ingehouden Belgische RV daarop (max €833 × 30% = €249,90 p.p.). Geldt NIET voor
         dividenden van fondsen/ETF's/beveks.
      2) FBB (optioneel) voor Franse aandelen: forfaitair gedeelte buitenlandse belasting,
         15% van het nettobedrag na Franse bronheffing (verdrag BE-FR).

    accounts: None (alle) of set/lijst. year: None = alle jaren samengeteld (per jaar via
    de 'per_year'-sleutel).
    """
    s = db.get_all_settings()
    exemption_pp = float(s.get("dividend_exemption_per_person", "833"))
    rv_rate      = float(s.get("withholding_tax_rate", "0.30"))
    persons      = 2 if s.get("household_regime", "single") == "community" else 1
    fbb_enabled  = s.get("fbb_enabled", "0") == "1"
    fbb_rate     = float(s.get("fbb_rate", "0.15"))
    cap_amount   = exemption_pp * persons

    accset = set(accounts) if accounts else None
    assets = {a["ticker"]: a for a in db.get_assets()}

    # Groepeer per jaar
    per_year: dict[int, dict] = {}
    for d in db.get_dividends():
        if accset is not None and (d.get("account") or db.DEFAULT_ACCOUNT) not in accset:
            continue
        yr = int(str(d["date"])[:4])
        if year is not None and yr != year:
            continue
        a = assets.get(d["ticker"], {})
        atype = a.get("asset_type", "stock")
        country = (a.get("country") or "BE").upper()
        fx = d.get("fx_rate") or 1.0
        gross_eur = d.get("gross_eur") if d.get("gross_eur") is not None else (d.get("gross_amount") or 0.0)
        foreign_wht_eur = (d.get("foreign_wht_amt") or 0.0) * fx
        wh_eur = d.get("withholding_eur")
        if wh_eur is None:
            wh_eur = (d.get("withholding_tax") or 0.0) * fx
        be_rv_eur = max(0.0, wh_eur - foreign_wht_eur)
        net_after_foreign = max(0.0, gross_eur - foreign_wht_eur)   # ~ C (grondslag BE RV / FBB)

        yd = per_year.setdefault(yr, {
            "qualifying_gross": 0.0, "be_rv_qualifying": 0.0,
            "fbb_base_fr": 0.0, "excluded_gross": 0.0})
        # Enkel individuele aandelen (geen fondsen/ETF's) én echte dividenden
        # (geen interest / securities lending) komen in aanmerking voor de 833-vrijstelling
        if atype == "stock" and (d.get("kind") or "dividend") == "dividend":
            yd["qualifying_gross"] += net_after_foreign
            yd["be_rv_qualifying"] += be_rv_eur
            if country == "FR":
                yd["fbb_base_fr"] += net_after_foreign
        else:
            yd["excluded_gross"] += gross_eur

    # Voordeel per jaar berekenen
    out_years = {}
    tot_reclaim = tot_fbb = 0.0
    for yr, yd in per_year.items():
        eligible_gross = min(yd["qualifying_gross"], cap_amount)
        reclaim = min(yd["be_rv_qualifying"], eligible_gross * rv_rate)
        fbb = (yd["fbb_base_fr"] * fbb_rate) if fbb_enabled else 0.0
        out_years[yr] = {
            **yd,
            "cap_amount": cap_amount,
            "eligible_gross": eligible_gross,
            "reclaimable_rv": reclaim,
            "fbb": fbb,
            "total_benefit": reclaim + fbb,
        }
        tot_reclaim += reclaim
        tot_fbb += fbb

    return {
        "per_year": out_years,
        "persons": persons,
        "exemption_per_person": exemption_pp,
        "cap_amount": cap_amount,
        "rv_rate": rv_rate,
        "fbb_enabled": fbb_enabled,
        "fbb_rate": fbb_rate,
        "total_reclaimable_rv": tot_reclaim,
        "total_fbb": tot_fbb,
        "total_benefit": tot_reclaim + tot_fbb,
    }


# ── TOB berekening ────────────────────────────────────────────────────────────

def calculate_tob(asset_type: str, etf_subtype: str, total_amount_eur: float,
                  belgian_registered: bool = True, txn_date=None) -> float:
    """Belgische beurstaks (TOB), berekend op de waarde in EUR.

    BELANGRIJK: 'total_amount_eur' moet de transactiewaarde in EUR zijn (niet de
    native valuta). De TOB is een Belgische heffing op de EUR-tegenwaarde; rekenen
    op het native bedrag geeft een (FX-)fout.

    txn_date: indien gegeven en vóór de geconfigureerde ingangsdatum
    ('tob_start_date', default 1/1/2017 — sinds wanneer Belgische beleggers via een
    buitenlandse tussenpersoon TOB-plichtig zijn), is er geen TOB (0).

    Tarieven (met plafond per verrichting):
      0,12% (max €1.300): obligaties; in België aangeboden UITKERENDE ETF's/fondsen
      1,32% (max €4.000): in België aangeboden KAPITALISERENDE ETF's/fondsen
      0,35% (max €1.600): aandelen; alle overige effecten, waaronder ETF's/fondsen
                          die NIET in België zijn aangeboden/geregistreerd
    """
    s = db.get_all_settings()
    if txn_date is not None:
        start = s.get("tob_start_date", "2017-01-01")
        if str(txn_date)[:10] < str(start)[:10]:
            return 0.0
    rate012 = float(s.get("tob_rate_etf_distributing", "0.0012"))
    cap012  = float(s.get("tob_max_etf_distributing",  "1300"))
    rate132 = float(s.get("tob_rate_etf_accumulating", "0.0132"))
    cap132  = float(s.get("tob_max_etf_accumulating",  "4000"))
    rate035 = float(s.get("tob_rate_stocks",           "0.0035"))
    cap035  = float(s.get("tob_max_stocks",            "1600"))

    if asset_type == "bond":
        rate, cap = rate012, cap012
    elif asset_type == "etf":
        if not belgian_registered:
            rate, cap = rate035, cap035          # niet in België aangeboden -> "andere effecten"
        elif etf_subtype == "accumulating":
            rate, cap = rate132, cap132
        else:
            rate, cap = rate012, cap012
    else:  # stock / overige
        rate, cap = rate035, cap035

    return round(min(total_amount_eur * rate, cap), 2)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _eur_total(txn: dict) -> float:
    """EUR-totaal van een transactie, met fallback voor oude rijen."""
    v = txn.get("total_amount_eur")
    if v is not None:
        return float(v)
    return float(txn["total_amount"]) * float(txn.get("fx_rate") or 1.0)


def _acct(txn: dict) -> str:
    return txn.get("account") or db.DEFAULT_ACCOUNT


def _year(date_str: str) -> int:
    fmt = "%Y-%m-%d %H:%M:%S" if " " in date_str else "%Y-%m-%d"
    return datetime.strptime(date_str[:19] if " " in date_str else date_str[:10], fmt).year


# ── FIFO core (per ticker + rekening, in EUR) ─────────────────────────────────

def _fifo_core(transactions: list[dict], snapshots: dict | None = None):
    """
    Verwerk transacties chronologisch via FIFO per (ticker, rekening).

    snapshots: optioneel {ticker: fotomomentwaarde_per_stuk_EUR}. Indien gegeven,
    wordt voor loten gekocht vóór REGIME_START_YEAR de belastbare meer-/minwaarde
    op basis van het fotomoment berekend (zie fotomoment_taxable). De economische
    'gain_loss' blijft de werkelijke winst/verlies; 'taxable_gain_loss' is de
    fiscale basis.

    Returns:
      pos_by_key   : {(ticker, account): {lots, total_quantity, total_cost}}
      realized     : lijst gerealiseerde W/V (EUR), met 'account'
      costs_by_key : {(ticker, account): som costs_eur}  (alle transacties)
    """
    snapshots = snapshots or {}
    txns = sorted(transactions, key=lambda x: x["date"])
    pos_by_key: dict[tuple, dict] = {}
    realized: list[dict] = []
    costs_by_key: dict[tuple, float] = {}

    for txn in txns:
        ticker = txn["ticker"]
        acct   = _acct(txn)
        key    = (ticker, acct)

        if key not in pos_by_key:
            pos_by_key[key] = {"lots": [], "total_quantity": 0.0, "total_cost": 0.0}
        pos = pos_by_key[key]

        costs_by_key[key] = costs_by_key.get(key, 0.0) + float(txn.get("costs_eur") or 0.0)

        eur_total = _eur_total(txn)
        qty       = float(txn["quantity"])
        price_eur = eur_total / qty if qty else 0.0

        if txn["transaction_type"] == "buy":
            pos["lots"].append({
                "date":               txn["date"],
                "quantity":           qty,
                "remaining_quantity": qty,
                "price_per_unit":     price_eur,   # EUR
                "total_cost":         eur_total,
                "currency":           "EUR",
                # Blokkering (bv. werkgeversplan/FCPE): dit lot is pas VANAF deze
                # datum vrij verhandelbaar. None/leeg = nooit geblokkeerd.
                "lock_until":         txn.get("lock_until"),
            })
            pos["total_quantity"] += qty
            pos["total_cost"]     += eur_total

        else:  # sell
            sell_qty     = qty
            sell_total   = eur_total          # EUR opbrengst (kosten apart)
            sell_year    = _year(txn["date"])
            snap_unit    = snapshots.get(ticker)
            remaining    = sell_qty
            cost_basis   = 0.0
            taxable_gl   = 0.0
            used_fotomoment = False
            for lot in pos["lots"]:
                if remaining <= 0:
                    break
                if lot["remaining_quantity"] <= 0:
                    continue
                consumed = min(lot["remaining_quantity"], remaining)
                portion_cost     = consumed * lot["price_per_unit"]
                portion_proceeds = consumed * price_eur
                cost_basis += portion_cost

                if snap_unit is not None and _year(lot["date"]) < REGIME_START_YEAR:
                    F = snap_unit * consumed
                    taxable_gl += fotomoment_taxable(portion_proceeds, portion_cost,
                                                     F, sell_year)
                    used_fotomoment = True
                else:
                    taxable_gl += portion_proceeds - portion_cost

                lot["remaining_quantity"] -= consumed
                remaining                 -= consumed

            realized.append({
                "ticker":     ticker,
                "account":    acct,
                "date":       txn["date"],
                "year":       sell_year,
                "quantity":   sell_qty,
                "sell_price": price_eur,
                "sell_total": sell_total,
                "cost_basis": cost_basis,
                "gain_loss":  sell_total - cost_basis,   # economisch (kosten tellen NIET mee)
                "taxable_gain_loss": taxable_gl,         # fiscale basis (fotomoment toegepast)
                "fotomoment_applied": used_fotomoment,
            })
            pos["total_quantity"] = max(0.0, pos["total_quantity"] - sell_qty)
            pos["total_cost"]     = max(0.0, pos["total_cost"]     - cost_basis)

    return pos_by_key, realized, costs_by_key


def build_fifo_positions(transactions: list[dict],
                         snapshots: dict | None = None) -> tuple[dict, list[dict]]:
    """
    Backward-compatibele weergave: posities geaggregeerd per ticker
    (over alle rekeningen heen). Realized blijft een platte lijst (met account).
    snapshots: optioneel {ticker: fotomomentwaarde_per_stuk_EUR} (zie _fifo_core).
    """
    pos_by_key, realized, _ = _fifo_core(transactions, snapshots)
    positions: dict[str, dict] = {}
    for (ticker, _acctname), pos in pos_by_key.items():
        if ticker not in positions:
            positions[ticker] = {"lots": [], "total_quantity": 0.0, "total_cost": 0.0}
        positions[ticker]["lots"].extend(pos["lots"])
        positions[ticker]["total_quantity"] += pos["total_quantity"]
        positions[ticker]["total_cost"]     += pos["total_cost"]
    return positions, realized


def build_fifo_positions_by_account(transactions: list[dict]) -> dict:
    """{account: {ticker: position}} — voor per-rekening weergaven."""
    pos_by_key, _, _ = _fifo_core(transactions)
    out: dict[str, dict] = {}
    for (ticker, acct), pos in pos_by_key.items():
        out.setdefault(acct, {})[ticker] = pos
    return out


def locked_summary(transactions: list[dict], on_date: str | None = None) -> dict:
    """Geblokkeerd (nog niet vrij verhandelbaar) deel van de OPEN posities.

    Een lot met een lock_until-datum is geblokkeerd zolang die datum in de toekomst
    ligt: 'vrij vanaf'-semantiek, dus op de dag zelf is het lot al vrij. De blokkering
    volgt de resterende FIFO-hoeveelheid van het lot: verkoop je (van een vrij lot)
    stukken, dan verandert dat niets aan wat elders nog vastzit.

    In de praktijk (werkgeversplannen zoals FCPE) lopen FIFO-volgorde en
    deblokkeringsvolgorde gelijk: de oudste toekenningen komen het eerst vrij. De
    FIFO-verwerking zelf blijft dan ook ongewijzigd — dit is een RAPPORTERING, geen
    verkoopbeperking (de app detecteert en toont, ze blokkeert niet; zie ook de
    waarschuwing in het verkoopformulier).

    Returns: {"by_key": {(ticker, account): {"locked_qty", "next_unlock"}},
              "by_ticker": {ticker: {"locked_qty", "next_unlock"}}}
    Enkel posities met effectief geblokkeerde stukken komen in het resultaat voor.
    """
    from datetime import date as _date
    on = (str(on_date)[:10] if on_date else _date.today().isoformat())
    pos_by_key, _, _ = _fifo_core(transactions)
    by_key: dict[tuple, dict] = {}
    by_ticker: dict[str, dict] = {}
    for (tk, acct), pos in pos_by_key.items():
        locked, nxt = 0.0, None
        for lot in pos["lots"]:
            rem = float(lot.get("remaining_quantity") or 0.0)
            lu  = (lot.get("lock_until") or "")[:10]
            if rem > 1e-9 and lu and lu > on:
                locked += rem
                if nxt is None or lu < nxt:
                    nxt = lu
        if locked > 1e-9:
            by_key[(tk, acct)] = {"locked_qty": locked, "next_unlock": nxt}
            agg = by_ticker.setdefault(tk, {"locked_qty": 0.0, "next_unlock": None})
            agg["locked_qty"] += locked
            if nxt and (agg["next_unlock"] is None or nxt < agg["next_unlock"]):
                agg["next_unlock"] = nxt
    return {"by_key": by_key, "by_ticker": by_ticker}


def total_costs_eur(transactions: list[dict]) -> float:
    """Som van alle transactiekosten in EUR (apart van de belasting)."""
    return sum(float(t.get("costs_eur") or 0.0) for t in transactions)


def open_position_tickers(epsilon: float = 1e-6) -> tuple[list[str], list[str]]:
    """(open_tickers, gesloten_tickers) — welke activa hebben nog een positie?

    BELANGRIJK: dit gebruikt exact DEZELFDE FIFO-logica als het dashboard en de
    portefeuillepagina (build_fifo_positions op de split-gecorrigeerde transacties).
    In 0.34.1 stond hier een eigen SQL-som (SUM(buy) - SUM(sell)), en dat is precies
    het soort duplicaat dat stilletjes uiteen gaat lopen met de rest van de app: elk
    transactietype dat niet letterlijk 'buy' of 'sell' heet, elke splitsing en elke
    andere nuance in _fifo_core telde daar niet mee, waardoor een activum ten onrechte
    als 'gesloten' kon worden bestempeld en er geen koersen meer voor werden opgehaald.
    Eén bron van waarheid is hier belangrijker dan een snellere query.

    Activa ZONDER transacties gelden als open: je hebt ze net toegevoegd en wil de
    koers al zien vóór je koopt.
    """
    assets = [a["ticker"] for a in db.get_assets()]
    txns = db.get_transactions()
    positions, _ = build_fifo_positions(txns)
    with_tx = {t["ticker"] for t in txns if t.get("ticker")}

    open_t, closed_t = [], []
    for tk in assets:
        qty = (positions.get(tk) or {}).get("total_quantity", 0.0) or 0.0
        if qty > epsilon or tk not in with_tx:
            open_t.append(tk)
        else:
            closed_t.append(tk)
    return open_t, closed_t


# ── Portefeuillewaarde (EUR) ─────────────────────────────────────────────────

def _price_eur(price: float | None, currency: str) -> float | None:
    if price is None:
        return None
    if currency == "EUR":
        return price
    conv = market_data.convert_to_eur(price, currency)
    return conv if conv is not None else None


def get_position_values(positions: dict, current_prices: dict) -> dict[str, dict]:
    """
    Actuele waarde en ongerealiseerde P&L per positie, ALLES in EUR.
    positions    : {ticker: {total_quantity, total_cost(EUR), ...}}
    current_prices: {ticker: {'price': float|None, 'currency': str}}
    """
    result = {}
    for ticker, pos in positions.items():
        qty  = pos["total_quantity"]
        cost = pos["total_cost"]          # EUR
        if qty <= 0:
            continue

        avg_cost   = cost / qty if qty > 0 else 0.0
        price_info = current_prices.get(ticker, {})
        native     = price_info.get("price")
        currency   = price_info.get("currency", "EUR")
        price_eur  = _price_eur(native, currency)

        if price_eur is not None:
            curr_value    = qty * price_eur
            unreal_gl     = curr_value - cost
            unreal_gl_pct = (unreal_gl / cost * 100) if cost > 0 else 0.0
        else:
            curr_value = unreal_gl = unreal_gl_pct = None

        result[ticker] = {
            "quantity":                 qty,
            "avg_cost":                 avg_cost,        # EUR/stuk
            "total_cost":               cost,           # EUR
            "current_price":            native,         # native
            "current_price_eur":        price_eur,      # EUR
            "current_price_currency":   currency,
            "current_value":            curr_value,     # EUR
            "unrealized_gain_loss":     unreal_gl,      # EUR
            "unrealized_gain_loss_pct": unreal_gl_pct,
        }
    return result


# ── Per-rekening samenvatting ─────────────────────────────────────────────────

def account_summary(transactions: list[dict], current_prices: dict) -> dict[str, dict]:
    """
    Per rekening: kostenbasis, huidige waarde, en %-meer/minwaarde t.o.v.
    aankoopprijs (ongerealiseerd). Alles in EUR.
    """
    by_acct = build_fifo_positions_by_account(transactions)
    out: dict[str, dict] = {}
    for acct, positions in by_acct.items():
        pv = get_position_values(positions, current_prices)
        cost  = sum(p["total_cost"] for p in pv.values())
        value = sum(p["current_value"] for p in pv.values() if p["current_value"] is not None)
        gl    = value - cost
        out[acct] = {
            "cost_basis":    cost,
            "current_value": value,
            "gain_loss":     gl,
            "gain_loss_pct": (gl / cost * 100) if cost > 0 else 0.0,
            "n_positions":   len(pv),
        }
    return out


# ── Meerwaardebelasting ───────────────────────────────────────────────────────

# Wettelijke parameters voor de overdraagbare vrijstelling
REGIME_START_YEAR = 2026     # meerwaardebelasting van kracht vanaf 2026
CARRY_CAP_PER_YEAR = 1000.0  # max overdraagbaar deel per jaar (eerste schijf)
CARRY_MAX_YEARS = 5          # overdracht max 5 jaar -> max +€5.000 p.p.


def realized_gains_by_year(all_gains: list[dict]) -> dict[int, float]:
    """Netto BELASTBARE gerealiseerde W/V per boekjaar (fotomoment toegepast).
    Valt terug op de economische gain_loss als er geen fiscale basis is."""
    out: dict[int, float] = {}
    for g in all_gains:
        val = g.get("taxable_gain_loss", g["gain_loss"])
        out[g["year"]] = out.get(g["year"], 0.0) + val
    return out


def available_exemption(gains_by_year: dict[int, float], target_year: int,
                        base_exemption: float, count: int,
                        first_activity_year: int | None = None) -> dict:
    """
    Bereken de beschikbare vrijstelling voor target_year mét meerjarige opbouw.

    Regels (per belastingplichtige):
      • basisvrijstelling €10.000/jaar (instelbaar via base_exemption)
      • ongebruikt deel van de EERSTE schijf van €1.000 is overdraagbaar
      • overdracht max 5 jaar -> opbouw tot max €15.000 p.p.
      • overgedragen vrijstelling wordt als EERSTE benut, vóór de basisvrijstelling
    Aanname bij gemeenschap van goederen (count=2): de jaarwinst wordt 50/50
    aan beide partners toegerekend; elke partner bouwt zijn eigen pot op.
    """
    start = REGIME_START_YEAR
    if first_activity_year:
        start = max(start, first_activity_year)
    if target_year < start:
        # Regime nog niet van toepassing in dit jaar
        per_person = base_exemption if target_year >= REGIME_START_YEAR else 0.0
        return {"base_per_person": base_exemption,
                "carry_per_person": 0.0,
                "total_per_person": per_person,
                "effective_total": per_person * count,
                "base_effective": base_exemption * count,
                "carry_effective": 0.0}

    lots: list[list] = []   # [origin_year, remaining] (per persoon)
    carry_in_target = 0.0

    for y in range(start, target_year + 1):
        # Verlopen lots verwijderen (bruikbaar van origin+1 t/m origin+CARRY_MAX_YEARS)
        lots = [lot for lot in lots if lot[0] >= y - CARRY_MAX_YEARS]
        carry_available = sum(lot[1] for lot in lots)
        if y == target_year:
            carry_in_target = carry_available

        gains_pp = max(0.0, gains_by_year.get(y, 0.0) / count)  # per persoon

        # Verbruik: eerst overgedragen pot (oudste eerst), dan basis
        remaining = gains_pp
        for lot in sorted(lots):
            if remaining <= 0:
                break
            take = min(lot[1], remaining)
            lot[1] -= take
            remaining -= take
        base_used = min(base_exemption, remaining)

        # Nieuwe overdracht = ongebruikt deel van de eerste €1.000 van de basis
        base_first_used = min(CARRY_CAP_PER_YEAR, base_used)
        new_carry = CARRY_CAP_PER_YEAR - base_first_used
        if new_carry > 1e-9 and y < target_year:
            lots.append([y, new_carry])
        lots = [lot for lot in lots if lot[1] > 1e-9]

    total_pp = base_exemption + carry_in_target
    return {
        "base_per_person":  base_exemption,
        "carry_per_person": carry_in_target,
        "total_per_person": total_pp,
        "effective_total":  total_pp * count,
        "base_effective":   base_exemption * count,
        "carry_effective":  carry_in_target * count,
    }


def calculate_tax_overview(year: int | None = None,
                            current_prices: dict | None = None,
                            account=None,
                            extra_transactions: list[dict] | None = None) -> dict:
    """
    Belastingoverzicht voor een boekjaar.

    De belasting (gerealiseerde W/V, vrijstelling) is ALTIJD globaal over alle
    rekeningen — de €-vrijstelling geldt per belastingplichtige. De 'account'-
    filter beïnvloedt alleen de getoonde posities/waarde (portefeuillekant).
    'account' mag None (alle), een string (één rekening) of een lijst/tuple zijn.

    extra_transactions: optionele lijst hypothetische transacties (zelfde vorm als
    db.get_transactions()) die mee verwerkt worden — gebruikt door de
    simulatiemodule om verkopen/heraankopen vooraf door te rekenen.
    """
    if year is None:
        year = datetime.now().year

    # Normaliseer rekeningfilter naar een set (of None = alle)
    if account is None:
        accts = None
    elif isinstance(account, str):
        accts = {account}
    else:
        accts = set(account) or None

    s         = db.get_all_settings()
    tax_rate  = float(s.get("capital_gains_tax_rate", "0.10"))
    base_exemption  = float(s.get("annual_exemption", "10000"))
    regime          = s.get("household_regime", "single")
    exemption_count = 2 if regime == "community" else 1

    all_txns = db.get_transactions()                      # globaal -> belasting
    if extra_transactions:
        all_txns = all_txns + list(extra_transactions)
    # Fotomoment-waarden per ticker (slotkoers 31/12/2025, in EUR)
    snapshots = {a["ticker"]: a["snapshot_price_eur"]
                 for a in db.get_assets()
                 if a.get("snapshot_price_eur") is not None}
    _, all_gains = build_fifo_positions(all_txns, snapshots)

    # Meerjarige opbouw van de vrijstelling (overdracht ongebruikt deel, max 5 jaar)
    gains_by_year = realized_gains_by_year(all_gains)     # fiscale basis
    first_year = None
    if all_txns:
        first_year = min(int(t["date"][:4]) for t in all_txns)
    exm = available_exemption(gains_by_year, year, base_exemption,
                              exemption_count, first_year)
    exemption       = exm["effective_total"]             # basis + opbouw, × aantal partners

    year_gains       = [g for g in all_gains if g["year"] == year]
    total_real_gl    = sum(g["gain_loss"] for g in year_gains)                       # economisch
    total_taxable_gl = sum(g.get("taxable_gain_loss", g["gain_loss"]) for g in year_gains)  # fiscaal
    # Bestond het regime in dat jaar wel? Vóór REGIME_START_YEAR was er voor normaal
    # beheer geen meerwaardebelasting; er is dan NIETS verschuldigd, hoe groot de
    # meerwaarde ook was. available_exemption() geeft voor zo'n jaar een vrijstelling
    # van 0 terug (er valt immers niets vrij te stellen) — die 0 mocht hier niet
    # gelezen worden als 'alles is belastbaar'.
    regime_applicable = year >= REGIME_START_YEAR
    if regime_applicable:
        taxable = max(0.0, total_taxable_gl - exemption) if total_taxable_gl > 0 else 0.0
    else:
        taxable = 0.0
    tax_due          = round(taxable * tax_rate, 2)
    fotomoment_used  = any(g.get("fotomoment_applied") for g in year_gains)

    # Gerealiseerde W/V voor weergave: alle jaren, rekening-bewust.
    # (De fiscale berekening hierboven blijft globaal + per boekjaar.)
    sel_realized      = [g for g in all_gains if (accts is None or g["account"] in accts)]
    sel_real_total    = sum(g["gain_loss"] for g in sel_realized)
    sel_real_year     = sum(g["gain_loss"] for g in sel_realized if g["year"] == year)

    # Dividenden dit boekjaar (EUR)
    divs      = db.get_dividends(year=year)
    gross_div = sum((d.get("gross_eur") if d.get("gross_eur") is not None
                     else d["gross_amount"]) for d in divs)
    wh_tax    = sum((d.get("withholding_eur") if d.get("withholding_eur") is not None
                     else d["withholding_tax"]) for d in divs)
    net_div   = gross_div - wh_tax

    # Posities (eventueel gefilterd op rekening)
    display_txns = [t for t in all_txns if _acct(t) in accts] if accts else all_txns
    positions, _ = build_fifo_positions(display_txns)

    if current_prices is None:
        assets  = db.get_assets()
        tickers = [a["ticker"] for a in assets]
        current_prices = market_data.get_prices_for_tickers(tickers)

    pos_values     = get_position_values(positions, current_prices)
    total_curr_val = sum(p["current_value"] for p in pos_values.values() if p["current_value"])
    total_cost_bas = sum(p["total_cost"]    for p in pos_values.values())
    total_unreal   = sum(p["unrealized_gain_loss"] for p in pos_values.values()
                         if p["unrealized_gain_loss"] is not None)

    # Kosten (apart) — globaal en voor de getoonde selectie
    costs_total = total_costs_eur(all_txns)
    costs_sel   = total_costs_eur(display_txns)
    costs_year  = total_costs_eur(db.get_transactions(year=year))

    # Algemene rekeningkosten (beheerskosten e.d. — niet aandeel-gebonden)
    acct_costs_total = db.total_account_costs_eur()
    acct_costs_sel   = (sum(db.total_account_costs_eur(account=a) for a in accts)
                        if accts else acct_costs_total)
    acct_costs_year  = db.total_account_costs_eur(year=year)

    return {
        "year":                  year,
        "account_filter":        account,
        "realized_gains":        year_gains,
        "total_realized_gl":     total_real_gl,
        "total_taxable_gl":      total_taxable_gl,
        "fotomoment_applied":    fotomoment_used,
        "all_realized_gains":      all_gains,
        "realized_all_total":      sum(g["gain_loss"] for g in all_gains),
        "selection_realized_gains": sel_realized,
        "selection_realized_total": sel_real_total,
        "selection_realized_year":  sel_real_year,
        "annual_exemption":      exemption,
        "base_exemption":        base_exemption,
        "base_exemption_effective": exm["base_effective"],
        "carry_exemption":       exm["carry_effective"],
        "exemption_count":       exemption_count,
        "household_regime":      regime,
        "taxable_amount":        taxable,
        "regime_applicable":     regime_applicable,
        "regime_start_year":     REGIME_START_YEAR,
        "tax_rate":              tax_rate,
        "tax_due":               tax_due,
        "remaining_exemption":   max(0.0, exemption - total_taxable_gl) if total_taxable_gl >= 0 else exemption,
        "total_dividends_gross": gross_div,
        "total_withholding_tax": wh_tax,
        "total_dividends_net":   net_div,
        "total_portfolio_value": total_curr_val,
        "total_cost_basis":      total_cost_bas,
        "unrealized_gl":         total_unreal,
        "total_costs":           costs_total,
        "selection_costs":       costs_sel,
        "year_costs":            costs_year,
        "account_costs_total":     acct_costs_total,
        "account_costs_selection": acct_costs_sel,
        "account_costs_year":      acct_costs_year,
        "positions":             positions,
        "position_values":       pos_values,
    }


# ── Historische reconstructie (pure functie, geen netwerk) ────────────────────

def reconstruct_portfolio_evolution(transactions: list[dict],
                                    price_series_map: dict,
                                    fx_series_map: dict,
                                    ticker_currency: dict):
    """
    Reconstrueer dagelijkse portefeuillewaarde en kostenbasis per rekening (EUR).

    price_series_map : {ticker: pandas.Series native close, datum-index}
    fx_series_map    : {currency: pandas.Series fx→EUR}  (EUR -> None)
    ticker_currency  : {ticker: currency}

    Returns pandas.DataFrame met kolommen:
       value::<account>, cost::<account>, value::TOTAL, cost::TOTAL
    """
    import pandas as pd

    if not transactions:
        return pd.DataFrame()

    txns = sorted(transactions, key=lambda x: x["date"])
    start = txns[0]["date"][:10]

    # Volledige dagindex
    all_idx = None
    for s in price_series_map.values():
        if s is not None and len(s):
            all_idx = s.index if all_idx is None else all_idx.union(s.index)
    if all_idx is None:
        return pd.DataFrame()
    full_idx = pd.date_range(start=start, end=all_idx.max(), freq="D")

    # EUR-prijsreeks per ticker (native * fx), ge-reindexed + ffill
    price_eur_map = {}
    for ticker, series in price_series_map.items():
        if series is None or not len(series):
            continue
        cur = ticker_currency.get(ticker, "EUR")
        s = series.reindex(full_idx).ffill()
        if cur != "EUR":
            fx = fx_series_map.get(cur)
            if fx is not None and len(fx):
                fx = fx.reindex(full_idx).ffill().bfill()
                s = s * fx
        price_eur_map[ticker] = s

    # FIFO-snapshots: na elke transactie de remaining cost + qty per (ticker,acct)
    pos: dict[tuple, dict] = {}
    accounts = set()
    # Per (ticker,acct): bouw step-series voor qty en remaining cost
    qty_steps: dict[tuple, dict] = {}   # key -> {date: qty}
    cost_steps: dict[tuple, dict] = {}  # key -> {date: remaining_cost_eur}

    def eur_total(t):
        v = t.get("total_amount_eur")
        return float(v) if v is not None else float(t["total_amount"]) * float(t.get("fx_rate") or 1.0)

    for t in txns:
        ticker = t["ticker"]
        acct = t.get("account") or db.DEFAULT_ACCOUNT
        accounts.add(acct)
        key = (ticker, acct)
        if key not in pos:
            pos[key] = {"lots": [], "qty": 0.0, "cost": 0.0}
        p = pos[key]
        q = float(t["quantity"])
        et = eur_total(t)
        ppu = et / q if q else 0.0
        if t["transaction_type"] == "buy":
            p["lots"].append({"rem": q, "ppu": ppu})
            p["qty"] += q
            p["cost"] += et
        else:
            rem = q
            cb = 0.0
            for lot in p["lots"]:
                if rem <= 0:
                    break
                if lot["rem"] <= 0:
                    continue
                c = min(lot["rem"], rem)
                cb += c * lot["ppu"]
                lot["rem"] -= c
                rem -= c
            p["qty"] = max(0.0, p["qty"] - q)
            p["cost"] = max(0.0, p["cost"] - cb)
        d = pd.Timestamp(t["date"][:10])
        qty_steps.setdefault(key, {})[d] = p["qty"]
        cost_steps.setdefault(key, {})[d] = p["cost"]

    # Bouw per rekening de value/cost series
    value_cols: dict[str, object] = {}
    cost_cols: dict[str, object] = {}
    for acct in accounts:
        value_cols[acct] = pd.Series(0.0, index=full_idx)
        cost_cols[acct] = pd.Series(0.0, index=full_idx)

    for (ticker, acct), steps in qty_steps.items():
        qser = pd.Series(steps).sort_index().reindex(full_idx).ffill().fillna(0.0)
        cser = pd.Series(cost_steps[(ticker, acct)]).sort_index().reindex(full_idx).ffill().fillna(0.0)
        pser = price_eur_map.get(ticker)
        if pser is not None:
            value_cols[acct] = value_cols[acct] + (qser * pser).fillna(0.0)
        cost_cols[acct] = cost_cols[acct] + cser

    data = {}
    total_val = pd.Series(0.0, index=full_idx)
    total_cost = pd.Series(0.0, index=full_idx)
    for acct in accounts:
        data[f"value::{acct}"] = value_cols[acct]
        data[f"cost::{acct}"] = cost_cols[acct]
        total_val = total_val + value_cols[acct]
        total_cost = total_cost + cost_cols[acct]
    data["value::TOTAL"] = total_val
    data["cost::TOTAL"] = total_cost

    df = pd.DataFrame(data, index=full_idx)
    # Beperk tot dagen waarop er iets in portefeuille zat
    df = df[df["cost::TOTAL"] > 0]
    return df

# ── Deblokkeringskalender ─────────────────────────────────────────────────────

def unlock_schedule(transactions: list[dict], current_prices: dict | None = None,
                    on_date: str | None = None) -> dict:
    """Wanneer komt hoeveel geblokkeerd kapitaal vrij?

    Werkt op dezelfde FIFO-loten als de rest van de app: elk lot met een
    lock_until-datum in de toekomst telt mee voor zijn RESTERENDE hoeveelheid, zodat
    verkopen uit vrije loten de kalender niet vervuilen.

    Per deblokkeringsdatum wordt de huidige waarde geschat als
    resterend_aantal × huidige koers (in EUR). Is er geen koers, dan valt de waarde
    terug op de kostbasis van het lot — dat is beter dan niets tonen, en het wordt
    apart gemeld zodat het cijfer niet als marktwaarde gelezen wordt.

    Returns:
      {"events":  [{"date","ticker","account","quantity","cost_eur","value_eur",
                    "priced","days_until"}, ...]  (chronologisch),
       "by_date": [{"date","quantity","cost_eur","value_eur","tickers","days_until"}],
       "totals":  {"locked_qty_value","locked_cost","free_value","priced_ok"},
       "on_date": "JJJJ-MM-DD"}
    """
    from datetime import date as _d
    on = (str(on_date)[:10] if on_date else _d.today().isoformat())
    on_dt = _d.fromisoformat(on)
    prices = current_prices or {}
    pos_by_key, _, _ = _fifo_core(transactions)

    events, free_value, priced_ok = [], 0.0, True
    for (tk, acct), pos in pos_by_key.items():
        px = _price_eur((prices.get(tk) or {}).get("price"),
                        (prices.get(tk) or {}).get("currency", "EUR"))
        for lot in pos["lots"]:
            rem = float(lot.get("remaining_quantity") or 0.0)
            if rem <= 1e-9:
                continue
            unit_cost = float(lot.get("price_per_unit") or 0.0)
            cost = rem * unit_cost
            if px is not None:
                value, ok = rem * px, True
            else:
                value, ok = cost, False
                priced_ok = False
            lu = (lot.get("lock_until") or "")[:10]
            if not lu or lu <= on:
                free_value += value
                continue
            events.append({
                "date": lu, "ticker": tk, "account": acct, "quantity": rem,
                "cost_eur": cost, "value_eur": value, "priced": ok,
                "days_until": (_d.fromisoformat(lu) - on_dt).days,
            })

    events.sort(key=lambda e: (e["date"], e["ticker"], e["account"]))
    by_date: dict[str, dict] = {}
    for e in events:
        b = by_date.setdefault(e["date"], {"date": e["date"], "quantity": 0.0,
                                           "cost_eur": 0.0, "value_eur": 0.0,
                                           "tickers": set(), "days_until": e["days_until"]})
        b["quantity"] += e["quantity"]
        b["cost_eur"] += e["cost_eur"]
        b["value_eur"] += e["value_eur"]
        b["tickers"].add(e["ticker"])
    rows = []
    for b in sorted(by_date.values(), key=lambda x: x["date"]):
        b["tickers"] = sorted(b["tickers"])
        rows.append(b)

    return {
        "events": events,
        "by_date": rows,
        "totals": {
            "locked_value": sum(e["value_eur"] for e in events),
            "locked_cost":  sum(e["cost_eur"] for e in events),
            "locked_qty":   sum(e["quantity"] for e in events),
            "free_value":   free_value,
            "priced_ok":    priced_ok,
        },
        "on_date": on,
    }


# ── Aangiftehulp ──────────────────────────────────────────────────────────────
# Deze functie REKENT alleen; ze beslist niets. De codes van de vakken staan als
# instelling in de database (net als de tarieven), want ze wijzigen van jaar tot
# jaar en de app mag ze niet als eeuwige waarheid hardcoderen. De gebruiker moet ze
# hoe dan ook naast het echte aangifteformulier leggen — dat staat ook prominent op
# de pagina zelf.

DECLARATION_CODE_DEFAULTS = {
    "decl_code_div_no_rv": "1444 / 2444",
    "decl_code_rv_refund": "1437 / 2437",
    "decl_code_fbb":       "",
    "decl_code_cgt":       "",
}


def declaration_lines(year: int, accounts=None) -> dict:
    """Bouw de aangifteregels voor een boekjaar: per vak het in te vullen bedrag,
    met de onderliggende lijnen erbij zodat elk cijfer navolgbaar is.

    Returns: {"year", "lines": [...], "notes": [...], "settings": {...}}
    Elke lijn: {"key","vak","label","code","amount","kind","explanation","rows",
                "verify"} waarbij 'rows' de brondetails zijn en 'verify' aangeeft dat
    de code onzeker is en nagekeken moet worden.
    """
    s = db.get_all_settings()
    codes = {k: (s.get(k) if s.get(k) is not None else v)
             for k, v in DECLARATION_CODE_DEFAULTS.items()}
    accset = set(accounts) if accounts else None
    assets = {a["ticker"]: a for a in db.get_assets()}

    # ── Dividenden van het boekjaar, opgesplitst naar hoe ze belast werden ──
    div_no_rv, div_with_rv = [], []
    for d in db.get_dividends(year=year):
        if accset is not None and (d.get("account") or db.DEFAULT_ACCOUNT) not in accset:
            continue
        fx = d.get("fx_rate") or 1.0
        gross = d.get("gross_eur") if d.get("gross_eur") is not None else (d.get("gross_amount") or 0.0)
        foreign = (d.get("foreign_wht_amt") or 0.0) * fx
        wh = d.get("withholding_eur")
        if wh is None:
            wh = (d.get("withholding_tax") or 0.0) * fx
        be_rv = max(0.0, wh - foreign)
        row = {
            "date": str(d["date"])[:10], "ticker": d.get("ticker") or "—",
            "account": d.get("account") or db.DEFAULT_ACCOUNT,
            "gross_eur": gross, "foreign_wht_eur": foreign,
            "after_foreign_eur": max(0.0, gross - foreign),
            "be_rv_eur": be_rv,
            "country": (assets.get(d.get("ticker"), {}).get("country") or "BE").upper(),
            "asset_type": assets.get(d.get("ticker"), {}).get("asset_type", "stock"),
            "kind": d.get("kind") or "dividend",
        }
        (div_with_rv if be_rv > 0.005 else div_no_rv).append(row)

    ben = dividend_tax_benefit(year=year, accounts=accounts)
    byear = ben["per_year"].get(year, {})
    overview = calculate_tax_overview(year=year, account=accounts)

    lines = []

    # 1. Buitenlandse dividenden zonder Belgische inhouding: VERPLICHT aan te geven
    amt_no_rv = sum(r["after_foreign_eur"] for r in div_no_rv)
    lines.append({
        "key": "div_no_rv", "vak": "VII", "code": codes["decl_code_div_no_rv"],
        "label": "Dividenden waarop geen Belgische roerende voorheffing werd ingehouden",
        "amount": amt_no_rv, "kind": "aangeven", "verify": True,
        "explanation": (
            "Dividenden die je rechtstreeks bij een buitenlandse bank of broker ontving, "
            "zonder Belgische tussenpersoon die de roerende voorheffing inhield. Die moet "
            "je ZELF aangeven en er is 30% op verschuldigd. Het bedrag is het brutodividend "
            "NA de buitenlandse bronbelasting."),
        "rows": sorted(div_no_rv, key=lambda r: r["date"]),
    })

    # 2. Terug te vorderen RV binnen de vrijstelling
    lines.append({
        "key": "rv_refund", "vak": "VII", "code": codes["decl_code_rv_refund"],
        "label": "Terug te vorderen roerende voorheffing (vrijstelling gewone aandelen)",
        "amount": byear.get("reclaimable_rv", 0.0), "kind": "terugvorderen", "verify": False,
        "explanation": (
            f"De eerste {ben['cap_amount']:,.0f} EUR aan dividenden van GEWONE AANDELEN is "
            f"vrijgesteld ({ben['exemption_per_person']:,.0f} EUR × {ben['persons']} "
            "belastingplichtige(n)). Je vult hier de INGEHOUDEN VOORHEFFING in, niet het "
            "dividend zelf. Dividenden van fondsen, ETF's en beveks tellen niet mee."),
        "rows": sorted([r for r in div_with_rv
                        if r["asset_type"] == "stock" and r["kind"] == "dividend"],
                       key=lambda r: -r["be_rv_eur"]),
        "extra": {
            "In aanmerking komend brutobedrag": byear.get("qualifying_gross", 0.0),
            "Waarvan binnen de vrijstelling":   byear.get("eligible_gross", 0.0),
            "Ingehouden Belgische voorheffing": byear.get("be_rv_qualifying", 0.0),
            "Niet in aanmerking (fondsen/ETF)": byear.get("excluded_gross", 0.0),
        },
    })

    # 3. FBB (enkel wanneer ingeschakeld)
    if ben.get("fbb_enabled"):
        lines.append({
            "key": "fbb", "vak": "VII", "code": codes["decl_code_fbb"],
            "label": "Forfaitair gedeelte buitenlandse belasting (FBB) — Franse dividenden",
            "amount": byear.get("fbb", 0.0), "kind": "terugvorderen", "verify": True,
            "explanation": (
                f"{ben['fbb_rate'] * 100:.0f}% van het nettobedrag na Franse bronbelasting, "
                "op grond van het dubbelbelastingverdrag Belgie-Frankrijk. Dit is betwiste "
                "materie: bewaar je rekeninguittreksels als bewijs."),
            "rows": sorted([r for r in (div_no_rv + div_with_rv)
                            if r["country"] == "FR" and r["asset_type"] == "stock"
                            and r["kind"] == "dividend"], key=lambda r: r["date"]),
        })

    # 4. Meerwaardebelasting
    _applies = overview.get("regime_applicable", True)
    if _applies:
        _cgt_expl = (
            "Gerealiseerde meerwaarde van dit boekjaar na aftrek van de vrijstelling. "
            f"Verschuldigd: {overview.get('tax_due', 0.0):,.2f} EUR. Let op: dit is de "
            "berekening van de app; de aangiftecodes voor dit regime worden pas met het "
            "aangifteformulier zelf bekendgemaakt.")
    else:
        _cgt_expl = (
            f"In {year} bestond de meerwaardebelasting op financiele activa nog niet — "
            f"die geldt vanaf {overview.get('regime_start_year', 2026)}. Er is dus niets "
            "verschuldigd en niets aan te geven, ook niet op een meerwaarde van "
            f"{overview.get('total_taxable_gl', 0.0):,.2f} EUR.")
    lines.append({
        "key": "cgt", "vak": "—", "code": codes["decl_code_cgt"],
        "label": "Belastbare meerwaarde op financiele activa",
        "amount": overview.get("taxable_amount", 0.0), "kind": "aangeven",
        "verify": bool(_applies),
        "explanation": _cgt_expl,
        "rows": [],
        "extra": {
            "Gerealiseerd (fiscaal) dit jaar": overview.get("total_taxable_gl", 0.0),
            "Beschikbare vrijstelling":        overview.get("annual_exemption", 0.0),
            "Belastbaar na vrijstelling":      overview.get("taxable_amount", 0.0),
            "Verschuldigde belasting":         overview.get("tax_due", 0.0),
        },
    })

    notes = []
    if not div_no_rv and not div_with_rv:
        notes.append("Er zijn geen dividenden geregistreerd voor dit boekjaar.")
    if any(r["country"] not in ("BE", "") for r in div_no_rv + div_with_rv):
        notes.append("Je ontving buitenlandse dividenden. Houd je rekeninguittreksels bij "
                     "de hand: de fiscus kan de ingehouden bronbelasting laten bewijzen.")
    return {"year": year, "lines": lines, "notes": notes, "codes": codes,
            "benefit": ben, "overview": overview}
