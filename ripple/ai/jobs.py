"""The three AI jobs and the code checks around them.

    Job 1  link extractor   (claude-haiku-5-5)  filing sections  -> candidate links
    Job 2  event checker    (claude-haiku-5-5)  news / 8-K items -> events
    Job 3  ripple explainer (claude-opus-5-5)   event + paths    -> ranked, explained impacts

All three are OFF until ANTHROPIC_API_KEY is set and RIPPLE_AI_ENABLED=1.
`--dry-run` shows exactly what would be sent, without sending it.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

from .. import config, db, events as ev_mod, tracer
from ..matching import NameIndex
from ..text import quote_in_text
from . import prompts
from .client import AIDisabled, ai_ready, build_request, call_json

MAX_SECTION_CHARS = 120_000   # keep each job-1 request a sensible size
USEFUL_SECTIONS = ("item_1", "item_1a", "customer_concentration", "full")
RIPPLE_SEVERITY_THRESHOLD = 3  # severity 3+ gets a ripple report automatically


def _today() -> str:
    return dt.date.today().isoformat()


# ======================================================================= Job 1
def link_extractor_requests(conn: sqlite3.Connection, limit: int = 5) -> list[tuple[int, dict]]:
    rows = conn.execute(
        f"""SELECT s.id, s.section, s.text, d.doc_type, d.published_at, n.name AS company_name
            FROM document_sections s JOIN documents d ON d.id = s.document_id
            LEFT JOIN nodes n ON n.id = d.company_id
            WHERE s.processed = 0 AND s.keyword_hits > 0 AND s.section IN ({','.join('?' * len(USEFUL_SECTIONS))})
            ORDER BY s.keyword_hits DESC LIMIT ?""", (*USEFUL_SECTIONS, limit)).fetchall()
    out = []
    for r in rows:
        user = prompts.LINK_EXTRACTOR_USER.format(
            company_name=r["company_name"] or "unknown", doc_type=r["doc_type"], published_at=r["published_at"],
            section=r["section"], section_text=r["text"][:MAX_SECTION_CHARS])
        out.append((r["id"], build_request(config.MODEL_LINK_EXTRACTOR, prompts.LINK_EXTRACTOR_SYSTEM, user,
                                           prompts.LINK_EXTRACTOR_SCHEMA, max_tokens=16000)))
    return out


def check_and_store_links(conn: sqlite3.Connection, section_id: int, reply: dict, verify_text: str | None = None) -> dict:
    """The checker (code part): verbatim quote check, name matching, duplicate merging."""
    sec = conn.execute("""SELECT s.*, d.text AS doc_text, d.company_id, d.published_at
                          FROM document_sections s JOIN documents d ON d.id = s.document_id WHERE s.id=?""",
                       (section_id,)).fetchone()
    names = NameIndex(conn)
    stats = {"linked": 0, "needs_review": 0, "rejected": 0}
    for item in reply.get("links", []):
        verified = quote_in_text(item.get("quote", ""), verify_text if verify_text is not None else (sec["doc_text"] or sec["text"]))
        matched = names.match(item.get("other_party"))
        status, reason, link_id = "needs_review", None, None
        if not verified:
            status, reason = "rejected", "quote not found word for word in the document"
        elif not sec["company_id"]:
            reason = "document has no company"
        elif not item.get("other_party"):
            reason = "unnamed other party (placeholder: fill from news or customs data)"
        elif not matched:
            reason = f"'{item['other_party']}' does not match any node (add an alias or a new node)"
        elif matched == sec["company_id"]:
            status, reason = "rejected", "link from a company to itself"
        else:
            filer, other = sec["company_id"], matched
            a, b = (other, filer) if item["direction"] == "other_to_filer" and item["type"] == "supplies" else (filer, other)
            link_id = _merge_link(conn, a, b, item, sec)
            status = "linked"
        conn.execute("""INSERT INTO link_candidates (document_id, section, filer_node, other_party, matched_node, type,
                        direction, what, share, quote, quote_verified, status, reason, link_id)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (sec["document_id"], sec["section"], sec["company_id"], item.get("other_party"), matched,
                      item.get("type"), item.get("direction"), item.get("what"), item.get("share"),
                      item.get("quote", ""), int(verified), status, reason, link_id))
        stats[status] += 1
    conn.execute("UPDATE document_sections SET processed=1 WHERE id=?", (section_id,))
    conn.execute("""UPDATE documents SET processed=1 WHERE id=? AND NOT EXISTS
                    (SELECT 1 FROM document_sections WHERE document_id=? AND processed=0)""",
                 (sec["document_id"], sec["document_id"]))
    conn.commit()
    return stats


