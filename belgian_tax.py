"""
belgian_tax.py — Belgische meerwaardebelasting (opt-out stelsel)

Regels (De Wever-hervormingen, 10% CGT):
  • 10% meerwaardebelasting op gerealiseerde nettomeerwaarden
  • Jaarlijkse vrijstelling per belastingplichtige (instelbaar, standaard €10.000)
  • Minwaarden worden verrekend met meerwaarden binnen hetzelfde boekjaar
  • FIFO-methode voor kostprijsbepaling
  • TOB (Taks op Beursverrichtingen) apart berekend per transactie
  • Roerende voorheffing (30%) op dividenden — reeds ingehouden aan de bron
"""
from __future__ import annotations

from datetime import datetime
import database as db
import market_data


# ── TOB berekening ────────────────────────────────────────────────────────────

def calculate_tob(asset_type: str, etf_subtype: str, total_amount: float) -> float:
    """
    Bereken TOB op een transactie.
    asset_type : 'stock' | 'etf'
    etf_subtype: 'distributing' | 'accumulating'
    """
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


# ── FIFO posities ─────────────────────────────────────────────────────────────

def build_fifo_positions(transactions: list[dict]) -> tuple[dict, list[dict]]:
    """
    Verwerk alle transacties chronologisch via FIFO.

    Geeft terug:
      positions      : {ticker: {'lots': [...], 'total_quantity', 'total_cost'}}
      realized_gains : lijst van gerealiseerde winst/verliesgebeurtenissen
    """
    # Sorteer op datum oplopend
    txns = sorted(transactions, key=lambda x: x["date"])

    positions: dict[str, dict] = {}
    realized_gains: list[dict] = []

    for txn in txns:
        ticker = txn["ticker"]
        if ticker not in positions:
            positions[ticker] = {"lots": [], "total_quantity": 0.0, "total_cost": 0.0}

        pos = positions[ticker]

        if txn["transaction_type"] == "buy":
            pos["lots"].append({
                "date":               txn["date"],
                "quantity":           txn["quantity"],
                "remaining_quantity": txn["quantity"],
                "price_per_unit":     txn["price_per_unit"],
                "total_cost":         txn["total_amount"],
                "currency":           txn.get("currency", "EUR"),
            })
            pos["total_quantity"] += txn["quantity"]
            pos["total_cost"]     += txn["total_amount"]

        elif txn["transaction_type"] == "sell":
            sell_qty   = txn["quantity"]
            sell_price = txn["price_per_unit"]
            sell_total = txn["total_amount"]
            txn_year   = _year(txn["date"])
            remaining  = sell_qty
            cost_basis = 0.0

            for lot in pos["lots"]:
                if remaining <= 0:
                    break
                if lot["remaining_quantity"] <= 0:
                    continue
                consumed = min(lot["remaining_quantity"], remaining)
                cost_basis             += consumed * lot["price_per_unit"]
                lot["remaining_quantity"] -= consumed
                remaining              -= consumed

            gain_loss = sell_total - cost_basis
            realized_gains.append({
                "ticker":     ticker,
                "date":       txn["date"],
                "year":       txn_year,
                "quantity":   sell_qty,
                "sell_price": sell_price,
                "sell_total": sell_total,
                "cost_basis": cost_basis,
                "gain_loss":  gain_loss,
            })

            pos["total_quantity"] = max(0.0, pos["total_quantity"] - sell_qty)
            pos["total_cost"]     = max(0.0, pos["total_cost"]     - cost_basis)

    return positions, realized_gains


def _year(date_str: str) -> int:
    fmt = "%Y-%m-%d %H:%M:%S" if " " in date_str else "%Y-%m-%d"
    return datetime.strptime(date_str[:19] if " " in date_str else date_str[:10], fmt).year


# ── Portefeuillewaarde ────────────────────────────────────────────────────────

