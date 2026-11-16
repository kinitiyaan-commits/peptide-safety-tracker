"""SQLite schema and helpers. Every user-owned table carries user_id."""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("peptide_safety.db")

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL UNIQUE,
    is_demo      INTEGER NOT NULL DEFAULT 0,
    age          INTEGER,
    tracking_note TEXT NOT NULL DEFAULT '',
    consent_ack  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Synthetic demo catalog. evidence_note must cite its source; statuses are
-- limited to the factual categories in peptide_safety.REGULATORY_STATUSES.
-- aliases: JSON list of reviewed alias strings (e.g. "HGH" -> Somatropin).
-- Name + aliases are stable identifiers; historical logs are never rewritten
-- when a catalog name changes.
CREATE TABLE IF NOT EXISTS catalog (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL UNIQUE,
    category          TEXT NOT NULL,
    regulatory_status TEXT NOT NULL,
    evidence_note     TEXT NOT NULL,
    source_url        TEXT NOT NULL,
    review_status     TEXT NOT NULL DEFAULT 'verified'
                      CHECK (review_status IN ('verified', 'awaiting-verification')),
    source_type       TEXT NOT NULL DEFAULT 'fda',
    last_reviewed     TEXT,
    aliases           TEXT
);

-- Neutral brand directory: no ratings, no endorsements (AGENTS.md rule 3).
CREATE TABLE IF NOT EXISTS brands (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    supplier_type TEXT NOT NULL CHECK (supplier_type IN
                      ('pharma', 'compounding-pharmacy', 'research-supplier', 'other')),
    region        TEXT NOT NULL DEFAULT 'unspecified',
    notes         TEXT NOT NULL DEFAULT '',
    is_demo       INTEGER NOT NULL DEFAULT 0,
    UNIQUE (name, supplier_type)
);

CREATE TABLE IF NOT EXISTS usage_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    peptide_name TEXT NOT NULL,
    amount       REAL NOT NULL CHECK (amount > 0),
    unit         TEXT NOT NULL CHECK (unit IN ('mcg', 'mg', 'IU', 'units', 'mL')),
    route        TEXT NOT NULL DEFAULT 'unspecified',
    brand_id     INTEGER REFERENCES brands(id) ON DELETE SET NULL,
    taken_at     TEXT NOT NULL,
    notes        TEXT NOT NULL DEFAULT '',
    goal_data    TEXT,
    -- Correction history: JSON list of [{edited_at, previous: {...}}], one
    -- entry per edit, preserving the values as they were before that edit.
    -- Original values are never overwritten destructively.
    corrections  TEXT
);

CREATE TABLE IF NOT EXISTS symptoms (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    peptide_name TEXT NOT NULL,
    severity     INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 5),
    description  TEXT NOT NULL,
    logged_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    peptide_name TEXT NOT NULL,
    time_of_day  TEXT NOT NULL CHECK (time_of_day GLOB '[0-2][0-9]:[0-5][0-9]'),
    days         TEXT NOT NULL CHECK (days <> ''),
    notes        TEXT NOT NULL DEFAULT '',
    enabled      INTEGER NOT NULL DEFAULT 1
);

-- Per-profile multi-select tracking goals (journal customization only).
-- custom_text: optional private text the user attaches to a goal key
-- (e.g. their own wording for a custom reason).
CREATE TABLE IF NOT EXISTS user_goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_key    TEXT NOT NULL,
    custom_text TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, goal_key)
);

-- Independent observation logging: goal measurements (sleep, height, weight,
-- waist, energy, ...) recorded WITHOUT any administration event. Doc:
-- "users must be able to record sleep, height, weight, or symptoms without
-- creating an administration event." Symptoms already have their own table.
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    taken_at    TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    goal_data   TEXT,
    corrections TEXT
);

-- Request idempotency (distinct from the suspected-duplicate guard): a
-- client-generated key for one logical submission. Replaying the same key
-- returns the stored response WITHOUT creating another event — so a retry
-- after a network failure can never double-log. Keyed per user.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    idem_key      TEXT NOT NULL,
    scope         TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, idem_key)
);

-- Products the user personally saved for quick re-logging.
CREATE TABLE IF NOT EXISTS saved_products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    default_unit TEXT CHECK (default_unit IN ('mcg', 'mg', 'IU', 'units', 'mL')),
    notes        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, name)
);

-- App-level metadata (schema version markers, one-off migration stamps).
-- Not user health data; nothing here is exported as part of a user's records.
CREATE TABLE IF NOT EXISTS app_meta (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_symptoms_user ON symptoms(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_products_user ON saved_products(user_id);
CREATE INDEX IF NOT EXISTS idx_observations_user ON observations(user_id);
"""


def connect(db_path=DEFAULT_DB_PATH):
    """Open a connection with foreign keys and Row access enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=DEFAULT_DB_PATH):
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    # Migrate pre-existing databases (tables created before new columns).
    for column, ddl in (
        ("age", "ALTER TABLE users ADD COLUMN age INTEGER"),
        ("tracking_note", "ALTER TABLE users ADD COLUMN tracking_note TEXT NOT NULL DEFAULT ''"),
        ("consent_ack", "ALTER TABLE users ADD COLUMN consent_ack INTEGER NOT NULL DEFAULT 0"),
        ("review_status", "ALTER TABLE catalog ADD COLUMN review_status TEXT NOT NULL DEFAULT 'verified'"),
        ("source_type", "ALTER TABLE catalog ADD COLUMN source_type TEXT NOT NULL DEFAULT 'fda'"),
        ("last_reviewed", "ALTER TABLE catalog ADD COLUMN last_reviewed TEXT"),
        ("goal_data", "ALTER TABLE usage_log ADD COLUMN goal_data TEXT"),
        ("aliases", "ALTER TABLE catalog ADD COLUMN aliases TEXT"),
        ("custom_text", "ALTER TABLE user_goals ADD COLUMN custom_text TEXT NOT NULL DEFAULT ''"),
        ("corrections", "ALTER TABLE usage_log ADD COLUMN corrections TEXT"),
        ("obs_corrections", "ALTER TABLE observations ADD COLUMN corrections TEXT"),
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()
