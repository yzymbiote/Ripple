"""Turn an event into stored impacts: run the tracer, then attach explanations.

Used by the SAMPLE loader now, and by the ripple explainer (AI job 3) later.
Kept separate from the website so later features (alerts, earnings signals)
can reuse it, as the build plan asks.

Guard against invented impacts: an explanation is only stored for a company
the tracer actually reached (or found as a possible winner). Anything else is
dropped and reported back.
"""
from __future__ import annotations

import json
import sqlite3

from . import tracer

WINNER_SCALE = 0.5  # a possible winner's score is a rough "how much it could gain", kept below direct exposure
HURTFUL_TYPES = {"disruption", "shortage", "price_spike", "policy"}


def get_event(conn: sqlite3.Connection, event_id: str) -> dict:
    row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        raise KeyError(f"no event {event_id}")
    ev = dict(row)
    for k in ("affected_nodes", "source_documents", "biggest_unknowns"):
        ev[k] = json.loads(ev[k] or "[]")
    return ev


def candidate_impacts(conn: sqlite3.Connection, event: dict, before: str | None = None,
                      include_sample: bool = True, max_steps: int = 4) -> tuple[list[dict], dict]:
    """Every company the ripple reaches (plus possible winners), with code-made defaults."""
    g = tracer.build_graph(conn, before=before, include_sample=include_sample)
    sources = event["affected_nodes"]
    reached_all = tracer.trace(g, sources, max_steps=max_steps, companies_only=False)
    reached = [r for r in reached_all if g.nodes[r["node_id"]].get("kind") == "company"]
    default_dir = "hurt" if event["event_type"] in HURTFUL_TYPES else "unclear"
    out = []
    for r in reached:
        r = dict(r, direction=default_dir, confidence=r["path_confidence"], winner_candidate=False)
        out.append(r)
    seen = {r["node_id"] for r in out}
    links = tracer.link_index(g)
    near = {r["node_id"] for r in reached_all if r["steps"] <= 1}  # only things hit directly or one step away
    for w in tracer.possible_winners(g, sources, near):
        if w["node_id"] in seen:
            continue
        link = links[w["link_id"]]
        thing = link.to_node
        out.append({"node_id": w["node_id"], "name": w["name"], "layer": g.nodes[w["node_id"]].get("layer"),
                    "exposure_score": round(100 * WINNER_SCALE * tracer.link_strength(link), 1),
                    "path": [thing, w["node_id"]], "path_links": [w["link_id"]], "steps": 1, "path_count": 1,
                    "path_confidence": link.confidence, "all_paths": [], "direction": "unclear",
                    "confidence": "low", "winner_candidate": True, "reason": w["reason"]})
    return out, links


def save_impacts(conn: sqlite3.Connection, event_id: str, candidates: list[dict],
                 explanations: dict[str, dict] | None = None) -> dict:
    """Store impacts for an event. `explanations` maps node_id -> explainer output."""
    explanations = explanations or {}
    known = {c["node_id"] for c in candidates}
    dropped = sorted(set(explanations) - known)
    conn.execute("DELETE FROM impacts WHERE event_id=?", (event_id,))
    for c in candidates:
        e = explanations.get(c["node_id"], {})
        conn.execute(
            """INSERT INTO impacts (event_id, node_id, direction, exposure_score, path, path_links, explanation,
                                    how_much, timing, what_would_change_this, confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, c["node_id"], e.get("direction", c["direction"]), c["exposure_score"],
             json.dumps(c["path"]), json.dumps(c["path_links"]),
             e.get("why") or c.get("reason"), e.get("how_much"), e.get("timing"),
             e.get("what_would_change_this"), e.get("confidence", c["confidence"])))
    conn.execute("UPDATE events SET status='analysed' WHERE id=? AND status='new'", (event_id,))
    conn.commit()
    return {"stored": len(candidates), "explained": len(set(explanations) & known), "dropped_invented": dropped}


def add_event_from_file(conn: sqlite3.Connection, path) -> str:
    """Enter an event by hand from a JSON file (see data/events/). Sources become 'news' documents."""
    import datetime as dt
    from pathlib import Path
    ev = json.loads(Path(path).read_text(encoding="utf-8"))
    if conn.execute("SELECT 1 FROM events WHERE id=?", (ev["id"],)).fetchone():
        return ev["id"]
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    doc_ids = []
    for i, src in enumerate(ev.get("sources", []), 1):
        doc_id = f"doc_{ev['id']}_{i}"
        conn.execute("""INSERT OR IGNORE INTO documents (id, source, url, doc_type, published_at, collected_at, text, processed, external_id)
                        VALUES (?, 'manual', ?, 'news', ?, ?, ?, 1, ?)""",
                     (doc_id, src.get("url"), src.get("date"), now, src["title"], src.get("url") or doc_id))
        doc_ids.append(doc_id)
    conn.execute("""INSERT INTO events (id, title, event_type, affected_nodes, severity, started_at, source_documents, status, one_line, is_sample)
                    VALUES (?,?,?,?,?,?,?, 'new', ?, 0)""",
                 (ev["id"], ev["title"], ev["event_type"], json.dumps(ev["affected_nodes"]), ev["severity"],
                  ev.get("started_at"), json.dumps(doc_ids), ev.get("one_line")))
    conn.commit()
    return ev["id"]
