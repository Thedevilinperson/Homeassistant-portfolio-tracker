"""
database.py — SQLite persistence layer voor Portfolio Tracker

Uitbreidingen:
  • account (rekening/oorsprong) per transactie
  • costs / costs_currency / costs_eur (kosten per transactie, apart van TOB)
  • total_amount_eur / fx_rate (alles wordt in EUR bijgehouden)
  • beheerbare rekeningenlijst in settings
"""
import sqlite3
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "portfolio.db")

DEFAULT_ACCOUNT = "Niet toegewezen"


def _ensure_data_dir():
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_data_dir()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables, run migrations and seed default settings."""
    _ensure_data_dir()
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS assets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT    NOT NULL UNIQUE,
            name        TEXT,
            asset_type  TEXT    DEFAULT 'stock',
            etf_subtype TEXT    DEFAULT 'distributing',
            currency    TEXT    DEFAULT 'EUR',
            exchange    TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker            TEXT    NOT NULL,
            transaction_type  TEXT    NOT NULL CHECK(transaction_type IN ('buy','sell')),
            date              TEXT    NOT NULL,
            quantity          REAL    NOT NULL CHECK(quantity > 0),
            price_per_unit    REAL    NOT NULL CHECK(price_per_unit > 0),
            total_amount      REAL    NOT NULL,
            currency          TEXT    DEFAULT 'EUR',
            tob_tax           REAL    DEFAULT 0,
            notes             TEXT,
            created_at        TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS dividends (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            date            TEXT    NOT NULL,
            gross_amount    REAL    NOT NULL CHECK(gross_amount > 0),
            withholding_tax REAL    DEFAULT 0,
            currency        TEXT    DEFAULT 'EUR',
            notes           TEXT,
            created_at      TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker    TEXT    NOT NULL,
            timestamp TEXT    NOT NULL,
            price     REAL    NOT NULL,
            currency  TEXT    DEFAULT 'EUR',
            UNIQUE(ticker, timestamp)
        );
        CREATE INDEX IF NOT EXISTS idx_price_ticker_ts ON price_history(ticker, timestamp);

        CREATE TABLE IF NOT EXISTS ai_evaluations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_type TEXT    NOT NULL,
            timing          TEXT,
            content         TEXT    NOT NULL,
            tickers         TEXT,
            created_at      TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS account_costs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            account     TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            amount      REAL    NOT NULL,
            currency    TEXT    DEFAULT 'EUR',
            amount_eur  REAL,
            fx_rate     REAL    DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ai_ratings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id     TEXT    NOT NULL,
            ticker       TEXT    NOT NULL,
            rating       TEXT    NOT NULL,
            price_target REAL,
            currency     TEXT    DEFAULT 'EUR',
            rationale    TEXT,
            model        TEXT,
            created_at   TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ai_ratings_batch ON ai_ratings(batch_id);
        CREATE INDEX IF NOT EXISTS idx_ai_ratings_ticker ON ai_ratings(ticker);

        CREATE TABLE IF NOT EXISTS ai_usage (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            function          TEXT,
            model             TEXT,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            cost_usd          REAL    DEFAULT 0,
            created_at        TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage(created_at);

        CREATE TABLE IF NOT EXISTS splits (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker     TEXT    NOT NULL,
            split_date TEXT    NOT NULL,
            ratio      REAL    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_splits_ticker ON splits(ticker);

        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        INSERT OR IGNORE INTO settings (key,value) VALUES
            ('capital_gains_tax_rate',      '0.10'),
            ('annual_exemption',            '10000'),
            ('tob_rate_stocks',             '0.0035'),
            ('tob_rate_etf_distributing',   '0.0012'),
            ('tob_rate_etf_accumulating',   '0.0132'),
            ('tob_max_stocks',              '1600'),
            ('tob_max_etf_distributing',    '1300'),
            ('tob_max_etf_accumulating',    '4000'),
            ('withholding_tax_rate',        '0.30'),
            ('base_currency',               'EUR'),
            ('accounts',                    'Niet toegewezen'),
            ('household_regime',            'single'),
            ('account_profiles',            '{}'),
            ('investment_volume_month',     '0'),
            ('investment_volume_year',      '0'),
            ('openai_price_target_model',   ''),
            ('anthropic_api_key',           ''),
            ('openai_api_key',              '');
    """)

    conn.commit()
    _migrate(conn)
    conn.close()


