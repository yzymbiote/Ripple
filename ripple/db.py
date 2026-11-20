"""The Ripple database (SQLite, one file at data/ripple.db).

Tables follow the "Data model" section of the build plan:
documents, nodes, links, link_sources, events, impacts, followups.

Two small helper tables are added (see DECISIONS.md):
- document_sections: the cut-out parts of a filing (Item 1, Item 1A, ...)
  so the AI only reads the parts that matter.
- ai_usage: tokens used per AI call, so you can see where money goes.

Safety rule from the plan: "No link exists without a source (the database
refuses it)". Triggers below refuse to mark a link `approved` unless it has
at least one source whose quote was verified word for word.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,              -- doc_000123
    source        TEXT NOT NULL,                 -- sec_edgar, opendart, edinet, gdelt, ...
    url           TEXT,
    doc_type      TEXT NOT NULL,                 -- 10-K, 20-F, 8-K, news, bill_of_lading ...
    company_id    TEXT REFERENCES nodes(id),
    published_at  TEXT,                          -- YYYY-MM-DD
    collected_at  TEXT NOT NULL,                 -- YYYY-MM-DD HH:MM:SS (UTC)
    text          TEXT,
    processed     INTEGER NOT NULL DEFAULT 0,    -- has the link extractor read it?
    external_id   TEXT,                          -- e.g. SEC accession number
    UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS document_sections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   TEXT NOT NULL REFERENCES documents(id),
    section       TEXT NOT NULL,                 -- item_1, item_1a, customer_concentration
    text          TEXT NOT NULL,
    keyword_hits  INTEGER NOT NULL DEFAULT 0,    -- supplier/customer keywords found
    processed     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (document_id, section)
);

CREATE TABLE IF NOT EXISTS nodes (
    id        TEXT PRIMARY KEY,                  -- sk_hynix, ras_laffan, helium
    kind      TEXT NOT NULL CHECK (kind IN ('company','place','material','part')),
    name      TEXT NOT NULL,
    aliases   TEXT NOT NULL DEFAULT '[]',        -- JSON list
    layer     TEXT CHECK (layer IN ('memory','packaging','power','materials','buyers') OR layer IS NULL),
    ticker    TEXT,
    country   TEXT,
    notes     TEXT,
    extra     TEXT NOT NULL DEFAULT '{}'         -- JSON: sec_cik, dart_stock_code, ...
);

CREATE TABLE IF NOT EXISTS links (
    id              TEXT PRIMARY KEY,            -- link_000456
    from_node       TEXT NOT NULL REFERENCES nodes(id),
    to_node         TEXT NOT NULL REFERENCES nodes(id),
    type            TEXT NOT NULL CHECK (type IN ('supplies','makes_in','uses','produces')),
    what            TEXT,
    share           REAL,                        -- % if disclosed
    confidence      TEXT NOT NULL CHECK (confidence IN ('high','medium','low')),
    status          TEXT NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('approved','pending_review','rejected')),
    first_seen      TEXT,
    last_confirmed  TEXT,
    is_sample       INTEGER NOT NULL DEFAULT 0   -- 1 = hand-made SAMPLE data, not real evidence
);

CREATE TABLE IF NOT EXISTS link_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id         TEXT NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    document_id     TEXT NOT NULL REFERENCES documents(id),
    quote           TEXT NOT NULL,
    quote_verified  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (link_id, document_id, quote)
);

CREATE TABLE IF NOT EXISTS events (
    id                TEXT PRIMARY KEY,          -- evt_0042
    title             TEXT NOT NULL,
    event_type        TEXT NOT NULL CHECK (event_type IN
                      ('disruption','shortage','new_contract','policy','price_spike','capacity_change')),
    affected_nodes    TEXT NOT NULL DEFAULT '[]',  -- JSON list of node ids
    severity          INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 5),
    started_at        TEXT,
    source_documents  TEXT NOT NULL DEFAULT '[]',  -- JSON list of document ids
    status            TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','analysed','published')),
    one_line          TEXT,
    summary           TEXT,
    biggest_unknowns  TEXT NOT NULL DEFAULT '[]',  -- JSON list
    is_sample         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS impacts (
    event_id         TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    node_id          TEXT NOT NULL REFERENCES nodes(id),
    direction        TEXT NOT NULL CHECK (direction IN ('hurt','helped','unclear')),
    exposure_score   REAL NOT NULL CHECK (exposure_score BETWEEN 0 AND 100),
    path             TEXT NOT NULL DEFAULT '[]', -- JSON list of node ids
    path_links       TEXT NOT NULL DEFAULT '[]', -- JSON list of link ids
    explanation      TEXT,
    how_much         TEXT,
    timing           TEXT,
    what_would_change_this TEXT,
    confidence       TEXT CHECK (confidence IN ('high','medium','low')),
    PRIMARY KEY (event_id, node_id)
);

CREATE TABLE IF NOT EXISTS followups (
    event_id      TEXT NOT NULL,
    node_id       TEXT NOT NULL,
    checked_at    TEXT NOT NULL CHECK (checked_at IN ('1d','1w','1m')),
    price_change  REAL,                          -- stock move vs its sector, in %
    notes         TEXT,
    PRIMARY KEY (event_id, node_id, checked_at),
    FOREIGN KEY (event_id, node_id) REFERENCES impacts(event_id, node_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_usage (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job            TEXT NOT NULL,
    model          TEXT NOT NULL,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    ref            TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Job 1 output before it becomes a link: every extracted relationship, checked by code.
CREATE TABLE IF NOT EXISTS link_candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     TEXT NOT NULL REFERENCES documents(id),
    section         TEXT,
    filer_node      TEXT REFERENCES nodes(id),
    other_party     TEXT,                        -- name as written in the filing (NULL if unnamed)
    matched_node    TEXT REFERENCES nodes(id),
    type            TEXT,
    direction       TEXT,
    what            TEXT,
    share           REAL,
    quote           TEXT NOT NULL,
    quote_verified  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'needs_review'
                    CHECK (status IN ('linked','needs_review','rejected')),
    reason          TEXT,
    link_id         TEXT REFERENCES links(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Job 2 output: which documents the event checker has already judged (never re-read).
CREATE TABLE IF NOT EXISTS event_checks (
    document_id  TEXT PRIMARY KEY REFERENCES documents(id),
    result       TEXT NOT NULL,                  -- JSON reply
    event_id     TEXT REFERENCES events(id),
    checked_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_links_from ON links(from_node);
CREATE INDEX IF NOT EXISTS idx_links_to ON links(to_node);
CREATE INDEX IF NOT EXISTS idx_docs_company ON documents(company_id);

-- "No link exists without a source": an approved link must have a verified quote.
CREATE TRIGGER IF NOT EXISTS links_need_source_insert
BEFORE INSERT ON links
WHEN NEW.status = 'approved'
BEGIN
    SELECT RAISE(ABORT, 'A link cannot be inserted as approved: add a verified source first, then approve it.');
END;

CREATE TRIGGER IF NOT EXISTS links_need_source_update
BEFORE UPDATE OF status ON links
WHEN NEW.status = 'approved'
 AND NOT EXISTS (SELECT 1 FROM link_sources s WHERE s.link_id = NEW.id AND s.quote_verified = 1)
BEGIN
    SELECT RAISE(ABORT, 'A link cannot be approved without a source whose quote was verified word for word.');
END;

CREATE TRIGGER IF NOT EXISTS link_sources_keep_one
BEFORE DELETE ON link_sources
WHEN OLD.quote_verified = 1
 AND (SELECT status FROM links WHERE id = OLD.link_id) = 'approved'
 AND NOT EXISTS (SELECT 1 FROM link_sources s WHERE s.link_id = OLD.link_id
                 AND s.quote_verified = 1 AND s.id != OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'Cannot remove the last verified source of an approved link.');
END;
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after the first version; added to older databases automatically.
_LATE_COLUMNS = {"events": {"one_line": "TEXT"}}


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for table, cols in _LATE_COLUMNS.items():
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, typ in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    conn.commit()


def next_id(conn: sqlite3.Connection, table: str, prefix: str, width: int = 6) -> str:
    """Return the next readable id like doc_000124 for a table."""
    row = conn.execute(
        f"SELECT id FROM {table} WHERE id LIKE ? ORDER BY id DESC LIMIT 1", (prefix + "_%",)
    ).fetchone()
    n = 0
    if row:
        try:
            n = int(row["id"].rsplit("_", 1)[1])
        except ValueError:
            n = 0
    return f"{prefix}_{n + 1:0{width}d}"


def node_extra(row: sqlite3.Row) -> dict:
    return json.loads(row["extra"] or "{}")