def _merge_link(conn, from_node, to_node, item, sec) -> str:
    """Same link found again = one link with another source (never a duplicate link)."""
    row = conn.execute("SELECT id FROM links WHERE from_node=? AND to_node=? AND type=? AND is_sample=0",
                       (from_node, to_node, item["type"])).fetchone()
    date = sec["published_at"] or _today()
    if row:
        link_id = row["id"]
        conn.execute("UPDATE links SET last_confirmed=MAX(COALESCE(last_confirmed,''), ?), share=COALESCE(?, share) WHERE id=?",
                     (date, item.get("share"), link_id))
    else:
        link_id = db.next_id(conn, "links", "link")
        # Stated in a filing = high confidence. Every new link waits in the review queue
        # (pending_review) for the first hand check, as the build plan asks.
        conn.execute("""INSERT INTO links (id, from_node, to_node, type, what, share, confidence, status, first_seen, last_confirmed)
                        VALUES (?,?,?,?,?,?, 'high', 'pending_review', ?, ?)""",
                     (link_id, from_node, to_node, item["type"], item.get("what"), item.get("share"), date, date))
    conn.execute("INSERT OR IGNORE INTO link_sources (link_id, document_id, quote, quote_verified) VALUES (?,?,?,1)",
                 (link_id, sec["document_id"], item["quote"]))
    return link_id


def run_link_extractor(conn, dry_run=False, limit=5):
    reqs = link_extractor_requests(conn, limit)
    if dry_run:
        return {"would_send": len(reqs), "requests": [{"section_id": sid, **_preview(r)} for sid, r in reqs]}
    results = []
    for sid, req in reqs:
        reply = call_json("link_extractor", req, conn, ref=f"section:{sid}")
        results.append({"section_id": sid, **check_and_store_links(conn, sid, reply)})
    return {"processed": results}


def submit_link_extractor_batch(conn, limit=500):
    """Cheaper bulk run via the Message Batches API (50% price, results within 24h)."""
    ok, why = ai_ready()
    if not ok:
        raise AIDisabled(why)
    import anthropic
    from anthropic.types.messages.batch_create_params import Request
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    reqs = link_extractor_requests(conn, limit)
    batch = client.messages.batches.create(requests=[Request(custom_id=f"section-{sid}", params=r) for sid, r in reqs])
    return {"batch_id": batch.id, "requests": len(reqs)}


def collect_link_extractor_batch(conn, batch_id: str):
    import anthropic
    from .client import parse_json_reply
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    if client.messages.batches.retrieve(batch_id).processing_status != "ended":
        return {"status": "still processing"}
    out = []
    for res in client.messages.batches.results(batch_id):
        sid = int(res.custom_id.split("-", 1)[1])
        if res.result.type != "succeeded":
            out.append({"section_id": sid, "error": res.result.type})
            continue
        msg = res.result.message
        conn.execute("INSERT INTO ai_usage (job, model, input_tokens, output_tokens, ref) VALUES (?,?,?,?,?)",
                     ("link_extractor_batch", msg.model, msg.usage.input_tokens, msg.usage.output_tokens, f"section:{sid}"))
        out.append({"section_id": sid, **check_and_store_links(conn, sid, parse_json_reply(msg))})
    return {"processed": out}


