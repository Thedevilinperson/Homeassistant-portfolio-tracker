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
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

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
            price_per_unit    REAL    NOT NULL CHECK(price_per_unit >= 0),
            total_amount      REAL    NOT NULL,
            currency          TEXT    DEFAULT 'EUR',
            tob_tax           REAL    DEFAULT 0,
            notes             TEXT,
            created_at        TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS dividends (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT,
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

        CREATE TABLE IF NOT EXISTS price_target_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker    TEXT    NOT NULL,
            target    REAL    NOT NULL,      -- koersdoel in de native munt
            currency  TEXT    DEFAULT 'EUR',
            source    TEXT    NOT NULL,      -- 'manual' | 'ai'
            note      TEXT,                  -- bv. AI-model of 'via transactie'
            set_at    TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_pth_ticker ON price_target_history(ticker, set_at);

        CREATE TABLE IF NOT EXISTS status_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT    NOT NULL,
            isin        TEXT,
            kind        TEXT    NOT NULL,   -- stale_price|flat_price|ticker_change|split|name_change
            severity    TEXT    DEFAULT 'warning',  -- info|warning|error
            message     TEXT,
            detail      TEXT,               -- JSON met specifieke gegevens
            detected_at TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now')),
            resolved_at TEXT,               -- gevuld wanneer de toestand niet meer geldt
            acknowledged INTEGER DEFAULT 0  -- door de gebruiker afgevinkt
        );
        CREATE INDEX IF NOT EXISTS idx_status_open ON status_events(ticker, kind, resolved_at);

        CREATE TABLE IF NOT EXISTS market_ideas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id        TEXT    NOT NULL,
            idea_date       TEXT    NOT NULL,   -- YYYY-MM-DD
            bucket          TEXT    NOT NULL,   -- defensive | moderate | speculative
            ticker          TEXT    NOT NULL,   -- Yahoo-symbool (met beurssuffix)
            name            TEXT,
            exchange        TEXT,
            isin            TEXT,
            currency        TEXT    DEFAULT 'EUR',
            rating          TEXT,               -- strong_buy .. strong_sell
            price_at_advice REAL,               -- koers (native) op het moment van het advies
            price_target    REAL,
            dividend_yield  REAL,
            horizon         TEXT,
            rationale       TEXT,
            catalysts       TEXT,
            risks           TEXT,
            model           TEXT,
            created_at      TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_market_ideas_date ON market_ideas(idea_date);
        CREATE INDEX IF NOT EXISTS idx_market_ideas_ticker ON market_ideas(ticker);
        CREATE INDEX IF NOT EXISTS idx_market_ideas_batch ON market_ideas(batch_id);

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

        CREATE TABLE IF NOT EXISTS cash_movements (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            account       TEXT    NOT NULL,
            date          TEXT    NOT NULL,
            type          TEXT    NOT NULL,          -- 'deposit' (storting) | 'withdrawal' (opname)
            amount_native REAL    NOT NULL,
            currency      TEXT    DEFAULT 'EUR',
            fx_rate       REAL    DEFAULT 1,
            amount_eur    REAL    NOT NULL,
            note          TEXT,
            created_at    TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cash_account ON cash_movements(account);

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
            ('status_stale_days',           '4'),
            ('euronext_aes_key',            ''),
            ('euronext_aes_iv',             ''),
            ('euronext_key_fingerprint',    ''),
            ('euronext_key_checked',        ''),
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
        ("is_performance_share", "INTEGER DEFAULT 0"),  # toegekend (vesting) i.p.v. gekocht
        ("income_tax_eur",       "REAL DEFAULT 0"),     # personenbelasting bij vesting (EUR)
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
        # Gedetailleerde keten (elk veld optioneel, met eigen munt); netto in EUR
        ("gross_before_wht",     "REAL"),  # A: bruto vóór buitenlandse bronbelasting
        ("gross_before_wht_cur", "TEXT"),
        ("foreign_wht_amt",      "REAL"),  # B: buitenlandse bronbelasting
        ("foreign_wht_cur",      "TEXT"),
        ("gross_after_wht",      "REAL"),  # C: bruto na bronbelasting / vóór Belgische RV
        ("gross_after_wht_cur",  "TEXT"),
        ("belgian_rv_amt",       "REAL"),  # Belgische roerende voorheffing (= C - D)
        ("net_received",         "REAL"),  # D: netto na alle voorheffingen
        ("net_received_cur",     "TEXT"),
        ("net_eur",              "REAL"),  # D in EUR (authoritatief voor totalen)
        ("cash_basis",           "TEXT DEFAULT 'net'"),  # welk veld naar de cashbalans gaat: net/gross_after/gross_before
        ("cash_eur",             "REAL"),                # het gekozen cashbedrag in EUR
        ("kind",                 "TEXT DEFAULT 'dividend'"),  # dividend / interest / securities_lending
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

    # Assets: land van herkomst (voor buitenlandse bronbelasting op dividenden)
    if not _column_exists(cur, "assets", "country"):
        cur.execute("ALTER TABLE assets ADD COLUMN country TEXT DEFAULT 'BE'")

    # Assets: TOB — in België aangeboden/geregistreerd (FSMA)? (1=ja, default ja)
    if not _column_exists(cur, "assets", "belgian_registered"):
        cur.execute("ALTER TABLE assets ADD COLUMN belgian_registered INTEGER DEFAULT 1")

    # Assets: fotomoment (slotkoers 31/12/2025) — native + EUR
    if not _column_exists(cur, "assets", "snapshot_price"):
        cur.execute("ALTER TABLE assets ADD COLUMN snapshot_price REAL")
    if not _column_exists(cur, "assets", "snapshot_price_eur"):
        cur.execute("ALTER TABLE assets ADD COLUMN snapshot_price_eur REAL")
    # Handmatige koers (voor effecten zonder Yahoo-notering, bv. warrants, FCPE)
    if not _column_exists(cur, "assets", "manual_price"):
        cur.execute("ALTER TABLE assets ADD COLUMN manual_price REAL")
    if not _column_exists(cur, "assets", "manual_price_cur"):
        cur.execute("ALTER TABLE assets ADD COLUMN manual_price_cur TEXT")
    # Enkel-handmatig: sla alle onlinebronnen over voor dit activum. Voor effecten die
    # nergens publiek genoteerd zijn (bv. een niet-beursgenoteerde warrant) is elke
    # onlinepoging bij voorbaat zinloos; deze vlag voorkomt 5 mislukte netwerkcalls en
    # even zoveel logregels bij élke koersverversing.
    # Handmatig gecorrigeerd: deze dividendlijn is door jou aangepast in de tabel.
    # De knop 'keten herberekenen' laat zulke lijnen standaard met rust — anders zou
    # een herberekening je eigen correcties (bv. een afwijkend verdragstarief of een
    # bedrag exact zoals de broker het afrekende) stilzwijgend overschrijven.
    if not _column_exists(cur, "dividends", "manual_override"):
        cur.execute("ALTER TABLE dividends ADD COLUMN manual_override INTEGER DEFAULT 0")

    if not _column_exists(cur, "assets", "manual_only"):
        cur.execute("ALTER TABLE assets ADD COLUMN manual_only INTEGER DEFAULT 0")

    # Aantal opeenvolgende mislukte koersophalingen. Na een grens (10) stopt de app met
    # proberen: blijven vijf bronnen tien keer op rij niets vinden, dan is dat geen
    # tijdelijke storing maar een instrument dat nergens genoteerd staat — en dan zijn
    # verdere pogingen enkel nog verspilde netwerkcalls en logruis.
    if not _column_exists(cur, "assets", "price_fail_count"):
        cur.execute("ALTER TABLE assets ADD COLUMN price_fail_count INTEGER DEFAULT 0")

    # Eigen wisselkoers: je broker hanteert vaak zijn eigen FX-koers (soms met een
    # auto-FX-marge erin verwerkt). Die koers hoort BIJ DE TRANSACTIE en mag nooit
    # overschreven worden door een herberekening met de historische marktkoers.
    if not _column_exists(cur, "transactions", "fx_manual"):
        cur.execute("ALTER TABLE transactions ADD COLUMN fx_manual INTEGER DEFAULT 0")
    # Idem voor een handmatig gecorrigeerde TOB.
    if not _column_exists(cur, "transactions", "tob_manual"):
        cur.execute("ALTER TABLE transactions ADD COLUMN tob_manual INTEGER DEFAULT 0")

    # Yahoo-symbool laatst gevonden VIA de ISIN (cache/weergave). De ISIN blijft de
    # brondata voor koersopzoeking; dit is enkel een gemakskolom zodat je ziet welk
    # concreet symbool daaraan gekoppeld werd, zonder dat de ticker zelf de bron van
    # waarheid is (ambigu bij Yahoo door beurssuffixen en gelijkaardige ISIN's).
    if not _column_exists(cur, "assets", "resolved_symbol"):
        cur.execute("ALTER TABLE assets ADD COLUMN resolved_symbol TEXT")

    # Koersdoel rechtstreeks op het activum (in te vullen bij het toevoegen, i.p.v.
    # pas bij een transactie). Blijft de meest recente transactie-koersdoel bestaan,
    # dan heeft dat voorrang in de weergave; dit is de standaard-/startwaarde.
    if not _column_exists(cur, "assets", "price_target"):
        cur.execute("ALTER TABLE assets ADD COLUMN price_target REAL")
    if not _column_exists(cur, "assets", "price_target_currency"):
        cur.execute("ALTER TABLE assets ADD COLUMN price_target_currency TEXT")

    # Zorg dat oude rijen een rekening hebben
    cur.execute(
        "UPDATE transactions SET account=? WHERE account IS NULL OR account=''",
        (DEFAULT_ACCOUNT,)
    )

    # Versoepel de oude CHECK(price_per_unit > 0) naar >= 0 zodat gratis toekenningen
    # (waarde 0) kunnen worden geregistreerd. SQLite kan een CHECK niet in-place
    # wijzigen, dus de tabel wordt herbouwd met behoud van alle kolommen en data.
    _relax_transactions_price_check(conn, cur)
    _relax_dividends_ticker_notnull(conn, cur)

    # Punt 2: koersdoelen 0 (of negatief) betekenen 'niet bepaald' en horen niet in de
    # historiek of in het gemiddelde. Bestaande rijen eenmalig opruimen.
    try:
        cur.execute("DELETE FROM price_target_history WHERE target IS NULL OR target <= 0")
    except Exception:
        pass

    _backfill_price_targets(conn, cur)

    conn.commit()


def _backfill_price_targets(conn, cur):
    """Vul de koersdoel-historiek (punt 8) éénmalig met wat er al in de database zit,
    zodat de tijdlijn meteen gevuld is: bestaande AI-koersdoelen (uit ai_ratings, met
    hun eigen datum), koersdoelen die aan transacties hangen (met de transactiedatum),
    en het huidige handmatige koersdoel op elk activum (als 'nu'). Draait enkel als de
    tabel nog leeg is — daarna houdt log_price_target de historiek bij."""
    have = cur.execute("SELECT COUNT(*) c FROM price_target_history").fetchone()
    if have and have["c"]:
        return  # al gevuld

    events = []  # (set_at, ticker, target, currency, source, note)
    # 1) AI-koersdoelen uit ai_ratings
    for r in cur.execute(
        "SELECT ticker, price_target, currency, model, created_at FROM ai_ratings "
        "WHERE price_target IS NOT NULL ORDER BY created_at ASC, id ASC"
    ).fetchall():
        events.append((str(r["created_at"] or ""), r["ticker"], r["price_target"],
                       r["currency"] or "EUR", "ai", r["model"]))
    # 2) Koersdoelen die aan transacties hangen (datum = transactiedatum)
    for r in cur.execute(
        "SELECT ticker, price_target, currency, date FROM transactions "
        "WHERE price_target IS NOT NULL ORDER BY date ASC, id ASC"
    ).fetchall():
        events.append((str(r["date"] or "")[:10] + " 00:00:00", r["ticker"],
                       r["price_target"], r["currency"] or "EUR", "manual", "via transactie"))
    # 3) Het huidige handmatige koersdoel op het activum zelf (als recentste ijkpunt)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:00")
    for r in cur.execute(
        "SELECT ticker, price_target, price_target_currency, currency FROM assets "
        "WHERE price_target IS NOT NULL"
    ).fetchall():
        events.append((now, r["ticker"], r["price_target"],
                       r["price_target_currency"] or r["currency"] or "EUR",
                       "manual", "huidig koersdoel (migratie)"))

    # Sorteer chronologisch en dedup per (ticker, source): enkel echte wijzigingen.
    events.sort(key=lambda e: (e[1], e[4], e[0]))  # ticker, source, set_at
    last_val = {}  # (ticker, source) -> (target, currency)
    to_insert = []
    for set_at, ticker, target, currency, source, note in events:
        try:
            tgt = round(float(target), 6)
        except (TypeError, ValueError):
            continue
        if tgt <= 0:
            continue          # 'niet bepaald' hoort niet in de historiek (punt 2)
        key = (ticker.upper(), source)
        prev = last_val.get(key)
        if prev and abs(prev[0] - tgt) < 1e-6 and prev[1] == (currency or "EUR"):
            continue  # zelfde bron, zelfde waarde na elkaar -> overslaan
        last_val[key] = (tgt, currency or "EUR")
        to_insert.append((ticker.upper(), tgt, currency or "EUR", source, note,
                          set_at or now))

    if to_insert:
        cur.executemany(
            "INSERT INTO price_target_history (ticker,target,currency,source,note,set_at) "
            "VALUES (?,?,?,?,?,?)", to_insert
        )


def _relax_dividends_ticker_notnull(conn, cur):
    """Interest en securities lending zijn niet altijd aan een specifiek activum
    gekoppeld (bv. cash-rekeninginterest). 'ticker' mag daarom leeg zijn — bestaande
    databases met de oude NOT NULL-constraint worden hier herbouwd, net als bij
    price_per_unit hierboven. Whitespace-onafhankelijke regex, want de exacte
    kolomuitlijning in oudere schemaversies kan licht verschillen."""
    import re
    row = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='dividends'"
    ).fetchone()
    sql = row["sql"] if row else None
    if not sql:
        return
    m = re.search(r'(\bticker\s+TEXT)\s+NOT NULL\b', sql)
    if not m:
        return  # nieuw schema (al versoepeld) of onverwachte vorm: niets doen
    new_sql = sql[:m.start()] + m.group(1) + sql[m.end():]
    new_sql = (new_sql.replace("CREATE TABLE IF NOT EXISTS dividends", "CREATE TABLE dividends_new")
                      .replace("CREATE TABLE dividends", "CREATE TABLE dividends_new"))
    cols = [r[1] for r in cur.execute("PRAGMA table_info(dividends)").fetchall()]
    collist = ", ".join(f'"{c}"' for c in cols)
    cur.execute("PRAGMA foreign_keys=off")
    cur.execute(new_sql)
    cur.execute(f"INSERT INTO dividends_new ({collist}) SELECT {collist} FROM dividends")
    cur.execute("DROP TABLE dividends")
    cur.execute("ALTER TABLE dividends_new RENAME TO dividends")
    cur.execute("PRAGMA foreign_keys=on")