def get_position_values(positions: dict, current_prices: dict) -> dict[str, dict]:
    """
    Bereken actuele waarde en ongerealiseerde P&L per positie.
    current_prices: {ticker: {'price': float|None, 'currency': str}}
    """
    result = {}
    for ticker, pos in positions.items():
        qty  = pos["total_quantity"]
        cost = pos["total_cost"]

        if qty <= 0:
            continue

        avg_cost     = cost / qty if qty > 0 else 0.0
        price_info   = current_prices.get(ticker, {})
        curr_price   = price_info.get("price")
        currency     = price_info.get("currency", "EUR")

        if curr_price is not None:
            curr_value   = qty * curr_price
            unreal_gl    = curr_value - cost
            unreal_gl_pct = (unreal_gl / cost * 100) if cost > 0 else 0.0
        else:
            curr_value   = None
            unreal_gl    = None
            unreal_gl_pct = None

        result[ticker] = {
            "quantity":              qty,
            "avg_cost":              avg_cost,
            "total_cost":            cost,
            "current_price":         curr_price,
            "current_price_currency": currency,
            "current_value":         curr_value,
            "unrealized_gain_loss":  unreal_gl,
            "unrealized_gain_loss_pct": unreal_gl_pct,
        }
    return result


# ── Meerwaardebelasting ───────────────────────────────────────────────────────

def calculate_tax_overview(year: int | None = None,
                            current_prices: dict | None = None) -> dict:
    """
    Volledig belastingoverzicht voor een boekjaar.

    Geeft terug:
      year, realized_gains, total_realized_gl,
      annual_exemption, taxable_amount, tax_rate, tax_due,
      total_dividends_gross, total_withholding_tax, total_dividends_net,
      unrealized_gl, total_portfolio_value, total_cost_basis,
      positions (raw), position_values
    """
    if year is None:
        year = datetime.now().year

    s          = db.get_all_settings()
    tax_rate   = float(s.get("capital_gains_tax_rate", "0.10"))
    exemption  = float(s.get("annual_exemption", "10000"))

    all_txns   = db.get_transactions()
    positions, all_gains = build_fifo_positions(all_txns)

    # Gerealiseerde winsten/verliezen van dit boekjaar
    year_gains     = [g for g in all_gains if g["year"] == year]
    total_real_gl  = sum(g["gain_loss"] for g in year_gains)

    # Belastbaar bedrag (enkel als netto meerwaarde > vrijstelling)
    if total_real_gl > 0:
        taxable   = max(0.0, total_real_gl - exemption)
    else:
        taxable   = 0.0

    tax_due = round(taxable * tax_rate, 2)

    # Dividenden dit boekjaar
    divs = db.get_dividends(year=year)
    gross_div   = sum(d["gross_amount"]    for d in divs)
    wh_tax      = sum(d["withholding_tax"] for d in divs)
    net_div     = gross_div - wh_tax

    # Ongerealiseerde P&L
    if current_prices is None:
        assets  = db.get_assets()
        tickers = [a["ticker"] for a in assets]
        current_prices = market_data.get_prices_for_tickers(tickers)

    pos_values      = get_position_values(positions, current_prices)
    total_curr_val  = sum(p["current_value"] for p in pos_values.values() if p["current_value"])
    total_cost_bas  = sum(p["total_cost"]    for p in pos_values.values())
    total_unreal_gl = sum(
        p["unrealized_gain_loss"] for p in pos_values.values()
        if p["unrealized_gain_loss"] is not None
    )

    return {
        "year":                  year,
        "realized_gains":        year_gains,
        "total_realized_gl":     total_real_gl,
        "annual_exemption":      exemption,
        "taxable_amount":        taxable,
        "tax_rate":              tax_rate,
        "tax_due":               tax_due,
        "remaining_exemption":   max(0.0, exemption - total_real_gl) if total_real_gl >= 0 else exemption,
        "total_dividends_gross": gross_div,
        "total_withholding_tax": wh_tax,
        "total_dividends_net":   net_div,
        "total_portfolio_value": total_curr_val,
        "total_cost_basis":      total_cost_bas,
        "unrealized_gl":         total_unreal_gl,
        "positions":             positions,
        "position_values":       pos_values,
    }
