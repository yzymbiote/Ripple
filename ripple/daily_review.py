"""Daily review by Claude (switched on in data/settings.json: "claude_reviews": true).

    python -m ripple review-list            -> ai_work/review.json: every pending link and candidate, with quotes
    python -m ripple review-apply FILE      -> apply Claude's decisions (approve / reject / keep, with a reason)

Every decision is logged in ai_work/history/<date>-review-log.json, so any of them can be checked or undone.
The database's own rule still applies: nothing can be approved without a quote verified word for word.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

from . import config, review_server
from .queue import HISTORY_DIR, WORK_DIR

REVIEW_FILE = WORK_DIR / "review.json"


def enabled() -> bool:
    try:
        return bool(json.loads((config.DATA_DIR / "settings.json").read_text(encoding="utf-8")).get("claude_reviews"))
    except (OSError, ValueError):
        return False


def build_list(conn: sqlite3.Connection) -> dict:
    data = review_server.review_data(conn)
    names = {k: v["name"] for k, v in data["nodes"].items()}
    links = [{"link_id": l["id"], "claim": f"{names.get(l['from_node'])} {l['type']} {names.get(l['to_node'])}",
              "from_node": l["from_node"], "type": l["type"], "to_node": l["to_node"], "what": l["what"],
              "share": l["share"], "confidence": l["confidence"],
              "quotes": [{"quote": s["quote"], "verified": bool(s["quote_verified"]), "doc": f"{s['doc_type']} {s['published_at']}"}
                         for s in l["sources"]]}
             for l in data["links"] if l["status"] == "pending_review"]
    cands = [{"candidate_id": c["id"], "filer": names.get(c["filer_node"]), "type": c["type"], "direction": c["direction"],
              "other_party": c["other_party"], "what": c["what"], "share": c["share"], "quote": c["quote"],
              "verified": bool(c["quote_verified"]), "reason_code_gave": c["reason"]} for c in data["candidates"]]
    out = {"prepared_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "pending_links": links, "candidates": cands,
           "map_nodes": {k: v["name"] for k, v in data["nodes"].items()}}
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"pending_links": len(links), "candidates": len(cands), "file": str(REVIEW_FILE)}


def apply(conn: sqlite3.Connection, decisions: dict) -> dict:
    """decisions = {"links": [{"link_id", "decision": approve|reject|keep, "confidence"?: high|medium|low, "reason"}],
                    "candidates": [{"candidate_id", "decision": link|placeholder|reject|keep, "node"?: id, "reason"}]}"""
    saved = review_server._save
    review_server._save = lambda c: c.commit()
    log = {"applied_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "links": [], "candidates": []}
    try:
        for d in decisions.get("links", []):
            lid, dec, res = d.get("link_id"), d.get("decision"), None
            if dec == "keep":
                res = {"ok": True}
            elif dec in ("approve", "reject"):
                if dec == "approve" and d.get("confidence") in ("high", "medium", "low"):
                    row = conn.execute("SELECT * FROM links WHERE id=?", (lid,)).fetchone()
                    if row and row["confidence"] != d["confidence"]:
                        review_server.act_on_link(conn, lid, {"action": "edit", "fields": {
                            "from_node": row["from_node"], "to_node": row["to_node"], "type": row["type"],
                            "what": row["what"], "share": "" if row["share"] is None else row["share"], "confidence": d["confidence"]}})
                res = review_server.act_on_link(conn, lid, {"action": dec})
            else:
                res = {"error": f"unknown decision {dec}"}
            log["links"].append({**d, "result": res})
        for d in decisions.get("candidates", []):
            cid, dec = d.get("candidate_id"), d.get("decision")
            if dec == "keep":
                res = {"ok": True}
            elif dec == "link":
                res = review_server.act_on_candidate(conn, int(cid), {"action": "link", "other_node": d.get("node"), "add_alias": True})
            elif dec in ("placeholder", "reject"):
                res = review_server.act_on_candidate(conn, int(cid), {"action": dec})
            else:
                res = {"error": f"unknown decision {dec}"}
            log["candidates"].append({**d, "result": res})
        conn.commit()
    finally:
        review_server._save = saved
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    (HISTORY_DIR / f"{stamp}-review-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {}
    for d in log["links"] + log["candidates"]:
        key = d.get("decision") if d["result"].get("ok") else "error"
        counts[key] = counts.get(key, 0) + 1
    return {"counts": counts, "errors": [d for d in log["links"] + log["candidates"] if not d["result"].get("ok")]}
