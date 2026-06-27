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
import database as db
import market_data


# ── TOB berekening ────────────────────────────────────────────────────────────

def calculate_tob(asset_type: str, etf_subtype: str, total_amount: float) -> float:
    s = db.get_all_settings()
    if asset_type == "etf":
        if etf_subtype == "accumulating":
            rate    = float(s.get("tob_rate_etf_accumulating", "0.0132"))
            max_tob = float(s.get("tob_max_etf_accumulating", "4000"))
        else:
            rate    = float(s.get("tob_rate_etf_distributing", "0.0012"))
            max_tob = float(s.get("tob_max_etf_distributing", "1300"))
    else:
        rate    = float(s.get("tob_rate_stocks", "0.0035"))
        max_tob = float(s.get("tob_max_stocks", "1600"))
    return round(min(total_amount * rate, max_tob), 2)


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

def _fifo_core(transactions: list[dict]):
    """
    Verwerk transacties chronologisch via FIFO per (ticker, rekening).

    Returns:
      pos_by_key   : {(ticker, account): {lots, total_quantity, total_cost}}
      realized     : lijst gerealiseerde W/V (EUR), met 'account'
      costs_by_key : {(ticker, account): som costs_eur}  (alle transacties)
    """
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
            })
            pos["total_quantity"] += qty
            pos["total_cost"]     += eur_total

        else:  # sell
            sell_qty   = qty
            sell_total = eur_total          # EUR opbrengst (kosten apart)
            remaining  = sell_qty
            cost_basis = 0.0
            for lot in pos["lots"]:
                if remaining <= 0:
                    break
                if lot["remaining_quantity"] <= 0:
                    continue
                consumed = min(lot["remaining_quantity"], remaining)
                cost_basis               += consumed * lot["price_per_unit"]
                lot["remaining_quantity"] -= consumed
                remaining                -= consumed

            realized.append({
                "ticker":     ticker,
                "account":    acct,
                "date":       txn["date"],
                "year":       _year(txn["date"]),
                "quantity":   sell_qty,
                "sell_price": price_eur,
                "sell_total": sell_total,
                "cost_basis": cost_basis,
                "gain_loss":  sell_total - cost_basis,   # kosten tellen NIET mee
            })
            pos["total_quantity"] = max(0.0, pos["total_quantity"] - sell_qty)
            pos["total_cost"]     = max(0.0, pos["total_cost"]     - cost_basis)

    return pos_by_key, realized, costs_by_key


def build_fifo_positions(transactions: list[dict]) -> tuple[dict, list[dict]]:
    """
    Backward-compatibele weergave: posities geaggregeerd per ticker
    (over alle rekeningen heen). Realized blijft een platte lijst (met account).
    """
    pos_by_key, realized, _ = _fifo_core(transactions)
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


def total_costs_eur(transactions: list[dict]) -> float:
    """Som van alle transactiekosten in EUR (apart van de belasting)."""
    return sum(float(t.get("costs_eur") or 0.0) for t in transactions)


# ── Portefeuillewaarde (EUR) ──────────────────────────────────────────────────

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
    """Netto gerealiseerde W/V per boekjaar (kan negatief zijn)."""
    out: dict[int, float] = {}
    for g in all_gains:
        out[g["year"]] = out.get(g["year"], 0.0) + g["gain_loss"]
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
                            account: str | None = None) -> dict:
    """
    Belastingoverzicht voor een boekjaar.

    De belasting (gerealiseerde W/V, vrijstelling) is ALTIJD globaal over alle
    rekeningen — de €-vrijstelling geldt per belastingplichtige. De 'account'-
    filter beïnvloedt alleen de getoonde posities/waarde (portefeuillekant).
    """
    if year is None:
        year = datetime.now().year

    s         = db.get_all_settings()
    tax_rate  = float(s.get("capital_gains_tax_rate", "0.10"))
    base_exemption  = float(s.get("annual_exemption", "10000"))
    regime          = s.get("household_regime", "single")
    exemption_count = 2 if regime == "community" else 1

    all_txns = db.get_transactions()                      # globaal -> belasting
    _, all_gains = build_fifo_positions(all_txns)

    # Meerjarige opbouw van de vrijstelling (overdracht ongebruikt deel, max 5 jaar)
    gains_by_year = realized_gains_by_year(all_gains)
    first_year = None
    if all_txns:
        first_year = min(int(t["date"][:4]) for t in all_txns)
    exm = available_exemption(gains_by_year, year, base_exemption,
                              exemption_count, first_year)
    exemption       = exm["effective_total"]             # basis + opbouw, × aantal partners

    year_gains    = [g for g in all_gains if g["year"] == year]
    total_real_gl = sum(g["gain_loss"] for g in year_gains)
    taxable       = max(0.0, total_real_gl - exemption) if total_real_gl > 0 else 0.0
    tax_due       = round(taxable * tax_rate, 2)

    # Dividenden dit boekjaar (EUR)
    divs      = db.get_dividends(year=year)
    gross_div = sum((d.get("gross_eur") if d.get("gross_eur") is not None
                     else d["gross_amount"]) for d in divs)
    wh_tax    = sum((d.get("withholding_eur") if d.get("withholding_eur") is not None
                     else d["withholding_tax"]) for d in divs)
    net_div   = gross_div - wh_tax

    # Posities (eventueel gefilterd op rekening)
    display_txns = db.get_transactions(account=account) if account else all_txns
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
    acct_costs_sel   = db.total_account_costs_eur(account=account) if account else acct_costs_total
    acct_costs_year  = db.total_account_costs_eur(year=year)

    return {
        "year":                  year,
        "account_filter":        account,
        "realized_gains":        year_gains,
        "total_realized_gl":     total_real_gl,
        "annual_exemption":      exemption,
        "base_exemption":        base_exemption,
        "base_exemption_effective": exm["base_effective"],
        "carry_exemption":       exm["carry_effective"],
        "exemption_count":       exemption_count,
        "household_regime":      regime,
        "taxable_amount":        taxable,
        "tax_rate":              tax_rate,
        "tax_due":               tax_due,
        "remaining_exemption":   max(0.0, exemption - total_real_gl) if total_real_gl >= 0 else exemption,
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