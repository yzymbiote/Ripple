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
EVENTS_FILE = config.DATA_DIR / "sample" / "sample_events.json"


def remove_sample(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM followups WHERE event_id IN (SELECT id FROM events WHERE is_sample=1)")
    conn.execute("DELETE FROM impacts WHERE event_id IN (SELECT id FROM events WHERE is_sample=1)")
    conn.execute("DELETE FROM events WHERE is_sample=1")
    conn.execute("UPDATE links SET status='pending_review' WHERE is_sample=1")
    conn.execute("DELETE FROM link_sources WHERE link_id IN (SELECT id FROM links WHERE is_sample=1)")
    conn.execute("DELETE FROM links WHERE is_sample=1")
    conn.execute("DELETE FROM documents WHERE source='sample'")
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
    n_events = load_sample_events(conn)
    return f"Loaded {len(data['links'])} SAMPLE links and {n_events} SAMPLE events (all marked is_sample=1)."


def load_sample_events(conn: sqlite3.Connection) -> int:
    from .events import candidate_impacts, save_impacts
    data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for ev in data["events"]:
        doc_ids = []
        for i, src in enumerate(ev.get("sources", []), 1):
            doc_id = f"doc_sample_{ev['id'][-4:]}_{i}"
            conn.execute("""INSERT INTO documents (id, source, url, doc_type, published_at, collected_at, text, processed, external_id)
                            VALUES (?, 'sample', ?, 'news', ?, ?, ?, 1, ?)""",
                         (doc_id, src.get("url"), src.get("date"), now, src["title"], doc_id))
            doc_ids.append(doc_id)
        conn.execute("""INSERT INTO events (id, title, event_type, affected_nodes, severity, started_at, source_documents,
                                            status, one_line, summary, biggest_unknowns, is_sample)
                        VALUES (?,?,?,?,?,?,?, 'new', ?,?,?, 1)""",
                     (ev["id"], ev["title"], ev["event_type"], json.dumps(ev["affected_nodes"]), ev["severity"],
                      ev["started_at"], json.dumps(doc_ids), ev["one_line"], ev["summary"],
                      json.dumps(ev.get("biggest_unknowns", []))))
        event = {"event_type": ev["event_type"], "affected_nodes": ev["affected_nodes"]}
        candidates, _ = candidate_impacts(conn, event, before=ev.get("trace_before"))
        save_impacts(conn, ev["id"], candidates, ev.get("impacts"))
        conn.execute("UPDATE events SET status='published' WHERE id=?", (ev["id"],))
        stored = {r[0] for r in conn.execute("SELECT node_id FROM impacts WHERE event_id=?", (ev["id"],))}
        for node_id, moves in ev.get("followups", {}).items():
            if node_id not in stored:
                continue
            for when, change in moves.items():
                conn.execute("INSERT INTO followups (event_id, node_id, checked_at, price_change, notes) VALUES (?,?,?,?,?)",
                             (ev["id"], node_id, when, change, "SAMPLE: made-up price move"))
    conn.commit()
    return len(data["events"])