# ── Migraties ────────────────────────────────────────────────────────────────

def _column_exists(cur, table: str, col: str) -> bool:
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    return col in cols


def _migrate(conn):
    """Voeg ontbrekende kolommen toe (idempotent)."""
    cur = conn.cursor()

    txn_cols = [
        ("account",          f"TEXT DEFAULT '{DEFAULT_ACCOUNT}'"),
        ("costs",            "REAL DEFAULT 0"),
        ("costs_currency",   "TEXT DEFAULT 'EUR'"),
        ("costs_eur",        "REAL DEFAULT 0"),
        ("total_amount_eur", "REAL"),       # NULL bij oude rijen -> backfillen
        ("fx_rate",          "REAL DEFAULT 1"),
        ("price_target",     "REAL"),       # koersdoel (native munt), optioneel
    ]
    for col, ddl in txn_cols:
        if not _column_exists(cur, "transactions", col):
            cur.execute(f"ALTER TABLE transactions ADD COLUMN {col} {ddl}")

    div_cols = [
        ("fx_rate",          "REAL DEFAULT 1"),
        ("gross_eur",        "REAL"),
        ("withholding_eur",  "REAL"),
        ("foreign_wht_withheld", "INTEGER DEFAULT 0"),  # bronbelasting al ingehouden?
        ("belgian_rv_withheld",  "INTEGER DEFAULT 0"),  # roerende voorheffing al ingehouden?
        ("account",          "TEXT"),                   # rekening waarop het dividend is uitgekeerd
    ]
    new_div_cols = []
    for col, ddl in div_cols:
        if not _column_exists(cur, "dividends", col):
            cur.execute(f"ALTER TABLE dividends ADD COLUMN {col} {ddl}")
            new_div_cols.append(col)
    # Bestaande dividenden zonder rekening toewijzen aan de standaardrekening
    if "account" in new_div_cols:
        cur.execute("UPDATE dividends SET account=? WHERE account IS NULL OR account=''",
                    (DEFAULT_ACCOUNT,))

    # Assets: ISIN-kolom
    if not _column_exists(cur, "assets", "isin"):
        cur.execute("ALTER TABLE assets ADD COLUMN isin TEXT")

    # Assets: TOB — in België aangeboden/geregistreerd (FSMA)? (1=ja, default ja)
    if not _column_exists(cur, "assets", "belgian_registered"):
        cur.execute("ALTER TABLE assets ADD COLUMN belgian_registered INTEGER DEFAULT 1")

    # Zorg dat oude rijen een rekening hebben
    cur.execute(
        "UPDATE transactions SET account=? WHERE account IS NULL OR account=''",
        (DEFAULT_ACCOUNT,)
    )
    conn.commit()


# ── Settings ────────────────────────────────────────────────────────────────

def get_setting(key: str, default=None) -> str | None:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key,value,updated_at) VALUES (?,?,datetime('now'))",
        (key, str(value))
    )
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT key,value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ── Rekeningen ───────────────────────────────────────────────────────────────

def get_accounts() -> list[str]:
    """Lijst van rekeningnamen (oorsprong van de aandelen)."""
    raw = get_setting("accounts", DEFAULT_ACCOUNT) or DEFAULT_ACCOUNT
    accts = [a.strip() for a in raw.split("|") if a.strip()]
    if DEFAULT_ACCOUNT not in accts:
        accts.append(DEFAULT_ACCOUNT)
    return accts


def set_accounts(accounts: list[str]):
    cleaned = [a.strip() for a in accounts if a.strip()]
    if DEFAULT_ACCOUNT not in cleaned:
        cleaned.append(DEFAULT_ACCOUNT)
    set_setting("accounts", "|".join(dict.fromkeys(cleaned)))


