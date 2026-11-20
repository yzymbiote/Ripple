"""Save / load the map's state as small text files in data/state/ (committed to git).

Why: the database file is not stored in GitHub, and every scheduled run (GitHub
Actions, the 3am Claude Code session) starts on a fresh machine. So after each
run we save everything that matters - links, sources, review decisions, events,
which sections were already read - as one JSON line per row. Bulky filing text
is NOT saved; it can always be downloaded again from the original URL.

    python -m ripple state-save     database -> data/state/*.jsonl
    python -m ripple state-load     data/state/*.jsonl -> fresh database
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import config, db
from .seed import seed

STATE_DIR = config.DATA_DIR / "state"

# table -> (columns left out, sort key). News documents keep their text (a headline is tiny).
KEEP_TEXT_SOURCES = {"gdelt"}
TABLES = {
    "documents": (set(), "id"),
    "document_sections": ({"text"}, "id"),
    "links": (set(), "id"),
    "link_sources": (set(), "id"),
    "link_candidates": (set(), "id"),
    "events": (set(), "id"),
    "impacts": (set(), "event_id, node_id"),
    "followups": (set(), "event_id, node_id, checked_at"),
    "event_checks": (set(), "document_id"),
    "ai_usage": (set(), "id"),
    "node_aliases_added": (set(), "node_id, alias"),
}


def save(conn: sqlite3.Connection, state_dir: Path = STATE_DIR) -> dict:
    state_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for table, (skip, order) in TABLES.items():
        cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})") if r["name"] not in skip]
        rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {order}").fetchall()
        with open(state_dir / f"{table}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                row = {c: r[c] for c in cols}
                if table == "documents" and row.get("source") not in KEEP_TEXT_SOURCES:
                    row.pop("text", None)  # filing text is re-downloaded when needed
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        counts[table] = len(rows)
    return counts


def _rows(state_dir: Path, table: str) -> list[dict]:
    p = state_dir / f"{table}.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _insert(conn, table, row):
    cols = list(row)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                 [row[c] for c in cols])


def load(conn: sqlite3.Connection, state_dir: Path = STATE_DIR) -> dict:
    """Rebuild a database from the saved state (filing text stays empty until re-downloaded)."""
    db.init(conn)
    seed(conn)
    counts = {}
    for table in TABLES:
        rows = _rows(state_dir, table)
        counts[table] = len(rows)
        if table == "links":
            # Insert as pending first: the database refuses an approved link before its sources exist.
            for r in rows:
                _insert(conn, "links", dict(r, status="pending_review"))
            continue
        for r in rows:
            if table == "document_sections" and "text" not in r:
                r = dict(r, text="")
            _insert(conn, table, r)
    for r in _rows(state_dir, "links"):
        if r["status"] != "pending_review":
            conn.execute("UPDATE links SET status=? WHERE id=?", (r["status"], r["id"]))
    for r in _rows(state_dir, "node_aliases_added"):
        add_alias(conn, r["node_id"], r["alias"], record=False)
    conn.commit()
    return counts


def add_alias(conn: sqlite3.Connection, node_id: str, alias: str, record: bool = True) -> None:
    """Teach the name matcher a new name for a node (e.g. from the review page)."""
    row = conn.execute("SELECT aliases FROM nodes WHERE id=?", (node_id,)).fetchone()
    if not row:
        return
    aliases = json.loads(row["aliases"] or "[]")
    if alias not in aliases:
        aliases.append(alias)
        conn.execute("UPDATE nodes SET aliases=? WHERE id=?", (json.dumps(aliases, ensure_ascii=False), node_id))
    if record:
        conn.execute("INSERT OR IGNORE INTO node_aliases_added (node_id, alias) VALUES (?, ?)", (node_id, alias))


def ensure_db() -> sqlite3.Connection:
    """Open the database; if it is missing or empty, rebuild it from data/state/."""
    fresh = not Path(config.DB_PATH).exists()
    conn = db.connect()
    db.init(conn)
    if fresh or conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0:
        load(conn)
    return conn
