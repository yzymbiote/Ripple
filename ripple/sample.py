"""Load / remove the hand-made SAMPLE links (data/sample/sample_links.json).

They exist only to test the tracer and the website before real links exist.
Each one is stored with is_sample=1 and backed by a single SAMPLE document
whose text contains every placeholder quote, so the normal "verified source"
rule still applies to them.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

from . import config
from .text import quote_in_text

SAMPLE_FILE = config.DATA_DIR / "sample" / "sample_links.json"
SAMPLE_DOC_ID = "doc_sample_000"


def remove_sample(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM impacts WHERE event_id IN (SELECT id FROM events WHERE is_sample=1)")
    conn.execute("DELETE FROM events WHERE is_sample=1")
    conn.execute("UPDATE links SET status='pending_review' WHERE is_sample=1")
    conn.execute("DELETE FROM link_sources WHERE link_id IN (SELECT id FROM links WHERE is_sample=1)")
    conn.execute("DELETE FROM links WHERE is_sample=1")
    conn.execute("DELETE FROM documents WHERE id=?", (SAMPLE_DOC_ID,))
    conn.commit()


def load_sample_links(conn: sqlite3.Connection) -> str:
    data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    remove_sample(conn)
    text = "SAMPLE DOCUMENT - hand-made test data, not a real filing.\n" + "\n".join(l["quote"] for l in data["links"])
    conn.execute("""INSERT INTO documents (id, source, url, doc_type, company_id, published_at, collected_at, text, processed, external_id)
                    VALUES (?, 'sample', NULL, 'sample', NULL, '2025-01-01', ?, ?, 1, 'sample')""",
                 (SAMPLE_DOC_ID, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), text))
    for l in data["links"]:
        conn.execute("""INSERT INTO links (id, from_node, to_node, type, what, share, confidence, status, first_seen, last_confirmed, is_sample)
                        VALUES (?,?,?,?,?,?,?, 'pending_review', ?,?,1)""",
                     (l["id"], l["from_node"], l["to_node"], l["type"], l["what"], l["share"], l["confidence"],
                      l["first_seen"], l["last_confirmed"]))
        conn.execute("INSERT INTO link_sources (link_id, document_id, quote, quote_verified) VALUES (?,?,?,?)",
                     (l["id"], SAMPLE_DOC_ID, l["quote"], int(quote_in_text(l["quote"], text))))
        conn.execute("UPDATE links SET status='approved' WHERE id=?", (l["id"],))
    conn.commit()
    return f"Loaded {len(data['links'])} SAMPLE links (marked is_sample=1)."