def _relax_transactions_price_check(conn, cur):
    row = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions'"
    ).fetchone()
    sql = row["sql"] if row else None
    if not sql or "price_per_unit > 0" not in sql:
        return  # nieuw schema of al versoepeld
    cols = [r[1] for r in cur.execute("PRAGMA table_info(transactions)").fetchall()]
    collist = ", ".join(f'"{c}"' for c in cols)
    new_sql = (sql.replace("price_per_unit > 0", "price_per_unit >= 0")
                  .replace("CREATE TABLE IF NOT EXISTS transactions", "CREATE TABLE transactions_new")
                  .replace("CREATE TABLE transactions", "CREATE TABLE transactions_new"))
    cur.execute("PRAGMA foreign_keys=off")
    cur.execute(new_sql)
    cur.execute(f"INSERT INTO transactions_new ({collist}) SELECT {collist} FROM transactions")
    cur.execute("DROP TABLE transactions")
    cur.execute("ALTER TABLE transactions_new RENAME TO transactions")
    cur.execute("PRAGMA foreign_keys=on")


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

def set_asset_snapshot(ticker, snapshot_price=None, snapshot_price_eur=None):
    """Bewaar de fotomomentwaarde (slotkoers 31/12/2025) voor een activum."""
    conn = get_connection()
    conn.execute("UPDATE assets SET snapshot_price=?, snapshot_price_eur=? WHERE ticker=?",
                 (snapshot_price, snapshot_price_eur, ticker.upper()))
    conn.commit()
    conn.close()


