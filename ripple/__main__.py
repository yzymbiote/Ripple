"""Command line for Ripple.  Run `python -m ripple --help` to see every command."""
from __future__ import annotations

import argparse
import json
import sys

from . import config, db


def cmd_init(args) -> None:
    from .seed import seed
    conn = db.connect()
    db.init(conn)
    n = seed(conn)
    print(f"Database ready at {config.DB_PATH} with {n} seed nodes.")


def cmd_status(args) -> None:
    conn = db.connect()
    db.init(conn)
    for table in ("nodes", "documents", "document_sections", "links", "link_sources",
                  "events", "impacts", "followups", "ai_usage"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:20s} {n}")
    kinds = conn.execute("SELECT kind, COUNT(*) c FROM nodes GROUP BY kind").fetchall()
    print("nodes by kind:", {r["kind"]: r["c"] for r in kinds})


def cmd_sec_verify(args) -> None:
    from .collectors import sec_edgar
    conn = db.connect()
    problems = sec_edgar.verify_ciks(conn)
    print("All SEC company numbers match SEC's ticker list." if not problems else "\n".join(problems))


def cmd_sec_collect(args) -> None:
    from .collectors import sec_edgar
    conn = db.connect()
    db.init(conn)
    companies = args.companies.split(",") if args.companies else None
    sec_edgar.collect(conn, companies=companies, quarters=args.quarters,
                      include_8k=not args.no_8k, max_8k=args.max_8k)


def cmd_cut_sections(args) -> None:
    from . import sections
    conn = db.connect()
    db.init(conn)
    n = sections.cut_all(conn, redo=args.redo)
    print(f"Cut sections for {n} document(s).")


def cmd_load_sample(args) -> None:
    from . import sample
    conn = db.connect()
    db.init(conn)
    if args.remove:
        sample.remove_sample(conn)
        print("Removed all SAMPLE links and events.")
    else:
        print(sample.load_sample_links(conn))


def cmd_trace(args) -> None:
    from . import tracer
    conn = db.connect()
    graph = tracer.build_graph(conn, before=args.before, include_sample=True)
    result = tracer.trace(graph, args.nodes.split(","), max_steps=args.steps)
    for imp in result[: args.top]:
        print(f"{imp['exposure_score']:5.1f}  {imp['node_id']:22s} {' -> '.join(imp['path'])}")


def cmd_export_site(args) -> None:
    from . import export_site
    conn = db.connect()
    path = export_site.export(conn, include_sample=not args.real_only)
    print(f"Wrote {path}")


def cmd_ai(args) -> None:
    from .ai import jobs
    conn = db.connect()
    db.init(conn)
    if args.job == "extract-links-batch":
        out = jobs.submit_link_extractor_batch(conn, limit=args.limit)
    elif args.job == "collect-batch":
        out = jobs.collect_link_extractor_batch(conn, args.batch_id)
    else:
        out = jobs.run(conn, args.job, dry_run=args.dry_run, limit=args.limit, event_id=args.event)
    print(json.dumps(out, indent=2, ensure_ascii=False)[:5000])


def cmd_collect_foreign(args) -> None:
    conn = db.connect()
    db.init(conn)
    if args.system == "opendart":
        from .collectors import opendart as mod
    else:
        from .collectors import edinet as mod
    print(mod.collect(conn))


def _conn():
    from .state import ensure_db
    return ensure_db()


def cmd_state_save(args) -> None:
    from . import state
    print(json.dumps(state.save(_conn()), indent=1))


def cmd_state_load(args) -> None:
    from . import state
    from pathlib import Path
    if Path(config.DB_PATH).exists():
        Path(config.DB_PATH).unlink()
    conn = db.connect()
    print(json.dumps(state.load(conn), indent=1))