# ======================================================================= Job 2
def event_checker_requests(conn: sqlite3.Connection, limit: int = 20, record_skips: bool = True) -> list[tuple[str, list[str], dict]]:
    names = NameIndex(conn)
    rows = conn.execute(
        """SELECT d.id, d.text, d.doc_type FROM documents d
           WHERE (d.doc_type IN ('news', '8-K', '6-K')) AND d.source != 'sample'
             AND NOT EXISTS (SELECT 1 FROM event_checks c WHERE c.document_id = d.id)
           ORDER BY d.published_at DESC LIMIT ?""", (limit,)).fetchall()
    out = []
    for r in rows:
        text = (r["text"] or "")[:6000]
        matched = names.find_in_text(text)
        if not matched:
            if not record_skips:
                continue
            conn.execute("INSERT INTO event_checks (document_id, result) VALUES (?, ?)",
                         (r["id"], json.dumps({"skipped": "mentions no map node"})))
            continue
        listing = ", ".join(f"{m}: {names.names[m]}" for m in matched)
        user = prompts.EVENT_CHECKER_USER.format(matched_nodes=listing, headline_and_summary=text)
        out.append((r["id"], matched, build_request(config.MODEL_EVENT_CHECKER, prompts.EVENT_CHECKER_SYSTEM, user,
                                                     prompts.EVENT_CHECKER_SCHEMA, max_tokens=2000)))
    conn.commit()
    return out


def store_event_check(conn, document_id: str, matched: list[str], reply: dict) -> str | None:
    """Code checks on job 2's answer, then logs a new event if it is one."""
    event_id = None
    affected = [n for n in reply.get("affected_nodes", []) if n in matched]  # only nodes actually mentioned
    sev = reply.get("severity")
    valid = (reply.get("is_event") and affected and isinstance(sev, int) and 1 <= sev <= 5
             and reply.get("event_type") in ("disruption", "shortage", "new_contract", "policy", "price_spike", "capacity_change"))
    if valid:
        doc = conn.execute("SELECT published_at FROM documents WHERE id=?", (document_id,)).fetchone()
        event_id = db.next_id(conn, "events", "evt", width=4)
        conn.execute("""INSERT INTO events (id, title, event_type, affected_nodes, severity, started_at, source_documents, status, one_line)
                        VALUES (?,?,?,?,?,?,?, 'new', ?)""",
                     (event_id, reply["one_line"][:200], reply["event_type"], json.dumps(affected), sev,
                      doc["published_at"] if doc else _today(), json.dumps([document_id]), reply["one_line"]))
    conn.execute("INSERT OR REPLACE INTO event_checks (document_id, result, event_id) VALUES (?,?,?)",
                 (document_id, json.dumps(reply), event_id))
    conn.commit()
    return event_id


def run_event_checker(conn, dry_run=False, limit=20):
    reqs = event_checker_requests(conn, limit, record_skips=not dry_run)
    if dry_run:
        return {"would_send": len(reqs), "requests": [{"document_id": d, "matched": m, **_preview(r)} for d, m, r in reqs]}
    out = []
    for doc_id, matched, req in reqs:
        reply = call_json("event_checker", req, conn, ref=f"doc:{doc_id}")
        event_id = store_event_check(conn, doc_id, matched, reply)
        out.append({"document_id": doc_id, "event_id": event_id, "severity": reply.get("severity")})
        # Severity 3+ automatically gets a ripple report; 1-2 just get logged.
        if event_id and reply.get("severity", 0) >= RIPPLE_SEVERITY_THRESHOLD:
            out[-1]["ripple"] = run_ripple_explainer(conn, event_id=event_id)
    return {"checked": out}


