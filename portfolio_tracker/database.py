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
    ]
    for col, ddl in txn_cols:
        if not _column_exists(cur, "transactions", col):
            cur.execute(f"ALTER TABLE transactions ADD COLUMN {col} {ddl}")

    div_cols = [
        ("fx_rate",          "REAL DEFAULT 1"),
        ("gross_eur",        "REAL"),
        ("withholding_eur",  "REAL"),
    ]
    for col, ddl in div_cols:
        if not _column_exists(cur, "dividends", col):
            cur.execute(f"ALTER TABLE dividends ADD COLUMN {col} {ddl}")

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


# ── Assets ──────────────────────────────────────────────────────────────────

def add_asset(ticker, name, asset_type="stock", etf_subtype="distributing",
              currency="EUR", exchange=None):
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO assets (ticker,name,asset_type,etf_subtype,currency,exchange)
           VALUES (?,?,?,?,?,?)""",
        (ticker.upper(), name, asset_type, etf_subtype, currency, exchange)
    )
    conn.commit()
    conn.close()


def update_asset(ticker, name=None, asset_type=None, etf_subtype=None, currency=None):
    conn = get_connection()
    fields, vals = [], []
    if name        is not None: fields.append("name=?");        vals.append(name)
    if asset_type  is not None: fields.append("asset_type=?");  vals.append(asset_type)
    if etf_subtype is not None: fields.append("etf_subtype=?"); vals.append(etf_subtype)
    if currency    is not None: fields.append("currency=?");     vals.append(currency)
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
                    fx_rate=1.0, total_amount_eur=None, costs_eur=None):
    if total_amount_eur is None:
        total_amount_eur = total_amount * (fx_rate or 1.0)
    if costs_eur is None:
        costs_eur = 0.0
    conn = get_connection()
    conn.execute(
        """INSERT INTO transactions
           (ticker,transaction_type,date,quantity,price_per_unit,total_amount,
            currency,tob_tax,notes,account,costs,costs_currency,costs_eur,
            total_amount_eur,fx_rate)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ticker.upper(), transaction_type, date, quantity, price_per_unit,
         total_amount, currency, tob_tax, notes, account, costs, costs_currency,
         costs_eur, total_amount_eur, fx_rate)
    )
    conn.commit()
    conn.close()


def get_transactions(ticker=None, year=None, txn_type=None, account=None) -> list[dict]:
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
    return [dict(r) for r in rows]


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
                 gross_eur=None, withholding_eur=None):
    if gross_eur is None:
        gross_eur = gross_amount * (fx_rate or 1.0)
    if withholding_eur is None:
        withholding_eur = withholding_tax * (fx_rate or 1.0)
    conn = get_connection()
    conn.execute(
        """INSERT INTO dividends
           (ticker,date,gross_amount,withholding_tax,currency,notes,
            fx_rate,gross_eur,withholding_eur)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (ticker.upper(), date, gross_amount, withholding_tax, currency, notes,
         fx_rate, gross_eur, withholding_eur)
    )
    conn.commit()
    conn.close()


def get_dividends(ticker=None, year=None) -> list[dict]:
    conn = get_connection()
    q, p = "SELECT * FROM dividends", []
    conds = []
    if ticker: conds.append("ticker=?");             p.append(ticker.upper())
    if year:   conds.append("strftime('%Y',date)=?"); p.append(str(year))
    if conds: q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY date DESC"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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