def cmd_ai_prepare(args) -> None:
    from . import queue
    conn = _conn()
    print(json.dumps(queue.prepare(conn, max_sections=args.max_sections, max_total_chars=args.max_chars), indent=1))
    if not args.no_save:
        from . import state
        state.save(conn)


def cmd_ai_status(args) -> None:
    from . import queue
    st = queue.status()
    print(json.dumps(st, indent=1))
    # exit code 0 = there is work to do, 3 = nothing to do (the session should stop)
    if st["status"] != "ready":
        sys.exit(3)


def cmd_ai_import(args) -> None:
    from . import export_site, queue, state
    conn = _conn()
    report = queue.import_results(conn)
    print(json.dumps(report, indent=1, ensure_ascii=False)[:6000])
    if "error" in report:
        sys.exit(1)
    state.save(conn)
    export_site.export(conn, include_sample=_site_wants_sample(conn))


def cmd_ai_backup(args) -> None:
    from .ai import backup
    print(json.dumps(backup.run(), indent=1))


def _site_wants_sample(conn) -> bool:
    """Show SAMPLE events on the site only until the first real event exists."""
    return conn.execute("SELECT COUNT(*) FROM events WHERE is_sample=0").fetchone()[0] == 0


def cmd_daily_collect(args) -> None:
    """Everything code does before the 3am session: collect, cut, pre-filter, build the queue, update the site."""
    from . import export_site, queue, sections, state
    from .collectors import gdelt, sec_edgar
    conn = _conn()
    steps = {}
    try:
        steps["sec"] = sec_edgar.collect(conn, quarters=args.quarters, max_8k=8, log=lambda *_: None)
        # Re-download text only for documents that still have unread sections.
        # Only the filings the next queues will use (same order as ripple/queue.py), not the whole backlog.
        need = [r[0] for r in conn.execute("""
            SELECT s.document_id FROM document_sections s JOIN documents d ON d.id = s.document_id
            WHERE s.processed=0 AND s.text='' AND s.keyword_hits > 0
            ORDER BY CASE WHEN d.doc_type IN ('10-K','20-F','40-F') THEN 0 ELSE 1 END,
                     CASE s.section WHEN 'customer_concentration' THEN 0 WHEN 'item_1' THEN 1 WHEN 'full' THEN 2 ELSE 3 END,
                     s.keyword_hits DESC LIMIT 40""")]
        # ...plus recent 8-Ks/6-Ks the event checker hasn't seen yet.
        need += [r[0] for r in conn.execute("""
            SELECT d.id FROM documents d WHERE d.doc_type IN ('8-K','6-K') AND d.text IS NULL
              AND d.published_at >= date('now','-7 day')
              AND NOT EXISTS (SELECT 1 FROM event_checks c WHERE c.document_id = d.id)""")]
        steps["sec_rehydrated"] = sec_edgar.rehydrate(conn, need)
    except Exception as exc:
        steps["sec_error"] = str(exc)
    for name in ("opendart", "edinet"):
        try:
            mod = __import__(f"ripple.collectors.{name}", fromlist=["collect"])
            steps[name] = mod.collect(conn, log=lambda *_: None)
        except Exception as exc:
            steps[f"{name}_error"] = str(exc)
    try:
        steps["gdelt"] = gdelt.collect(conn)
    except Exception as exc:
        steps["gdelt_error"] = str(exc)
    sections.cut_all(conn)
    steps["queue"] = queue.prepare(conn)
    state.save(conn)
    export_site.export(conn, include_sample=_site_wants_sample(conn))
    print(json.dumps(steps, indent=1, default=str))
    if any(k.endswith("_error") for k in steps) and args.strict:
        sys.exit(1)