def get_used_accounts() -> list[str]:
    """Rekeningen die daadwerkelijk in transacties voorkomen."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT account FROM transactions WHERE account IS NOT NULL ORDER BY account"
    ).fetchall()
    conn.close()
    return [r["account"] for r in rows]


# ── Rekeningprofielen (beleggingsprofiel per rekening) ───────────────────────

import json as _json

def get_account_profiles() -> dict:
    """{rekening: profielsleutel}."""
    raw = get_setting("account_profiles", "{}") or "{}"
    try:
        return _json.loads(raw)
    except Exception:
        return {}


def set_account_profile(account: str, profile: str):
    profiles = get_account_profiles()
    profiles[account] = profile
    set_setting("account_profiles", _json.dumps(profiles))


def get_account_profile(account: str, default: str = "neutral") -> str:
    return get_account_profiles().get(account, default)


# ── Rekeningkosten (algemene kosten, niet gelinkt aan een aandeel) ───────────

def add_account_cost(account, date, amount, currency="EUR", description=None,
                     fx_rate=1.0, amount_eur=None):
    if amount_eur is None:
        amount_eur = amount * (fx_rate or 1.0)
    conn = get_connection()
    conn.execute(
        """INSERT INTO account_costs
           (account,date,description,amount,currency,amount_eur,fx_rate)
           VALUES (?,?,?,?,?,?,?)""",
        (account, date, description, amount, currency, amount_eur, fx_rate)
    )
    conn.commit()
    conn.close()


def get_account_costs(account=None, year=None) -> list[dict]:
    conn = get_connection()
    q, p, conds = "SELECT * FROM account_costs", [], []
    if account: conds.append("account=?");             p.append(account)
    if year:    conds.append("strftime('%Y',date)=?"); p.append(str(year))
    if conds: q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY date DESC"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def total_account_costs_eur(account=None, year=None) -> float:
    return sum(c.get("amount_eur") or 0.0 for c in get_account_costs(account, year))


def delete_account_cost(cost_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM account_costs WHERE id=?", (cost_id,))
    conn.commit()
    conn.close()


# ── AI-ratings (gestructureerde adviezen per ticker) ─────────────────────────

def save_ai_rating(batch_id, ticker, rating, price_target=None,
                   currency="EUR", rationale=None, model=None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO ai_ratings
           (batch_id,ticker,rating,price_target,currency,rationale,model)
           VALUES (?,?,?,?,?,?,?)""",
        (batch_id, ticker.upper(), rating, price_target, currency, rationale, model)
    )
    conn.commit()
    conn.close()


