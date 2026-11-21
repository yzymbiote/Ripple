"""Automatic approval of links, used while the owner has asked Claude to handle reviews.

Switched on/off in data/settings.json ("auto_approve": true/false). When on, it runs at the end of
every `python -m ripple ai-import`. It is deliberately strict; it approves a pending link only if ALL hold:

1. the link was found in a company FILING (not news), with confidence "high";
2. at least one of its quotes was verified word for word in that filing;
3. the quote itself names the other side of the link (the counterparty, place or material),
   checked by code against the map's names and aliases, not by AI judgement.

Everything else (news links, medium/low confidence, quotes that don't name the other side) stays
pending for a person. Nothing is ever rejected automatically. Every automatic approval is listed in
the import report in ai_work/history/.
"""
from __future__ import annotations

import json
import sqlite3

from . import config
from .matching import NameIndex

SETTINGS_FILE = config.DATA_DIR / "settings.json"
FILING_SOURCES = ("sec_edgar", "opendart", "edinet")


def enabled() -> bool:
    try:
        return bool(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get("auto_approve"))
    except (OSError, ValueError):
        return False


def run(conn: sqlite3.Connection) -> dict:
    names = NameIndex(conn)
    approved, kept = [], []
    rows = conn.execute("SELECT * FROM links WHERE status='pending_review' AND is_sample=0 ORDER BY id").fetchall()
    for l in rows:
        reason = None
        if l["confidence"] != "high":
            reason = f"{l['confidence']} confidence"
        else:
            sources = conn.execute(
                """SELECT s.quote, d.company_id FROM link_sources s JOIN documents d ON d.id = s.document_id
                   WHERE s.link_id=? AND s.quote_verified=1 AND d.source IN (%s)""" % ",".join("?" * len(FILING_SOURCES)),
                (l["id"], *FILING_SOURCES)).fetchall()
            if not sources:
                reason = "no verified quote from a filing"
            else:
                ok = False
                for s in sources:
                    other = l["to_node"] if s["company_id"] == l["from_node"] else l["from_node"]
                    if other in names.find_in_text(s["quote"]):
                        ok = True
                        break
                if not ok:
                    reason = "quote doesn't name the other side"
        if reason:
            kept.append({"link": l["id"], "why_kept_pending": reason})
            continue
        conn.execute("UPDATE links SET status='approved' WHERE id=?", (l["id"],))
        approved.append({"link": l["id"], "claim": f"{l['from_node']} {l['type']} {l['to_node']}", "what": l["what"]})
    conn.commit()
    return {"auto_approved": approved, "left_pending": kept}
