"""The daily AI work queue (zero-cost setup).

Code prepares a SMALL queue; a scheduled Claude Code session (on your normal
Claude plan) reads it, does jobs 1-3 following AI_TASKS.md, and writes its
answers to ai_work/results.json; then `python -m ripple ai-import` runs every
answer through the same code checkers as before.

    ai_work/queue.json     written by `python -m ripple ai-prepare`
    ai_work/results.json   written by the Claude session
    ai_work/history/       finished queues and results, kept for the record

Limits (per day): job 1 sections and characters are capped so the session stays
small; job 2 gets at most 30 items that mention a map node; job 3 gets at most 3
events (most severe first).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3

from . import config, events as ev_mod, tracer
from .ai import prompts
from .matching import NameIndex
from .sections import _CJK_RELATION, _RELATION, _SHARE

WORK_DIR = config.ROOT / "ai_work"
QUEUE_FILE = WORK_DIR / "queue.json"
RESULTS_FILE = WORK_DIR / "results.json"
HISTORY_DIR = WORK_DIR / "history"

MAX_JOB1_SECTIONS = 15
MAX_JOB1_CHARS_PER_SECTION = 6_000
MAX_JOB1_TOTAL_CHARS = 70_000
MAX_JOB2_ITEMS = 30
MAX_JOB2_CHARS_PER_ITEM = 1_500
MAX_JOB3_EVENTS = 3
JOB3_MIN_SEVERITY = 3

# Most useful sections first: customer notes and the annual "Business" section,
# then risk factors; 10-Q risk factors mostly repeat the 10-K, so they come last.
SECTION_PRIORITY = {"customer_concentration": 0, "item_1": 1, "full": 2, "item_1a": 3}
ANNUAL_TYPES = ("10-K", "20-F", "40-F", "annual_report_kr", "annual_report_jp")
SUPPLY_WORDS = re.compile(
    r"suppl|shortage|outage|strike|fire|explosion|earthquake|flood|plant|factory|fab\b|fabs\b|export|import|tariff|"
    r"sanction|ban\b|contract|order|capacity|production|output|shipment|port|lead time|price|halt|shut|expan|invest",
    re.I)


def excerpt(text: str, names: NameIndex | None = None, limit: int = MAX_JOB1_CHARS_PER_SECTION,
            seen: set | None = None) -> str:
    """Keep only the paragraphs that talk about customers, suppliers, sources or map nodes.

    The excerpt is cut from the section word for word, so any quote copied from it
    is also in the original filing.
    """
    paras = [p for p in text.split("\n") if p.strip()]
    keep = []
    for i, p in enumerate(paras):
        hit = (_RELATION.search(p) or _CJK_RELATION.search(p)) and (_SHARE.search(p) or len(p) > 120)
        if not hit and names is not None and len(p) > 60 and names.find_in_text(p):
            hit = True
        if hit:
            keep.append(i)
    out, total = [], 0
    for i in keep:
        p = paras[i].strip()
        if seen is not None:
            key = re.sub(r"\W+", " ", p.lower())[:300]
            if key in seen:
                continue  # same paragraph already queued today (quarterly reports repeat the annual one)
            seen.add(key)
        if total + len(p) > limit:
            break
        out.append(p)
        total += len(p) + 1
    return "\n".join(out)


def _job1_tasks(conn, names, max_sections, max_total_chars) -> list[dict]:
    rows = conn.execute(
        """SELECT s.id, s.section, s.text, s.keyword_hits, d.id AS doc_id, d.doc_type, d.published_at, d.url,
                  d.company_id, n.name AS company_name
           FROM document_sections s JOIN documents d ON d.id = s.document_id LEFT JOIN nodes n ON n.id = d.company_id
           WHERE s.processed = 0 AND s.keyword_hits > 0 AND s.text != '' AND d.source != 'sample'""").fetchall()
    def rank(r):
        annual = 0 if r["doc_type"] in ANNUAL_TYPES else 1
        return (annual, SECTION_PRIORITY.get(r["section"], 9), -(r["keyword_hits"] or 0), r["id"])
    tasks, total = [], 0
    seen_by_company: dict = {}
    for r in sorted(rows, key=rank):
        if len(tasks) >= max_sections:
            break
        if r["section"] == "full" and (r["keyword_hits"] or 0) < 2:
            continue  # short 8-Ks with barely a mention of customers/suppliers aren't worth reading
        text = excerpt(r["text"], names, seen=seen_by_company.setdefault(r["company_id"], set()))
        if not text:
            # Nothing relevant inside: mark as read so it never comes back.
            conn.execute("UPDATE document_sections SET processed=1 WHERE id=?", (r["id"],))
            continue
        if total + len(text) > max_total_chars:
            break
        total += len(text)
        tasks.append({"task_id": f"s{r['id']}", "section_id": r["id"], "company_id": r["company_id"],
                      "company_name": r["company_name"], "document_id": r["doc_id"], "doc_type": r["doc_type"],
                      "published_at": r["published_at"], "url": r["url"], "section": r["section"], "text": text})
    conn.commit()
    return tasks


def _job2_tasks(conn, names, max_items) -> list[dict]:
    since = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    rows = conn.execute(
        """SELECT d.id, d.doc_type, d.source, d.published_at, d.url, d.text, d.company_id FROM documents d
           WHERE d.source != 'sample' AND d.doc_type IN ('news', '8-K', '6-K') AND d.published_at >= ?
             AND NOT EXISTS (SELECT 1 FROM event_checks c WHERE c.document_id = d.id)
           ORDER BY d.published_at DESC, d.id DESC""", (since,)).fetchall()
    tasks = []
    for r in rows:
        if len(tasks) >= max_items:
            break
        text = (r["text"] or "").strip()
        if not text:
            continue  # text not downloaded yet; it stays unchecked and comes back next time
        if r["doc_type"] in ("8-K", "6-K"):
            # Keep the "Item x.xx" part of an 8-K, skip the cover page boilerplate.
            m = re.search(r"(?im)^\s*item\s+\d\.\d\d", text)
            text = text[m.start():] if m else text
        text = text[:MAX_JOB2_CHARS_PER_ITEM]
        matched = names.find_in_text(text)
        if r["company_id"] and r["company_id"] not in matched:
            matched.append(r["company_id"])
        relevant = matched and (r["doc_type"] != "news" or SUPPLY_WORDS.search(text))
        if not relevant:
            conn.execute("INSERT OR IGNORE INTO event_checks (document_id, result) VALUES (?, ?)",
                         (r["id"], json.dumps({"skipped": "pre-filter: no map node or no supply wording"})))
            continue
        tasks.append({"task_id": r["id"], "document_id": r["id"], "doc_type": r["doc_type"], "source": r["source"],
                      "published_at": r["published_at"], "url": r["url"], "text": text,
                      "matched_nodes": {m: names.names[m] for m in matched}})
    conn.commit()
    return tasks


def _job3_tasks(conn, max_events) -> list[dict]:
    rows = conn.execute(
        """SELECT id FROM events WHERE status='new' AND is_sample=0 AND severity >= ?
           ORDER BY severity DESC, started_at DESC LIMIT ?""", (JOB3_MIN_SEVERITY, max_events)).fetchall()
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM nodes")}
    tasks = []
    for r in rows:
        event = ev_mod.get_event(conn, r["id"])
        candidates, links = ev_mod.candidate_impacts(conn, event)
        sources = []
        for d in event["source_documents"]:
            doc = conn.execute("SELECT doc_type, published_at, url, text FROM documents WHERE id=?", (d,)).fetchone()
            if doc:
                sources.append({"document_id": d, "doc_type": doc["doc_type"], "date": doc["published_at"],
                                "url": doc["url"], "text": (doc["text"] or "")[:1500]})
        companies = []
        for c in candidates:
            path_links = []
            for lid in c["path_links"]:
                l: tracer.Link = links[lid]
                path_links.append({"link_id": lid, "from": names.get(l.from_node), "type": l.type, "to": names.get(l.to_node),
                                   "what": l.what, "share": l.share, "confidence": l.confidence,
                                   "last_confirmed": l.last_confirmed,
                                   "quote": l.quotes[0]["quote"] if l.quotes else None})
            companies.append({"company_id": c["node_id"], "name": names.get(c["node_id"]),
                              "exposure_score": c["exposure_score"], "possible_winner": bool(c.get("winner_candidate")),
                              "path": [names.get(n, n) for n in c["path"]], "links": path_links})
        tasks.append({"task_id": event["id"], "event_id": event["id"], "title": event["title"],
                      "event_type": event["event_type"], "severity": event["severity"], "started_at": event["started_at"],
                      "sources": sources, "companies_reached": companies})
    return tasks


def prepare(conn: sqlite3.Connection, max_sections: int = MAX_JOB1_SECTIONS, max_total_chars: int = MAX_JOB1_TOTAL_CHARS,
            max_items: int = MAX_JOB2_ITEMS, max_events: int = MAX_JOB3_EVENTS) -> dict:
    names = NameIndex(conn)
    queue = {
        "queue_id": dt.datetime.now(dt.timezone.utc).strftime("q%Y%m%d-%H%M%S"),
        "prepared_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "status": "ready",
        "instructions": "Follow AI_TASKS.md. Write answers to ai_work/results.json, then run: python -m ripple ai-import",
        "job1_link_extractor": _job1_tasks(conn, names, max_sections, max_total_chars),
        "job2_event_checker": _job2_tasks(conn, names, max_items),
        "job3_ripple_explainer": _job3_tasks(conn, max_events),
        "prompts": {
            "job1": {"system": prompts.LINK_EXTRACTOR_SYSTEM, "user_template": prompts.LINK_EXTRACTOR_USER},
            "job2": {"system": prompts.EVENT_CHECKER_SYSTEM, "user_template": prompts.EVENT_CHECKER_USER},
            "job3": {"system": prompts.RIPPLE_EXPLAINER_SYSTEM, "user_template": prompts.RIPPLE_EXPLAINER_USER},
        },
    }
    n = sum(len(queue[k]) for k in ("job1_link_extractor", "job2_event_checker", "job3_ripple_explainer"))
    if n == 0:
        queue["status"] = "empty"
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    if RESULTS_FILE.exists():
        RESULTS_FILE.unlink()
    return {"queue_id": queue["queue_id"], "status": queue["status"],
            "job1_sections": len(queue["job1_link_extractor"]),
            "job1_chars": sum(len(t["text"]) for t in queue["job1_link_extractor"]),
            "job2_items": len(queue["job2_event_checker"]), "job3_events": len(queue["job3_ripple_explainer"])}


def status() -> dict:
    if not QUEUE_FILE.exists():
        return {"status": "empty", "reason": "no queue file"}
    q = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    return {"queue_id": q["queue_id"], "status": q["status"], "job1": len(q["job1_link_extractor"]),
            "job2": len(q["job2_event_checker"]), "job3": len(q["job3_ripple_explainer"]),
            "results_present": RESULTS_FILE.exists()}


def import_results(conn: sqlite3.Connection, results: dict | None = None) -> dict:
    """Run the session's answers through the code checkers and store them."""
    from .ai import jobs
    queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    if results is None:
        results = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    if queue["status"] != "ready":
        return {"error": f"queue status is {queue['status']}, nothing to import"}
    if results.get("queue_id") != queue["queue_id"]:
        return {"error": f"results are for queue {results.get('queue_id')}, but the current queue is {queue['queue_id']}"}
    report = {"job1": [], "job2": [], "job3": [], "ignored": []}

    job1 = {t["task_id"]: t for t in queue["job1_link_extractor"]}
    for ans in results.get("job1", []):
        task = job1.get(ans.get("task_id"))
        if not task:
            report["ignored"].append(f"job1 answer for unknown task {ans.get('task_id')}")
            continue
        # The quote must appear word for word in the text that was actually given to Claude.
        stats = jobs.check_and_store_links(conn, task["section_id"], {"links": ans.get("links", [])},
                                           verify_text=task["text"])
        report["job1"].append({"task_id": task["task_id"], **stats})

    job2 = {t["task_id"]: t for t in queue["job2_event_checker"]}
    for ans in results.get("job2", []):
        task = job2.get(ans.get("task_id"))
        if not task:
            report["ignored"].append(f"job2 answer for unknown task {ans.get('task_id')}")
            continue
        event_id = jobs.store_event_check(conn, task["document_id"], list(task["matched_nodes"]), ans)
        report["job2"].append({"task_id": task["task_id"], "event_id": event_id})

    job3 = {t["task_id"]: t for t in queue["job3_ripple_explainer"]}
    for ans in results.get("job3", []):
        task = job3.get(ans.get("task_id"))
        if not task:
            report["ignored"].append(f"job3 answer for unknown task {ans.get('task_id')}")
            continue
        event = ev_mod.get_event(conn, task["event_id"])
        candidates, _ = ev_mod.candidate_impacts(conn, event)
        result = jobs.store_explanation(conn, task["event_id"], candidates, ans)
        conn.execute("UPDATE events SET status='published' WHERE id=?", (task["event_id"],))
        report["job3"].append({"task_id": task["task_id"], **result})

    conn.commit()
    queue["status"] = "imported"
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = queue["queue_id"]
    (HISTORY_DIR / f"{stamp}-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    (HISTORY_DIR / f"{stamp}-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if RESULTS_FILE.exists():
        RESULTS_FILE.unlink()
    return report