def get_recent_rating_batches(limit: int = 9) -> list[str]:
    """De meest recente batch-id's (1 batch = 1 AI-advies-ronde)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT batch_id, MAX(created_at) AS ts, MAX(id) AS mid FROM ai_ratings "
        "GROUP BY batch_id ORDER BY ts DESC, mid DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [r["batch_id"] for r in rows]


def get_ai_ratings(batch_ids: list[str] | None = None,
                   ticker: str | None = None) -> list[dict]:
    conn = get_connection()
    q, p, conds = "SELECT * FROM ai_ratings", [], []
    if batch_ids:
        conds.append(f"batch_id IN ({','.join('?'*len(batch_ids))})")
        p.extend(batch_ids)
    if ticker:
        conds.append("ticker=?"); p.append(ticker.upper())
    if conds: q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY created_at DESC, id DESC"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_price_target(ticker: str) -> dict | None:
    """Meest recente AI-koersdoel voor een ticker (uit ai_ratings)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT price_target,currency,created_at FROM ai_ratings "
        "WHERE ticker=? AND price_target IS NOT NULL ORDER BY created_at DESC, id DESC LIMIT 1",
        (ticker.upper(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── AI-gebruik & kosten ───────────────────────────────────────────────────────

def record_ai_usage(function, model, prompt_tokens, completion_tokens, cost_usd):
    conn = get_connection()
    conn.execute(
        """INSERT INTO ai_usage
           (function,model,prompt_tokens,completion_tokens,cost_usd)
           VALUES (?,?,?,?,?)""",
        (function, model, int(prompt_tokens or 0), int(completion_tokens or 0),
         float(cost_usd or 0.0))
    )
    conn.commit()
    conn.close()


def get_ai_usage_summary() -> dict:
    """Totale en maandelijkse AI-kosten + uitsplitsing per model."""
    conn = get_connection()
    total = conn.execute(
        "SELECT COALESCE(SUM(cost_usd),0) c, COALESCE(SUM(prompt_tokens),0) pt, "
        "COALESCE(SUM(completion_tokens),0) ct, COUNT(*) n FROM ai_usage"
    ).fetchone()
    month = conn.execute(
        "SELECT COALESCE(SUM(cost_usd),0) c, COUNT(*) n FROM ai_usage "
        "WHERE strftime('%Y-%m',created_at)=strftime('%Y-%m','now')"
    ).fetchone()
    by_model = conn.execute(
        "SELECT model, COUNT(*) n, COALESCE(SUM(prompt_tokens),0) pt, "
        "COALESCE(SUM(completion_tokens),0) ct, COALESCE(SUM(cost_usd),0) c "
        "FROM ai_usage GROUP BY model ORDER BY c DESC"
    ).fetchall()
    by_func = conn.execute(
        "SELECT function, COUNT(*) n, COALESCE(SUM(cost_usd),0) c "
        "FROM ai_usage GROUP BY function ORDER BY c DESC"
    ).fetchall()
    conn.close()
    return {
        "total_cost_usd":  total["c"],
        "total_calls":     total["n"],
        "total_prompt_tokens":     total["pt"],
        "total_completion_tokens": total["ct"],
        "month_cost_usd":  month["c"],
        "month_calls":     month["n"],
        "by_model":        [dict(r) for r in by_model],
        "by_function":     [dict(r) for r in by_func],
    }


# ── Assets ──────────────────────────────────────────────────────────────────

def add_asset(ticker, name, asset_type="stock", etf_subtype="distributing",
              currency="EUR", exchange=None, isin=None, belgian_registered=1):
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO assets
           (ticker,name,asset_type,etf_subtype,currency,exchange,isin,belgian_registered)
           VALUES (?,?,?,?,?,?,?,?)""",
        (ticker.upper(), name, asset_type, etf_subtype, currency, exchange, isin,
         int(belgian_registered))
    )
    conn.commit()
    conn.close()


def update_asset(ticker, name=None, asset_type=None, etf_subtype=None,
                 currency=None, exchange=None, isin=None, belgian_registered=None):
    conn = get_connection()
    fields, vals = [], []
    if name        is not None: fields.append("name=?");        vals.append(name)
    if asset_type  is not None: fields.append("asset_type=?");  vals.append(asset_type)
    if etf_subtype is not None: fields.append("etf_subtype=?"); vals.append(etf_subtype)
    if currency    is not None: fields.append("currency=?");    vals.append(currency)
    if exchange    is not None: fields.append("exchange=?");    vals.append(exchange)
    if isin        is not None: fields.append("isin=?");        vals.append(isin)
    if belgian_registered is not None:
        fields.append("belgian_registered=?"); vals.append(int(belgian_registered))
    if fields:
        vals.append(ticker.upper())
        conn.execute(f"UPDATE assets SET {','.join(fields)} WHERE ticker=?", vals)
        conn.commit()
    conn.close()


def get_assets() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM assets ORDER BY ticker").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_asset(ticker: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM assets WHERE ticker=?", (ticker.upper(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def rename_ticker(old: str, new: str) -> bool:
    """Hernoem een ticker overal (assets + transacties + dividenden +
    koershistoriek + AI-ratings). Geeft False als de nieuwe ticker al bestaat."""
    o, n = old.upper(), new.upper()
    if o == n:
        return True
    conn = get_connection()
    exists = conn.execute("SELECT 1 FROM assets WHERE ticker=?", (n,)).fetchone()
    if exists:
        conn.close()
        return False
    for tbl in ("assets", "transactions", "dividends", "price_history", "ai_ratings"):
        conn.execute(f"UPDATE {tbl} SET ticker=? WHERE ticker=?", (n, o))
    conn.commit()
    conn.close()
    return True


def delete_asset(ticker: str):
    conn = get_connection()
    t = ticker.upper()
    conn.execute("DELETE FROM price_history WHERE ticker=?", (t,))
    conn.execute("DELETE FROM dividends WHERE ticker=?", (t,))
    conn.execute("DELETE FROM transactions WHERE ticker=?", (t,))
    conn.execute("DELETE FROM assets WHERE ticker=?", (t,))
    conn.commit()
    conn.close()


# ── Transactions ─────────────────────────────────────────────────────────────

def add_transaction(ticker, transaction_type, date, quantity, price_per_unit,
                    total_amount, currency="EUR", tob_tax=0.0, notes=None,
                    account=DEFAULT_ACCOUNT, costs=0.0, costs_currency="EUR",
                    fx_rate=1.0, total_amount_eur=None, costs_eur=None,
                    price_target=None):
    if total_amount_eur is None:
        total_amount_eur = total_amount * (fx_rate or 1.0)
    if costs_eur is None:
        costs_eur = 0.0
    conn = get_connection()
    conn.execute(
        """INSERT INTO transactions
           (ticker,transaction_type,date,quantity,price_per_unit,total_amount,
            currency,tob_tax,notes,account,costs,costs_currency,costs_eur,
            total_amount_eur,fx_rate,price_target)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ticker.upper(), transaction_type, date, quantity, price_per_unit,
         total_amount, currency, tob_tax, notes, account, costs, costs_currency,
         costs_eur, total_amount_eur, fx_rate, price_target)
    )
    conn.commit()
    conn.close()