def set_manual_price(ticker, price=None, currency=None):
    """Bewaar (of wis) een handmatige koers voor een activum zonder Yahoo-notering."""
    conn = get_connection()
    conn.execute("UPDATE assets SET manual_price=?, manual_price_cur=? WHERE ticker=?",
                 (price, currency, ticker.upper()))
    conn.commit()
    conn.close()


def get_manual_price(ticker) -> dict | None:
    """Handmatige koers voor een activum, of None."""
    conn = get_connection()
    row = conn.execute("SELECT manual_price, manual_price_cur, currency FROM assets WHERE ticker=?",
                       (ticker.upper(),)).fetchone()
    conn.close()
    if row and row["manual_price"] is not None:
        return {"price": float(row["manual_price"]),
                "currency": row["manual_price_cur"] or row["currency"] or "EUR"}
    return None


def set_manual_only(ticker, enabled: bool):
    """Zet/wis 'enkel handmatige koers' voor een activum: alle onlinebronnen worden dan
    overgeslagen."""
    conn = get_connection()
    conn.execute("UPDATE assets SET manual_only=? WHERE ticker=?",
                 (1 if enabled else 0, ticker.upper()))
    conn.commit()
    conn.close()


def is_manual_only(ticker) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT manual_only FROM assets WHERE ticker=?",
                       (ticker.upper(),)).fetchone()
    conn.close()
    return bool(row and row["manual_only"])


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