# ======================================================================= Job 3
def ripple_explainer_request(conn, event_id: str, before: str | None = None, include_sample: bool = False):
    event = ev_mod.get_event(conn, event_id)
    include_sample = include_sample or bool(event.get("is_sample"))  # SAMPLE events trace over SAMPLE links
    candidates, links = ev_mod.candidate_impacts(conn, event, before=before, include_sample=include_sample)
    snippets = []
    for d in event["source_documents"]:
        doc = conn.execute("SELECT doc_type, published_at, url, text FROM documents WHERE id=?", (d,)).fetchone()
        if doc:
            snippets.append(f"- [{d}] {doc['doc_type']} {doc['published_at']} {doc['url'] or ''}\n  {(doc['text'] or '')[:1500]}")
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM nodes")}
    blocks = []
    for c in candidates:
        lines = [f"[{c['node_id']}] {names.get(c['node_id'], c['node_id'])} - exposure {c['exposure_score']}"
                 + (" - POSSIBLE WINNER (also makes the hit material)" if c.get("winner_candidate") else "")]
        lines.append("  path: " + " -> ".join(names.get(n, n) for n in c["path"]))
        for lid in c["path_links"]:
            l: tracer.Link = links[lid]
            q = (l.quotes[0]["quote"] if l.quotes else "no quote")
            share = f", share {l.share}%" if l.share is not None else ""
            lines.append(f"  link {lid}: {names.get(l.from_node)} {l.type} {names.get(l.to_node)} ({l.what or ''}{share}; "
                         f"{l.confidence} confidence; last confirmed {l.last_confirmed}) quote: \"{q}\"")
        blocks.append("\n".join(lines))
    user = prompts.RIPPLE_EXPLAINER_USER.format(
        event_title=event["title"], event_type=event["event_type"], severity=event["severity"],
        started_at=event["started_at"], event_source_snippets="\n".join(snippets) or "(none stored)",
        paths_with_scores_and_quotes="\n\n".join(blocks) or "(no paths found)")
    req = build_request(config.MODEL_RIPPLE_EXPLAINER, prompts.RIPPLE_EXPLAINER_SYSTEM, user,
                        prompts.RIPPLE_EXPLAINER_SCHEMA, max_tokens=64000, effort="high")
    req["thinking"] = {"type": "adaptive"}
    return event, candidates, req


def store_explanation(conn, event_id: str, candidates: list[dict], reply: dict) -> dict:
    """Code checks on job 3's answer before saving."""
    known = {c["node_id"] for c in candidates}
    names = NameIndex(conn)
    explanations = {}
    for imp in reply.get("impacts", []):
        nid = imp["company"] if imp["company"] in known else names.match(imp["company"])
        nid = nid or imp["company"]
        if imp.get("uses_general_knowledge"):
            imp["confidence"] = "low"  # anything resting on general knowledge is marked low confidence
        explanations[nid] = imp
    result = ev_mod.save_impacts(conn, event_id, candidates, explanations)  # drops invented companies
    conn.execute("UPDATE events SET summary=?, biggest_unknowns=? WHERE id=?",
                 (reply.get("summary"), json.dumps(reply.get("biggest_unknowns", [])), event_id))
    conn.commit()
    return result


def run_ripple_explainer(conn, event_id: str | None = None, dry_run=False, before: str | None = None):
    if not event_id:
        row = conn.execute("SELECT id FROM events WHERE status='new' AND is_sample=0 ORDER BY severity DESC LIMIT 1").fetchone()
        if not row:
            return {"message": "no new events to explain"}
        event_id = row["id"]
    event, candidates, req = ripple_explainer_request(conn, event_id, before=before)
    if dry_run:
        return {"event_id": event_id, "companies_reached": len(candidates), **_preview(req)}
    reply = call_json("ripple_explainer", req, conn, ref=event_id, stream=True, fallback=True)
    return {"event_id": event_id, **store_explanation(conn, event_id, candidates, reply)}


# ======================================================================= entry
def _preview(req: dict) -> dict:
    return {"model": req["model"], "max_tokens": req["max_tokens"], "system": req["system"],
            "user_prompt": req["messages"][0]["content"]}


def run(conn, job: str, dry_run: bool = False, limit: int = 5, event_id: str | None = None):
    ok, why = ai_ready()
    if not ok and not dry_run:
        return {"switched_off": why, "tip": "Use --dry-run to see what would be sent."}
    if job == "extract-links":
        return run_link_extractor(conn, dry_run, limit)
    if job == "check-events":
        return run_event_checker(conn, dry_run, limit)
    return run_ripple_explainer(conn, event_id=event_id, dry_run=dry_run)