def update_transaction(txn_id: int, **fields):
    """Werk willekeurige velden van een transactie bij (voor correcties)."""
    allowed = {"ticker", "transaction_type", "date", "quantity", "price_per_unit",
               "total_amount", "currency", "tob_tax", "notes", "account", "costs",
               "costs_currency", "costs_eur", "total_amount_eur", "fx_rate",
               "price_target"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v.upper() if k == "ticker" and isinstance(v, str) else v)
    if not sets:
        return
    vals.append(txn_id)
    conn = get_connection()
    conn.execute(f"UPDATE transactions SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()


def get_transactions(ticker=None, year=None, txn_type=None, account=None,
                     adjusted=True) -> list[dict]:
    conn = get_connection()
    q, p = "SELECT * FROM transactions", []
    conds = []
    if ticker:   conds.append("ticker=?");              p.append(ticker.upper())
    if year:     conds.append("strftime('%Y',date)=?"); p.append(str(year))
    if txn_type: conds.append("transaction_type=?");    p.append(txn_type)
    if account:  conds.append("account=?");             p.append(account)
    if conds: q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY date ASC"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    txns = [dict(r) for r in rows]
    return _apply_splits(txns) if adjusted else txns


# ── Aandelensplitsingen ───────────────────────────────────────────────────────

def add_split(ticker, split_date, ratio):
    conn = get_connection()
    conn.execute("INSERT INTO splits (ticker,split_date,ratio) VALUES (?,?,?)",
                 (ticker.upper(), split_date, float(ratio)))
    conn.commit()
    conn.close()


def get_splits(ticker=None) -> list[dict]:
    conn = get_connection()
    if ticker:
        rows = conn.execute("SELECT * FROM splits WHERE ticker=? ORDER BY split_date",
                            (ticker.upper(),)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM splits ORDER BY ticker, split_date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_split(split_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM splits WHERE id=?", (split_id,))
    conn.commit()
    conn.close()


def _all_splits_map() -> dict:
    """{ticker: [(split_date, ratio), ...]} — leeg als er geen splits zijn."""
    out: dict[str, list] = {}
    for s in get_splits():
        out.setdefault(s["ticker"], []).append((s["split_date"], float(s["ratio"])))
    return out


def _apply_splits(txns: list[dict]) -> list[dict]:
    """Pas geregistreerde splitsingen toe op transacties die vóór de splitsdatum
    vallen: aantal × ratio, prijs ÷ ratio (kostbasis blijft gelijk). Yahoo-koersen
    zijn al split-gecorrigeerd, dus zo blijven posities en waarde consistent."""
    smap = _all_splits_map()
    if not smap:
        return txns
    for t in txns:
        splits = smap.get(t["ticker"])
        if not splits:
            continue
        factor = 1.0
        tdate = (t.get("date") or "")[:10]
        for sdate, ratio in splits:
            if tdate < sdate[:10] and ratio:      # gekocht/verkocht vóór de splitsing
                factor *= ratio
        if factor != 1.0:
            if t.get("quantity") is not None:
                t["quantity"] = t["quantity"] * factor
            if t.get("price_per_unit") is not None:
                t["price_per_unit"] = t["price_per_unit"] / factor
            if t.get("price_target"):
                t["price_target"] = t["price_target"] / factor
            t["_split_factor"] = factor          # markering voor weergave
    return txns


def update_transaction_account(txn_id: int, account: str):
    conn = get_connection()
    conn.execute("UPDATE transactions SET account=? WHERE id=?", (account, txn_id))
    conn.commit()
    conn.close()


def set_transaction_eur(txn_id: int, fx_rate: float, total_amount_eur: float,
                        costs_eur: float):
    conn = get_connection()
    conn.execute(
        "UPDATE transactions SET fx_rate=?, total_amount_eur=?, costs_eur=? WHERE id=?",
        (fx_rate, total_amount_eur, costs_eur, txn_id)
    )
    conn.commit()
    conn.close()


def delete_transaction(txn_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM transactions WHERE id=?", (txn_id,))
    conn.commit()
    conn.close()


# ── Dividends ────────────────────────────────────────────────────────────────

def add_dividend(ticker, date, gross_amount, withholding_tax=0.0,
                 currency="EUR", notes=None, fx_rate=1.0,
                 gross_eur=None, withholding_eur=None,
                 foreign_wht_withheld=0, belgian_rv_withheld=0,
                 account=None):
    if gross_eur is None:
        gross_eur = gross_amount * (fx_rate or 1.0)
    if withholding_eur is None:
        withholding_eur = withholding_tax * (fx_rate or 1.0)
    if not account:
        account = DEFAULT_ACCOUNT
    conn = get_connection()
    conn.execute(
        """INSERT INTO dividends
           (ticker,date,gross_amount,withholding_tax,currency,notes,
            fx_rate,gross_eur,withholding_eur,
            foreign_wht_withheld,belgian_rv_withheld,account)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ticker.upper(), date, gross_amount, withholding_tax, currency, notes,
         fx_rate, gross_eur, withholding_eur,
         int(foreign_wht_withheld), int(belgian_rv_withheld), account)
    )
    conn.commit()
    conn.close()


def get_dividends(ticker=None, year=None, account=None) -> list[dict]:
    conn = get_connection()
    q, p = "SELECT * FROM dividends", []
    conds = []
    if ticker:  conds.append("ticker=?");             p.append(ticker.upper())
    if year:    conds.append("strftime('%Y',date)=?"); p.append(str(year))
    if account: conds.append("account=?");            p.append(account)
    if conds: q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY date DESC"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_dividend_account(div_id: int, account: str):
    conn = get_connection()
    conn.execute("UPDATE dividends SET account=? WHERE id=?", (account, div_id))
    conn.commit()
    conn.close()


def delete_dividend(div_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM dividends WHERE id=?", (div_id,))
    conn.commit()
    conn.close()


def set_dividend_eur(div_id: int, fx_rate: float, gross_eur: float,
                     withholding_eur: float):
    conn = get_connection()
    conn.execute(
        "UPDATE dividends SET fx_rate=?, gross_eur=?, withholding_eur=? WHERE id=?",
        (fx_rate, gross_eur, withholding_eur, div_id)
    )
    conn.commit()
    conn.close()


# ── Price history ────────────────────────────────────────────────────────────

def save_price(ticker: str, price: float, currency: str = "EUR"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:00")
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO price_history (ticker,timestamp,price,currency) VALUES (?,?,?,?)",
        (ticker.upper(), ts, price, currency)
    )
    conn.commit()
    conn.close()


def get_latest_price(ticker: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT price,currency,timestamp FROM price_history WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
        (ticker.upper(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_price_history(ticker: str, days: int = 30) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT timestamp,price,currency FROM price_history
           WHERE ticker=? AND timestamp>=datetime('now',? || ' days')
           ORDER BY timestamp ASC""",
        (ticker.upper(), f"-{days}")
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── AI Evaluations ───────────────────────────────────────────────────────────

def save_ai_evaluation(evaluation_type: str, content: str,
                       timing: str = None, tickers: str = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO ai_evaluations (evaluation_type,timing,content,tickers) VALUES (?,?,?,?)",
        (evaluation_type, timing, content, tickers)
    )
    conn.commit()
    conn.close()


def get_ai_evaluations(evaluation_type: str = None, limit: int = 10) -> list[dict]:
    conn = get_connection()
    q, p = "SELECT * FROM ai_evaluations", []
    if evaluation_type:
        q += " WHERE evaluation_type=?"
        p.append(evaluation_type)
    q += " ORDER BY created_at DESC LIMIT ?"
    p.append(limit)
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cleanup_old_prices(keep_days: int = 90):
    conn = get_connection()
    conn.execute(
        "DELETE FROM price_history WHERE timestamp < datetime('now', ? || ' days')",
        (f"-{keep_days}",)
    )
    conn.commit()
    conn.close()