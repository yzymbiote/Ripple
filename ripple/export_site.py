"""Write the website's data file (site/data/data.js) from the database.

The website reads ONLY this file, so swapping sample data for real data is
just: put real links/events in the database and run
    python -m ripple export-site --real-only

The file is plain JavaScript (`window.RIPPLE_DATA = {...}`) rather than JSON so
the pages also work when opened straight from disk (double-click), without a
web server.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from . import config

OUT = config.ROOT / "site" / "data" / "data.js"


def _json(v, default):
    try:
        return json.loads(v) if v else default
    except (TypeError, ValueError):
        return default


def build(conn: sqlite3.Connection, include_sample: bool = True) -> dict:
    sample_clause = "" if include_sample else " AND is_sample = 0"
    nodes = {}
    for r in conn.execute("SELECT * FROM nodes ORDER BY id"):
        nodes[r["id"]] = {k: r[k] for k in ("id", "kind", "name", "layer", "ticker", "country", "notes")}
        nodes[r["id"]]["aliases"] = _json(r["aliases"], [])

    links = []
    for r in conn.execute(f"SELECT * FROM links WHERE status='approved'{sample_clause} ORDER BY id"):
        sources = [{
            "quote": s["quote"], "verified": bool(s["quote_verified"]), "document_id": s["document_id"],
            "url": s["url"], "doc_type": s["doc_type"], "published_at": s["published_at"], "source": s["source"],
        } for s in conn.execute(
            """SELECT s.*, d.url, d.doc_type, d.published_at, d.source FROM link_sources s
               JOIN documents d ON d.id = s.document_id WHERE s.link_id = ?""", (r["id"],))]
        links.append({
            "id": r["id"], "from": r["from_node"], "to": r["to_node"], "type": r["type"], "what": r["what"],
            "share": r["share"], "confidence": r["confidence"], "first_seen": r["first_seen"],
            "last_confirmed": r["last_confirmed"], "is_sample": bool(r["is_sample"]), "sources": sources,
        })

    # Unnamed customers/suppliers with a disclosed share, approved as placeholders in review.
    unnamed = [{
        "company": r["filer_node"], "type": r["type"], "direction": r["direction"], "what": r["what"],
        "share": r["share"], "quote": r["quote"], "url": r["url"], "doc_type": r["doc_type"], "published_at": r["published_at"],
    } for r in conn.execute(
        """SELECT c.*, d.url, d.doc_type, d.published_at FROM link_candidates c JOIN documents d ON d.id = c.document_id
           WHERE c.status = 'placeholder' ORDER BY c.filer_node, c.share DESC""")]

    events = []
    for r in conn.execute(f"SELECT * FROM events WHERE status IN ('analysed','published'){sample_clause} "
                          "ORDER BY started_at DESC, id DESC"):
        doc_ids = _json(r["source_documents"], [])
        sources = []
        for d in doc_ids:
            doc = conn.execute("SELECT id, url, doc_type, published_at, text, source FROM documents WHERE id=?", (d,)).fetchone()
            if doc:
                title = (doc["text"] or "").split("\n", 1)[0][:200] if doc["source"] in ("sample", "news", "gdelt") else doc["doc_type"]
                sources.append({"document_id": doc["id"], "title": title, "url": doc["url"],
                                "date": doc["published_at"], "doc_type": doc["doc_type"]})
        impacts = []
        for i in conn.execute("SELECT * FROM impacts WHERE event_id=? ORDER BY exposure_score DESC", (r["id"],)):
            follow = {f["checked_at"]: f["price_change"] for f in conn.execute(
                "SELECT checked_at, price_change FROM followups WHERE event_id=? AND node_id=?", (r["id"], i["node_id"]))}
            impacts.append({
                "node_id": i["node_id"], "direction": i["direction"], "exposure_score": i["exposure_score"],
                "path": _json(i["path"], []), "path_links": _json(i["path_links"], []),
                "why": i["explanation"], "how_much": i["how_much"], "timing": i["timing"],
                "what_would_change_this": i["what_would_change_this"], "confidence": i["confidence"],
                "followups": follow,
            })
        events.append({
            "id": r["id"], "title": r["title"], "event_type": r["event_type"], "severity": r["severity"],
            "started_at": r["started_at"], "status": r["status"], "one_line": r["one_line"],
            "summary": r["summary"], "affected_nodes": _json(r["affected_nodes"], []),
            "biggest_unknowns": _json(r["biggest_unknowns"], []), "is_sample": bool(r["is_sample"]),
            "sources": sources, "impacts": impacts,
        })

    has_sample = any(l["is_sample"] for l in links) or any(e["is_sample"] for e in events)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "contains_sample_data": has_sample,
        "nodes": nodes, "links": links, "events": events, "unnamed": unnamed,
    }


def sample_build() -> dict:
    """The hand-made SAMPLE map and events, built in a throwaway in-memory database."""
    from . import db, sample
    from .seed import seed
    mem = db.connect(":memory:")
    db.init(mem)
    seed(mem)
    sample.load_sample_links(mem)
    return build(mem, include_sample=True)


def build_with_sample_fallback(conn: sqlite3.Connection) -> dict:
    """Real data first. SAMPLE data (clearly flagged) only fills what is still empty:
    - no approved real links yet  -> show the sample map
    - no published real events yet -> show the sample events (and the sample links their ripples use)
    """
    real = build(conn, include_sample=False)
    if real["links"] and real["events"]:
        return real
    sm = sample_build()
    if not real["events"]:
        real["events"] = sm["events"]
    if not real["links"]:
        real["links"] = sm["links"]
    else:
        used = {lid for e in real["events"] if e["is_sample"] for i in e["impacts"] for lid in i["path_links"]}
        real["links"] += [l for l in sm["links"] if l["id"] in used]
    real["contains_sample_data"] = True
    return real


def export(conn: sqlite3.Connection, include_sample: bool = True, out: Path = OUT) -> Path:
    data = build_with_sample_fallback(conn) if include_sample else build(conn, include_sample=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, indent=1)
    out.write_text("// Generated by `python -m ripple export-site`. Do not edit by hand.\n"
                   f"window.RIPPLE_DATA = {body};\n", encoding="utf-8")
    return out