def cmd_review(args) -> None:
    from . import review_server
    review_server.serve(port=args.port, open_browser=not args.no_browser)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m ripple", description="Ripple supply chain tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the database and load the seed list").set_defaults(func=cmd_init)
    sub.add_parser("status", help="show how many rows are in each table").set_defaults(func=cmd_status)
    sub.add_parser("sec-verify", help="check seed SEC company numbers against SEC's ticker list").set_defaults(func=cmd_sec_verify)

    s = sub.add_parser("sec-collect", help="download SEC filings (10-K/20-F, 10-Q, 8-K)")
    s.add_argument("--companies", help="comma-separated node ids, e.g. micron,amkor (default: all SEC filers)")
    s.add_argument("--quarters", type=int, default=4, help="how many recent 10-Qs to fetch")
    s.add_argument("--no-8k", action="store_true", help="skip 8-K filings")
    s.add_argument("--max-8k", type=int, default=8, help="most 8-Ks to fetch per company")
    s.set_defaults(func=cmd_sec_collect)

    s = sub.add_parser("cut-sections", help="cut Item 1, Item 1A and customer notes out of stored filings")
    s.add_argument("--redo", action="store_true")
    s.set_defaults(func=cmd_cut_sections)

    s = sub.add_parser("load-sample", help="load the hand-made SAMPLE links (for testing only)")
    s.add_argument("--remove", action="store_true", help="remove all SAMPLE links and events instead")
    s.set_defaults(func=cmd_load_sample)

    s = sub.add_parser("trace", help="trace a ripple from one or more nodes")
    s.add_argument("nodes", help="comma-separated node ids, e.g. ras_laffan,helium")
    s.add_argument("--steps", type=int, default=4)
    s.add_argument("--before", help="only use links first seen before this date (YYYY-MM-DD)")
    s.add_argument("--top", type=int, default=25)
    s.set_defaults(func=cmd_trace)

    s = sub.add_parser("export-site", help="write site/data/data.js from the database")
    s.add_argument("--real-only", action="store_true", help="leave out SAMPLE links and events")
    s.set_defaults(func=cmd_export_site)

    s = sub.add_parser("ai", help="PAID API route (off by default; the free route is ai-prepare / ai-import)")
    s.add_argument("job", choices=["extract-links", "check-events", "explain-ripple", "extract-links-batch", "collect-batch"])
    s.add_argument("--batch-id", help="batch id for collect-batch")
    s.add_argument("--dry-run", action="store_true", help="build the prompts but do not call Claude")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--event", help="event id for explain-ripple")
    s.set_defaults(func=cmd_ai)

    s = sub.add_parser("collect-foreign", help="Korean (OpenDART) or Japanese (EDINET) filings")
    s.add_argument("system", choices=["opendart", "edinet"])
    s.set_defaults(func=cmd_collect_foreign)

    sub.add_parser("state-save", help="save the map's state to data/state/ (for git)").set_defaults(func=cmd_state_save)
    sub.add_parser("state-load", help="rebuild the database from data/state/").set_defaults(func=cmd_state_load)

    s = sub.add_parser("ai-prepare", help="build today's small AI work queue (ai_work/queue.json)")
    s.add_argument("--max-sections", type=int, default=15)
    s.add_argument("--max-chars", type=int, default=70_000)
    s.add_argument("--no-save", action="store_true")
    s.set_defaults(func=cmd_ai_prepare)
    sub.add_parser("ai-status", help="is there AI work to do? (exit code 3 = no, stop)").set_defaults(func=cmd_ai_status)
    sub.add_parser("ai-import", help="check and import ai_work/results.json").set_defaults(func=cmd_ai_import)
    sub.add_parser("ai-backup", help="OPTIONAL: answer the queue with a free model (off by default)").set_defaults(func=cmd_ai_backup)

    s = sub.add_parser("daily-collect", help="collectors + news + work queue + site data (run by GitHub Actions)")
    s.add_argument("--quarters", type=int, default=4)
    s.add_argument("--strict", action="store_true", help="exit with an error if any collector failed")
    s.set_defaults(func=cmd_daily_collect)

    s = sub.add_parser("review", help="open the review queue page in your browser")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(func=cmd_review)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