def update_account_cost(cost_id: int, **fields):
    """Werk een rekeningkost bij (whitelist)."""
    allowed = {"account", "date", "description", "amount", "currency", "amount_eur", "fx_rate"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(cost_id)
    conn = get_connection()
    conn.execute(f"UPDATE account_costs SET {','.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()


def delete_account_cost(cost_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM account_costs WHERE id=?", (cost_id,))
    conn.commit()
    conn.close()


# ── Cash-grootboek ───────────────────────────────────────────────────────────

def add_cash_movement(account, date, mtype, amount_native, currency="EUR",
                      fx_rate=1.0, amount_eur=None, note=None):
    """mtype = 'deposit' (storting) of 'withdrawal' (opname)."""
    if amount_eur is None:
        amount_eur = amount_native * (fx_rate or 1.0)
    conn = get_connection()
    conn.execute(
        """INSERT INTO cash_movements
           (account,date,type,amount_native,currency,fx_rate,amount_eur,note)
           VALUES (?,?,?,?,?,?,?,?)""",
        (account, date, mtype, amount_native, currency, fx_rate, amount_eur, note))
    conn.commit()
    conn.close()


def get_cash_movements(account=None) -> list[dict]:
    conn = get_connection()
    q, p = "SELECT * FROM cash_movements", []
    if account:
        q += " WHERE account=?"; p.append(account)
    q += " ORDER BY date DESC, id DESC"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_cash_movement(mov_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM cash_movements WHERE id=?", (mov_id,))
    conn.commit()
    conn.close()


def _div_net_eur(d: dict) -> float:
    if d.get("net_eur") is not None:
        return d["net_eur"]
    g = d.get("gross_eur") if d.get("gross_eur") is not None else d["gross_amount"]
    w = d.get("withholding_eur") if d.get("withholding_eur") is not None else d["withholding_tax"]
    return (g or 0) - (w or 0)


def _div_cash_eur(d: dict) -> float:
    """Cashbedrag (EUR) van een dividend voor het cash-grootboek.
    Gebruikt het bij invoer gekozen veld (cash_basis: net/gross_after/gross_before);
    valt terug op het netto-bedrag voor oudere rijen."""
    if d.get("cash_eur") is not None:
        return d["cash_eur"]
    return _div_net_eur(d)


def compute_cash_positions(accounts=None) -> dict:
    """Afgeleide cashpositie per rekening uit alle bewegingen.

    beschikbare cash = stortingen − opnames + verkopen(netto) − aankopen(netto)
                       + dividenden(netto) − rekeningkosten

    Performance shares (toekenningen) kosten geen brokergeld: hun aankoop telt voor €0.
    De personenbelasting erop is geen brokerbeweging (doorgaans via loon) en zit hier
    dus niet in — betaalde je ze tóch vanaf de rekening, boek ze dan als een opname.
    """
    accs = set(accounts) if accounts else None

    def _use(a):
        return accs is None or (a or DEFAULT_ACCOUNT) in accs

    per = {}
    def _row(a):
        a = a or DEFAULT_ACCOUNT
        return per.setdefault(a, {"deposits": 0.0, "withdrawals": 0.0, "buys": 0.0,
                                  "sells": 0.0, "dividends": 0.0, "costs": 0.0})

    for m in get_cash_movements():
        if not _use(m["account"]):
            continue
        r = _row(m["account"])
        if m["type"] == "deposit":
            r["deposits"] += m["amount_eur"] or 0.0
        else:
            r["withdrawals"] += m["amount_eur"] or 0.0

    for t in get_transactions():
        if not _use(t.get("account")):
            continue
        r = _row(t.get("account"))
        tot = t.get("total_amount_eur") or 0.0
        fees = (t.get("costs_eur") or 0.0) + (t.get("tob_tax") or 0.0)
        if t["transaction_type"] == "buy":
            if t.get("is_performance_share"):
                continue                     # toekenning: geen cash-uitgave
            r["buys"] += tot + fees          # cash uit
        else:
            r["sells"] += tot - fees         # cash in

    for d in get_dividends():
        if not _use(d.get("account")):
            continue
        _row(d.get("account"))["dividends"] += _div_cash_eur(d)

    for a in (accs if accs is not None else get_accounts()):
        cost = total_account_costs_eur(account=a)
        if cost:
            _row(a)["costs"] += cost

    totals = {"deposits": 0.0, "withdrawals": 0.0, "buys": 0.0,
              "sells": 0.0, "dividends": 0.0, "costs": 0.0, "available": 0.0}
    for a, r in per.items():
        r["available"] = (r["deposits"] - r["withdrawals"] + r["sells"]
                          - r["buys"] + r["dividends"] - r["costs"])
        for k in totals:
            if k != "available":
                totals[k] += r[k]
    totals["available"] = (totals["deposits"] - totals["withdrawals"] + totals["sells"]
                           - totals["buys"] + totals["dividends"] - totals["costs"])
    return {"per_account": per, "totals": totals}


def cash_ledger(accounts=None) -> list[dict]:
    """Volledig chronologisch cash-grootboek: handmatige stortingen/opnames + de
    afgeleide bewegingen uit aankopen, verkopen, dividenden en rekeningkosten, elk met
    een lopend saldo per rekening. Performance shares verschijnen als €0 (geen cash)."""
    accs = set(accounts) if accounts else None
    def _use(a):
        return accs is None or (a or DEFAULT_ACCOUNT) in accs

    items = []
    for m in get_cash_movements():
        if not _use(m["account"]):
            continue
        delta = (m["amount_eur"] or 0.0) * (1 if m["type"] == "deposit" else -1)
        items.append({"date": m["date"][:10], "account": m["account"] or DEFAULT_ACCOUNT,
                      "label": "Storting" if m["type"] == "deposit" else "Opname",
                      "delta": delta, "desc": m.get("note") or "",
                      "source": "manual", "ref": m["id"]})
    for t in get_transactions():
        if not _use(t.get("account")):
            continue
        tot  = t.get("total_amount_eur") or 0.0
        fees = (t.get("costs_eur") or 0.0) + (t.get("tob_tax") or 0.0)
        acc  = t.get("account") or DEFAULT_ACCOUNT
        desc = f"{t['quantity']:g} × {t['ticker']}"
        if t["transaction_type"] == "buy":
            if t.get("is_performance_share"):
                items.append({"date": t["date"][:10], "account": acc, "label": "Toekenning",
                              "delta": 0.0, "desc": desc + " (geen cash)", "source": "txn", "ref": t["id"]})
            else:
                items.append({"date": t["date"][:10], "account": acc, "label": "Aankoop",
                              "delta": -(tot + fees), "desc": desc, "source": "txn", "ref": t["id"]})
        else:
            items.append({"date": t["date"][:10], "account": acc, "label": "Verkoop",
                          "delta": tot - fees, "desc": desc, "source": "txn", "ref": t["id"]})
    _KIND_LABEL = {"dividend": "Dividend", "interest": "Interest",
                   "securities_lending": "Securities lending"}
    for d in get_dividends():
        if not _use(d.get("account")):
            continue
        items.append({"date": d["date"][:10], "account": d.get("account") or DEFAULT_ACCOUNT,
                      "label": _KIND_LABEL.get(d.get("kind"), "Dividend"),
                      "delta": _div_cash_eur(d),
                      "desc": d["ticker"] or "Algemeen (niet gekoppeld)",
                      "source": "div", "ref": d["id"]})
    for c in get_account_costs():
        if not _use(c.get("account")):
            continue
        items.append({"date": c["date"][:10], "account": c.get("account") or DEFAULT_ACCOUNT,
                      "label": "Rekeningkost", "delta": -(c.get("amount_eur") or 0.0),
                      "desc": c.get("description") or "", "source": "cost", "ref": c["id"]})

    # Chronologisch oplopend; lopend saldo per rekening
    order = {"manual": 0, "txn": 1, "div": 2, "cost": 3}
    items.sort(key=lambda x: (x["date"], order.get(x["source"], 9)))
    bals = {}
    for it in items:
        bals[it["account"]] = bals.get(it["account"], 0.0) + it["delta"]
        it["balance"] = bals[it["account"]]
    return items


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
    # Koersdoel-historiek: elk AI-koersdoel mee opnemen (punt 8). Dedup gebeurt in
    # log_price_target zelf (zelfde bron + zelfde waarde na elkaar => niet opnieuw).
    if price_target is not None:
        try:
            log_price_target(ticker, price_target, currency, "ai", note=model)
        except Exception as e:
            logger.warning(f"log_price_target(ai,{ticker}) faalde: {e}")


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


# ── Koersdoel-historiek (punt 8) ─────────────────────────────────────────────

def log_price_target(ticker: str, target, currency: str = "EUR",
                     source: str = "manual", note: str | None = None,
                     set_at: str | None = None) -> bool:
    """Leg een koersdoel vast in de historiek. Bron is 'manual' of 'ai'.

    Dedup: is het laatst gelogde koersdoel VAN DEZELFDE BRON voor deze ticker exact
    hetzelfde (waarde + munt), dan wordt er niets toegevoegd — zo blijft de tijdlijn
    een lijst van ECHTE wijzigingen i.p.v. een herhaling bij elke opslag of AI-ronde.
    Een handmatig doel ná een AI-doel (of omgekeerd) met dezelfde waarde wordt wél
    gelogd, want dat is een betekenisvolle bevestiging vanuit een andere bron.
    Geeft True terug als er effectief een rij is toegevoegd."""
    if target is None:
        return False
    try:
        tgt = round(float(target), 6)
    except (TypeError, ValueError):
        return False
    if tgt <= 0:
        return False   # 0/negatief = 'niet bepaald' -> nooit in de historiek (punt 2)
    cur = (currency or "EUR")
    conn = get_connection()
    last = conn.execute(
        "SELECT target,currency FROM price_target_history "
        "WHERE ticker=? AND source=? ORDER BY set_at DESC, id DESC LIMIT 1",
        (ticker.upper(), source)
    ).fetchone()
    if last and abs((last["target"] or 0) - tgt) < 1e-6 and (last["currency"] or "EUR") == cur:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO price_target_history (ticker,target,currency,source,note,set_at) "
        "VALUES (?,?,?,?,?,COALESCE(?, datetime('now')))",
        (ticker.upper(), tgt, cur, source, note, set_at)
    )
    conn.commit()
    conn.close()
    return True


def get_price_target_history(ticker: str) -> list[dict]:
    """Alle vastgelegde koersdoelen voor een ticker, NIEUWSTE eerst."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT target,currency,source,note,set_at FROM price_target_history "
        "WHERE ticker=? AND target > 0 ORDER BY set_at ASC, id ASC",
        (ticker.upper(),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_ai_targets(ticker: str, limit: int = 9) -> list[dict]:
    """De laatste AI-koersdoelbepalingen voor een ticker (nieuwste eerst), zonder
    nulwaarden — een 0 betekent 'niet bepaald' en telt niet mee (punt 2)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT price_target,currency,model,created_at FROM ai_ratings "
        "WHERE ticker=? AND price_target IS NOT NULL AND price_target > 0 "
        "ORDER BY created_at DESC, id DESC LIMIT ?", (ticker.upper(), int(limit))
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_effective_price_target(ticker: str, limit: int = 9,
                               manual_asset=None, manual_txn=None) -> dict:
    """Het koersdoel zoals het dashboard het moet tonen (punt 1).

    Volgorde:
      1. een HANDMATIG koersdoel heeft altijd voorrang (op het activum, anders het
         laatste transactie-koersdoel);
      2. anders het GEMIDDELDE van de laatste 'limit' AI-bepalingen (of minder als er
         minder zijn).
    Nulwaarden tellen nooit mee: 0 betekent 'niet bepaald' (punt 2).

    Geeft {'value', 'source', 'count', 'currency'} met source in
    'manual' | 'manual_txn' | 'ai_avg' | None.
    'manual_asset'/'manual_txn' kunnen meegegeven worden om extra queries te vermijden
    wanneer de oproeper die gegevens al heeft."""
    def _pos(v):
        try:
            f = float(v)
            return f if f > 0 else None
        except (TypeError, ValueError):
            return None

    if manual_asset is None or manual_txn is None:
        a = get_asset(ticker) or {}
        if manual_asset is None:
            manual_asset = a.get("price_target")
        cur_default = a.get("price_target_currency") or a.get("currency") or "EUR"
    else:
        cur_default = "EUR"

    m = _pos(manual_asset)
    if m is not None:
        return {"value": m, "source": "manual", "count": 1, "currency": cur_default}
    m = _pos(manual_txn)
    if m is not None:
        return {"value": m, "source": "manual_txn", "count": 1, "currency": cur_default}

    rows = get_recent_ai_targets(ticker, limit)
    vals = [float(r["price_target"]) for r in rows]
    if not vals:
        return {"value": None, "source": None, "count": 0, "currency": cur_default}
    return {"value": round(sum(vals) / len(vals), 6), "source": "ai_avg",
            "count": len(vals), "currency": (rows[0].get("currency") or cur_default)}


def get_last_price_changes(tickers: list[str]) -> dict:
    """Punt 3: per ticker het tijdstip waarop de koers VOOR HET LAATST VERANDERDE.

    price_history krijgt bij elke ophaling een rij, ook als de koers identiek blijft
    (bv. in het weekend). Het laatste rij-tijdstip zegt dus enkel 'wanneer keken we',
    niet 'wanneer bewoog de koers'. Deze functie zoekt het BEGIN van de huidige reeks
    identieke koersen: het moment waarop de actuele koers voor het eerst verscheen.

    Geeft {TICKER: {'timestamp', 'price', 'checked'}} — 'checked' is het laatste
    ophaalmoment, zodat de UI beide kan tonen."""
    if not tickers:
        return {}
    conn = get_connection()
    out = {}
    for t in {str(x).upper() for x in tickers}:
        last = conn.execute(
            "SELECT price, timestamp FROM price_history WHERE ticker=? "
            "ORDER BY timestamp DESC, rowid DESC LIMIT 1", (t,)
        ).fetchone()
        if not last:
            continue
        cur_price, checked = last["price"], last["timestamp"]
        # Laatste tijdstip met een ANDERE koers dan de huidige...
        prev = conn.execute(
            "SELECT MAX(timestamp) ts FROM price_history "
            "WHERE ticker=? AND ROUND(price, 6) <> ROUND(?, 6)", (t, cur_price)
        ).fetchone()
        if prev and prev["ts"]:
            # ...en dan de eerste rij daarna: toen kreeg de koers haar huidige waarde.
            row = conn.execute(
                "SELECT MIN(timestamp) ts FROM price_history "
                "WHERE ticker=? AND timestamp > ?", (t, prev["ts"])
            ).fetchone()
            changed = (row["ts"] if row and row["ts"] else checked)
        else:
            # Nooit een andere koers gezien: dan geldt de eerste meting als startpunt.
            row = conn.execute(
                "SELECT MIN(timestamp) ts FROM price_history WHERE ticker=?", (t,)
            ).fetchone()
            changed = (row["ts"] if row and row["ts"] else checked)
        out[t] = {"timestamp": changed, "price": cur_price, "checked": checked}
    conn.close()
    return out


def get_tickers_with_target_history() -> list[str]:
    """Tickers waarvoor minstens één koersdoel is vastgelegd (alfabetisch)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM price_target_history WHERE target > 0 ORDER BY ticker"
    ).fetchall()
    conn.close()
    return [r["ticker"] for r in rows]


# ── Statusgebeurtenissen / waarschuwingen (punt 2 + 3) ───────────────────────

import json as _json


def record_status_event(ticker: str, kind: str, severity: str, message: str,
                        detail=None, isin: str | None = None) -> bool:
    """Registreer (of werk bij) een openstaande statusgebeurtenis voor (ticker, kind).

    Bestaat er al een OPENSTAANDE (niet-opgeloste) gebeurtenis van dezelfde soort voor
    deze ticker, dan wordt die bijgewerkt (boodschap/detail/tijd) zonder de gebruiker
    opnieuw te alarmeren — het blijft één lopende waarschuwing. Bestaat ze nog niet, dan
    wordt er een nieuwe aangemaakt. Geeft True terug als er een NIEUWE gebeurtenis is
    aangemaakt (voor de teller 'nieuw')."""
    det = _json.dumps(detail, ensure_ascii=False) if detail is not None else None
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM status_events WHERE ticker=? AND kind=? AND resolved_at IS NULL "
        "ORDER BY id DESC LIMIT 1", (ticker.upper(), kind)
    ).fetchone()
    created = False
    if row:
        conn.execute(
            "UPDATE status_events SET severity=?, message=?, detail=?, isin=COALESCE(?,isin), "
            "updated_at=datetime('now') WHERE id=?",
            (severity, message, det, isin, row["id"])
        )
    else:
        conn.execute(
            "INSERT INTO status_events (ticker,isin,kind,severity,message,detail) "
            "VALUES (?,?,?,?,?,?)", (ticker.upper(), isin, kind, severity, message, det)
        )
        created = True
    conn.commit()
    conn.close()
    return created


def resolve_status_event(ticker: str, kind: str) -> int:
    """Sluit de openstaande gebeurtenis(sen) van (ticker, kind) — de toestand geldt niet
    meer (bv. de koers wordt weer bijgewerkt). Geeft het aantal gesloten rijen terug."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE status_events SET resolved_at=datetime('now') "
        "WHERE ticker=? AND kind=? AND resolved_at IS NULL", (ticker.upper(), kind)
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n or 0


def acknowledge_status_event(event_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE status_events SET acknowledged=1, updated_at=datetime('now') WHERE id=?",
                 (event_id,))
    conn.commit()
    conn.close()


def resolve_status_event_by_id(event_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE status_events SET resolved_at=datetime('now') WHERE id=?", (event_id,))
    conn.commit()
    conn.close()


def delete_status_event(event_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM status_events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()


def get_status_events(include_resolved: bool = False) -> list[dict]:
    """Openstaande statusgebeurtenissen (of alle, incl. opgeloste). Detail wordt naar een
    dict teruggeparset."""
    conn = get_connection()
    q = "SELECT * FROM status_events"
    if not include_resolved:
        q += " WHERE resolved_at IS NULL"
    q += " ORDER BY (severity='error') DESC, (severity='warning') DESC, updated_at DESC, id DESC"
    rows = conn.execute(q).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = _json.loads(d["detail"]) if d.get("detail") else {}
        except (ValueError, TypeError):
            d["detail"] = {}
        out.append(d)
    return out


def detect_stale_prices(tickers: list[str], max_days: float) -> list[dict]:
    """Tickers waarvan de laatst vastgelegde koers ouder is dan max_days. Puur op basis
    van price_history — geen netwerk. Tickers zonder enige koers worden overgeslagen."""
    if not tickers:
        return []
    latest = get_latest_prices(tickers)
    now = datetime.now()
    out = []
    for t in tickers:
        row = latest.get(t.upper())
        if not row or not row.get("timestamp"):
            continue
        try:
            ts = datetime.strptime(str(row["timestamp"])[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue
        age_days = (now - ts).total_seconds() / 86400.0
        if age_days > max_days:
            out.append({
                "ticker": t.upper(),
                "message": (f"Geen nieuwe koers sinds {ts.strftime('%d/%m %H:%M')} "
                            f"({age_days:.0f} dagen geleden)."),
                "detail": {"last": row["timestamp"], "age_days": round(age_days, 1)},
            })
    return out


def detect_flat_prices(tickers: list[str], min_measurements: int = 3) -> list[dict]:
    """Tickers die op hun recentste koersdag GEEN ENKELE koersbeweging vertoonden
    (min == max over minstens 'min_measurements' metingen die dag). Puur uit
    price_history — geen netwerk. Signaleert o.a. een effect waarvan de koers de hele
    dag identiek blijft (bv. omdat de bron telkens dezelfde slotkoers teruggeeft)."""
    if not tickers:
        return []
    keys = [t.upper() for t in tickers]
    placeholders = ",".join("?" * len(keys))
    conn = get_connection()
    out = []
    for t in keys:
        row = conn.execute(
            """SELECT date(timestamp) d, COUNT(*) n, MIN(price) mn, MAX(price) mx
               FROM price_history WHERE ticker=?
               GROUP BY date(timestamp) ORDER BY d DESC LIMIT 1""", (t,)
        ).fetchone()
        if not row or not row["d"]:
            continue
        if (row["n"] or 0) >= min_measurements and row["mn"] is not None \
                and abs((row["mn"] or 0) - (row["mx"] or 0)) < 1e-9:
            out.append({
                "ticker": t,
                "message": (f"Koers bewoog niet op {row['d']} — {row['n']} metingen, "
                            f"allemaal dezelfde waarde."),
                "detail": {"date": row["d"], "n": row["n"], "price": row["mn"]},
            })
    conn.close()
    return out


def run_status_checks(online: bool = True, tickers: list[str] | None = None) -> dict:
    """Voer alle statuscontroles uit en werk de status_events-tabel bij. Bedoeld voor
    de dagelijkse planner (online=True) én de knop op de statuspagina.

    - Altijd (geen netwerk): verouderde koersen en 'geen koersbeweging op een dag'.
    - Online: tickerwijziging/meerdere producten onder één ISIN (met bijwerken van de
      resolved_symbol-kolom), niet-geregistreerde aandelensplits, en naamsafwijkingen.
    Toestanden die niet meer gelden worden automatisch gesloten. Splits worden NIET
    automatisch toegepast (dat zou de kostbasis wijzigen) — enkel gemeld."""
    if tickers is None:
        try:
            import belgian_tax as _bt
            tickers, _ = _bt.open_position_tickers()
        except Exception:
            tickers = [a["ticker"] for a in get_assets()]
    tickers = [t.upper() for t in (tickers or [])]
    assets = {a["ticker"].upper(): a for a in get_assets()}
    summary = {"checked": len(tickers), "new": 0, "resolved": 0, "open": 0,
               "online": online, "errors": 0}

    try:
        stale_days = float(get_setting("status_stale_days", "4") or 4)
    except (ValueError, TypeError):
        stale_days = 4.0

    stale = {f["ticker"]: f for f in detect_stale_prices(tickers, stale_days)}
    flat = {f["ticker"]: f for f in detect_flat_prices(tickers)}

    md = None
    if online:
        try:
            import market_data as md  # lazy, defensief
        except Exception as e:
            logger.warning(f"run_status_checks: market_data niet importeerbaar ({e})")
            md = None
        # Euronext-sleutel dagelijks fris houden (goedkoop als hij nog werkt); dit
        # herstelt automatisch een sleutelrotatie en logt/waarschuwt indien nodig.
        if md is not None:
            try:
                kr = md.euronext_rebuild_key()
                if kr.get("rotated"):
                    summary["new"] += 1
            except Exception as e:
                logger.info(f"euronext_rebuild_key in statuscontrole: {e}")

    for t in tickers:
        a = assets.get(t, {"ticker": t})
        isin = a.get("isin")

        # DB-checks
        if t in stale:
            if record_status_event(t, "stale_price", "warning", stale[t]["message"],
                                   stale[t]["detail"], isin):
                summary["new"] += 1
        else:
            summary["resolved"] += resolve_status_event(t, "stale_price")

        if t in flat:
            if record_status_event(t, "flat_price", "info", flat[t]["message"],
                                   flat[t]["detail"], isin):
                summary["new"] += 1
        else:
            summary["resolved"] += resolve_status_event(t, "flat_price")

        # Netwerk-checks
        if online and md is not None:
            try:
                probe = md.asset_status_probe(a, online=True)
            except Exception as e:
                logger.info(f"asset_status_probe({t}): {e}")
                summary["errors"] += 1
                probe = None
            if probe:
                rs = (probe.get("resolved_symbol") or "").strip().upper()
                if rs and rs != (a.get("resolved_symbol") or "").strip().upper():
                    try:
                        update_asset(t, resolved_symbol=rs)
                    except Exception as e:
                        logger.warning(f"resolved_symbol bijwerken ({t}) faalde: {e}")
                evs = {e["kind"]: e for e in probe.get("events", [])}
                for kind in ("ticker_change", "name_change"):
                    if kind in evs:
                        e = evs[kind]
                        if record_status_event(t, kind, e["severity"], e["message"],
                                               e.get("detail"), isin):
                            summary["new"] += 1
                    else:
                        summary["resolved"] += resolve_status_event(t, kind)
                # Splits: enkel nog niet-geregistreerde melden (niet auto-toepassen)
                known = {(s["split_date"], round(float(s["ratio"]), 6)) for s in get_splits(t)}
                new_splits = [(d, r) for (d, r) in probe.get("splits", [])
                              if (d, round(float(r), 6)) not in known]
                if new_splits:
                    d, r = sorted(new_splits)[-1]
                    msg = f"Niet-geregistreerde aandelensplit gedetecteerd: {r:g}-voudig op {d}."
                    if record_status_event(t, "split", "warning", msg,
                                           {"splits": new_splits}, isin):
                        summary["new"] += 1
                else:
                    summary["resolved"] += resolve_status_event(t, "split")

    summary["open"] = len(get_status_events())
    try:
        set_setting("status_last_run", datetime.now().strftime("%Y-%m-%d %H:%M:00"))
    except Exception:
        pass
    return summary


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


def get_ai_usage_avg(function: str) -> dict | None:
    """Gemiddeld tokengebruik per oproep voor één AI-functie (uit de echte historiek).
    Basis voor een realistische kostenraming per model. None als er nog geen oproepen zijn."""
    conn = get_connection()
    row = conn.execute(
        """SELECT COUNT(*) n, AVG(prompt_tokens) pt, AVG(completion_tokens) ct
           FROM ai_usage WHERE function=?""", (function,)
    ).fetchone()
    conn.close()
    if not row or not row["n"]:
        return None
    return {"n": row["n"], "pt": row["pt"] or 0, "ct": row["ct"] or 0}


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
              currency="EUR", exchange=None, isin=None, belgian_registered=1,
              country="BE", price_target=None, price_target_currency=None):
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO assets
           (ticker,name,asset_type,etf_subtype,currency,exchange,isin,belgian_registered,country,
            price_target,price_target_currency)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ticker.upper(), name, asset_type, etf_subtype, currency, exchange, isin,
         int(belgian_registered), (country or "BE").upper(),
         price_target, price_target_currency)
    )
    conn.commit()
    conn.close()
    if price_target is not None:
        log_price_target(ticker, price_target,
                         price_target_currency or currency or "EUR", "manual")


def update_asset(ticker, name=None, asset_type=None, etf_subtype=None,
                 currency=None, exchange=None, isin=None, belgian_registered=None,
                 country=None, resolved_symbol=None, price_target=None,
                 price_target_currency=None, clear_price_target=False):
    conn = get_connection()
    fields, vals = [], []
    if name        is not None: fields.append("name=?");        vals.append(name)
    if asset_type  is not None: fields.append("asset_type=?");  vals.append(asset_type)
    if etf_subtype is not None: fields.append("etf_subtype=?"); vals.append(etf_subtype)
    if currency    is not None: fields.append("currency=?");    vals.append(currency)
    if exchange    is not None: fields.append("exchange=?");    vals.append(exchange)
    if isin        is not None: fields.append("isin=?");        vals.append(isin)
    if country     is not None: fields.append("country=?");     vals.append(country.upper())
    if belgian_registered is not None:
        fields.append("belgian_registered=?"); vals.append(int(belgian_registered))
    if resolved_symbol is not None:
        fields.append("resolved_symbol=?"); vals.append(resolved_symbol)
    if clear_price_target:
        fields.append("price_target=NULL"); fields.append("price_target_currency=NULL")
    else:
        if price_target is not None:
            fields.append("price_target=?"); vals.append(price_target)
        if price_target_currency is not None:
            fields.append("price_target_currency=?"); vals.append(price_target_currency)
    if fields:
        vals.append(ticker.upper())
        conn.execute(f"UPDATE assets SET {','.join(fields)} WHERE ticker=?", vals)
        conn.commit()
    conn.close()
    # Koersdoel-historiek: een handmatige wijziging van het koersdoel loggen (punt 8).
    if price_target is not None and not clear_price_target:
        cur = price_target_currency
        if cur is None:
            a = get_asset(ticker)
            cur = (a.get("price_target_currency") or a.get("currency") or "EUR") if a else "EUR"
        log_price_target(ticker, price_target, cur, "manual")


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
                    price_target=None, is_performance_share=0, income_tax_eur=0.0,
                    fx_manual=0, tob_manual=0):
    if total_amount_eur is None:
        total_amount_eur = total_amount * (fx_rate or 1.0)
    if costs_eur is None:
        costs_eur = 0.0
    conn = get_connection()
    conn.execute(
        """INSERT INTO transactions
           (ticker,transaction_type,date,quantity,price_per_unit,total_amount,
            currency,tob_tax,notes,account,costs,costs_currency,costs_eur,
            total_amount_eur,fx_rate,price_target,is_performance_share,income_tax_eur,
            fx_manual,tob_manual)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ticker.upper(), transaction_type, date, quantity, price_per_unit,
         total_amount, currency, tob_tax, notes, account, costs, costs_currency,
         costs_eur, total_amount_eur, fx_rate, price_target,
         int(is_performance_share or 0), income_tax_eur or 0.0,
         int(fx_manual or 0), int(tob_manual or 0))
    )
    conn.commit()
    conn.close()
    if price_target is not None:
        log_price_target(ticker, price_target, currency or "EUR", "manual",
                         note="via transactie", set_at=(str(date)[:10] + " 00:00:00"))


def update_transaction(txn_id: int, **fields):
    """Werk willekeurige velden van een transactie bij (voor correcties)."""
    allowed = {"ticker", "transaction_type", "date", "quantity", "price_per_unit",
               "total_amount", "currency", "tob_tax", "notes", "account", "costs",
               "costs_currency", "costs_eur", "total_amount_eur", "fx_rate",
               "price_target", "is_performance_share", "income_tax_eur",
               "fx_manual", "tob_manual"}
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
    # Ticker + munt van deze transactie ophalen voor een eventuele koersdoel-log.
    row = conn.execute("SELECT ticker, currency, date FROM transactions WHERE id=?",
                       (txn_id,)).fetchone()
    conn.close()
    if fields.get("price_target") is not None and row:
        log_price_target(row["ticker"], fields["price_target"],
                         row["currency"] or "EUR", "manual", note="via transactie")


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
                 account=None, details=None):
    """ticker mag None zijn voor interest/securities lending die niet aan een
    specifiek activum gekoppeld zijn (bv. cash-rekeninginterest)."""
    if gross_eur is None:
        gross_eur = gross_amount * (fx_rate or 1.0)
    if withholding_eur is None:
        withholding_eur = withholding_tax * (fx_rate or 1.0)
    if not account:
        account = DEFAULT_ACCOUNT
    d = details or {}
    if d.get("net_eur") is None:
        d["net_eur"] = gross_eur - withholding_eur
    if d.get("cash_basis") is None:
        d["cash_basis"] = "net"
    if d.get("cash_eur") is None:
        d["cash_eur"] = d["net_eur"]
    if d.get("kind") is None:
        d["kind"] = "dividend"
    cols = ["ticker", "date", "gross_amount", "withholding_tax", "currency", "notes",
            "fx_rate", "gross_eur", "withholding_eur",
            "foreign_wht_withheld", "belgian_rv_withheld", "account",
            "gross_before_wht", "gross_before_wht_cur", "foreign_wht_amt",
            "foreign_wht_cur", "gross_after_wht", "gross_after_wht_cur",
            "belgian_rv_amt", "net_received", "net_received_cur", "net_eur",
            "cash_basis", "cash_eur", "kind"]
    vals = [ticker.strip().upper() if ticker else None, date, gross_amount, withholding_tax, currency, notes,
            fx_rate, gross_eur, withholding_eur,
            int(foreign_wht_withheld), int(belgian_rv_withheld), account,
            d.get("gross_before_wht"), d.get("gross_before_wht_cur"),
            d.get("foreign_wht_amt"), d.get("foreign_wht_cur"),
            d.get("gross_after_wht"), d.get("gross_after_wht_cur"),
            d.get("belgian_rv_amt"), d.get("net_received"),
            d.get("net_received_cur"), d.get("net_eur"),
            d.get("cash_basis"), d.get("cash_eur"), d.get("kind")]
    conn = get_connection()
    conn.execute(f"INSERT INTO dividends ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
                 vals)
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


_DIV_EDITABLE = {
    "date", "account", "notes", "currency", "gross_amount", "withholding_tax",
    "fx_rate", "gross_eur", "withholding_eur", "net_eur",
    "foreign_wht_withheld", "belgian_rv_withheld",
    "gross_before_wht", "gross_before_wht_cur", "foreign_wht_amt", "foreign_wht_cur",
    "gross_after_wht", "gross_after_wht_cur", "belgian_rv_amt",
    "net_received", "net_received_cur", "cash_basis", "cash_eur", "kind",
    "manual_override",
}


def update_dividend(div_id: int, **fields):
    """Werk een dividend bij. Enkel toegelaten kolommen (whitelist) worden gewijzigd."""
    sets, vals = [], []
    for k, v in fields.items():
        if k in _DIV_EDITABLE:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(div_id)
    conn = get_connection()
    conn.execute(f"UPDATE dividends SET {','.join(sets)} WHERE id=?", vals)
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


# ── Marktopportuniteiten (luik 2 van het dagelijkse AI-advies) ───────────────

def save_market_idea(batch_id: str, idea_date: str, bucket: str, ticker: str,
                     name=None, exchange=None, isin=None, currency="EUR",
                     rating=None, price_at_advice=None, price_target=None,
                     dividend_yield=None, horizon=None, rationale=None,
                     catalysts=None, risks=None, model=None):
    """Sla één koopidee uit het marktadvies op."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO market_ideas
           (batch_id,idea_date,bucket,ticker,name,exchange,isin,currency,rating,
            price_at_advice,price_target,dividend_yield,horizon,rationale,
            catalysts,risks,model)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (batch_id, idea_date, bucket, ticker.upper(), name, exchange, isin, currency,
         rating, price_at_advice, price_target, dividend_yield, horizon, rationale,
         catalysts, risks, model),
    )
    conn.commit()
    conn.close()


def get_market_ideas(batch_id: str | None = None, since_date: str | None = None,
                     ticker: str | None = None, limit: int | None = None) -> list[dict]:
    """Koopideeën, nieuwste eerst. since_date = 'YYYY-MM-DD' (inclusief)."""
    conn = get_connection()
    q, p, conds = "SELECT * FROM market_ideas", [], []
    if batch_id:
        conds.append("batch_id=?"); p.append(batch_id)
    if since_date:
        conds.append("idea_date>=?"); p.append(since_date)
    if ticker:
        conds.append("ticker=?"); p.append(ticker.upper())
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY idea_date DESC, id ASC"
    if limit:
        q += " LIMIT ?"; p.append(limit)
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_idea_batch() -> str | None:
    """Batch-id van de meest recente ronde marktopportuniteiten."""
    conn = get_connection()
    row = conn.execute(
        "SELECT batch_id FROM market_ideas ORDER BY idea_date DESC, id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["batch_id"] if row else None


def get_idea_tickers_since(since_date: str, limit: int = 200) -> list[str]:
    """Unieke tickers uit de koopideeën sinds een datum — de scheduler volgt hun
    koers op zodat het rendement sinds advies zonder netwerkcalls getoond kan
    worden. Nieuwste ideeën eerst, afgetopt op 'limit'."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT ticker, MAX(idea_date) AS d FROM market_ideas
           WHERE idea_date >= ? GROUP BY ticker ORDER BY d DESC LIMIT ?""",
        (since_date, limit),
    ).fetchall()
    conn.close()
    return [r["ticker"] for r in rows]


def cleanup_old_market_ideas(keep_days: int = 400):
    conn = get_connection()
    conn.execute("DELETE FROM market_ideas WHERE idea_date < date('now', ? || ' days')",
                 (f"-{keep_days}",))
    conn.commit()
    conn.close()


def get_previous_closes(tickers: list[str], before_date: str) -> dict[str, dict]:
    """Laatst opgeslagen koers STRIKT vóór 'before_date' (YYYY-MM-DD), per ticker,
    in één query. Dat is de referentie voor de dagelijkse P/L: de laatste koers van
    de vorige (beurs)dag. Tickers zonder oudere koers ontbreken in het resultaat."""
    if not tickers:
        return {}
    keys = [t.upper() for t in tickers]
    placeholders = ",".join("?" * len(keys))
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT ticker, price, currency, MAX(timestamp) AS timestamp
            FROM price_history
            WHERE ticker IN ({placeholders}) AND timestamp < ?
            GROUP BY ticker""",
        keys + [f"{before_date} 00:00:00"],
    ).fetchall()
    conn.close()
    return {r["ticker"]: dict(r) for r in rows}


def record_price_failure(ticker: str) -> int:
    """Tel één mislukte koersophaling voor dit activum en geef de nieuwe stand terug."""
    conn = get_connection()
    conn.execute("UPDATE assets SET price_fail_count = COALESCE(price_fail_count,0) + 1 "
                 "WHERE ticker=?", (ticker.upper(),))
    conn.commit()
    row = conn.execute("SELECT price_fail_count FROM assets WHERE ticker=?",
                       (ticker.upper(),)).fetchone()
    conn.close()
    return int(row["price_fail_count"]) if row and row["price_fail_count"] else 0


def reset_price_failures(ticker: str):
    conn = get_connection()
    conn.execute("UPDATE assets SET price_fail_count=0 WHERE ticker=?", (ticker.upper(),))
    conn.commit()
    conn.close()


def get_price_fail_count(ticker: str) -> int:
    conn = get_connection()
    row = conn.execute("SELECT price_fail_count FROM assets WHERE ticker=?",
                       (ticker.upper(),)).fetchone()
    conn.close()
    return int(row["price_fail_count"]) if row and row["price_fail_count"] else 0


def get_latest_prices(tickers: list[str]) -> dict[str, dict]:
    """Recentste opgeslagen koers voor meerdere tickers in EEN query
    (i.p.v. get_latest_price per ticker). Sleutels zijn UPPERCASE tickers;
    waarden dicts met price, currency en timestamp. Tickers zonder opgeslagen
    koers ontbreken in het resultaat."""
    if not tickers:
        return {}
    keys = [t.upper() for t in tickers]
    placeholders = ",".join("?" * len(keys))
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT ticker, price, currency, MAX(timestamp) AS timestamp
            FROM price_history WHERE ticker IN ({placeholders})
            GROUP BY ticker""",
        keys,
    ).fetchall()
    conn.close()
    return {r["ticker"]: dict(r) for r in rows}


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