"""Load the seed list (data/seed/nodes.json) into the database.

Safe to run again: existing nodes are updated, not duplicated.
"""
from __future__ import annotations

import json
import sqlite3

from . import config

EXTRA_KEYS = ("filer", "sec_cik", "dart_stock_code", "edinet_sec_code")


def load_seed() -> dict:
    return json.loads(config.SEED_FILE.read_text(encoding="utf-8"))


def seed(conn: sqlite3.Connection) -> int:
    data = load_seed()
    rows = []
    for c in data["companies"]:
        extra = {k: c[k] for k in EXTRA_KEYS if k in c}
        rows.append((c["id"], "company", c["name"], json.dumps(c.get("aliases", []), ensure_ascii=False),
                     c["layer"], c.get("ticker"), c.get("country"), c.get("notes"), json.dumps(extra)))
    for n in data["places_and_materials"]:
        rows.append((n["id"], n["kind"], n["name"], json.dumps(n.get("aliases", []), ensure_ascii=False),
                     None, None, n.get("country"), n.get("notes"), "{}"))
    conn.executemany(
        """INSERT INTO nodes (id, kind, name, aliases, layer, ticker, country, notes, extra)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, name=excluded.name,
             aliases=excluded.aliases, layer=excluded.layer, ticker=excluded.ticker,
             country=excluded.country, notes=excluded.notes, extra=excluded.extra""",
        rows,
    )
    conn.commit()
    return len(rows)
