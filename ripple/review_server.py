"""Private review queue: approve, reject or edit links in your browser.

    python -m ripple review

starts a small web server on your own computer (http://localhost:8765, not
reachable from the internet) and opens the review page. Every decision is saved
to the database, to data/state/ (so it survives and can be committed), and the
public site's data file is refreshed.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import config, db, export_site, state

REVIEW_DIR = config.ROOT / "review"
SITE_DIR = config.ROOT / "site"
TYPES = ("supplies", "makes_in", "uses", "produces")
CONFIDENCE = ("high", "medium", "low")


def review_data(conn) -> dict:
    nodes = {r["id"]: {"id": r["id"], "name": r["name"], "kind": r["kind"], "ticker": r["ticker"], "layer": r["layer"]}
             for r in conn.execute("SELECT * FROM nodes ORDER BY name")}
    links = []
    for r in conn.execute("SELECT * FROM links WHERE is_sample=0 ORDER BY CASE status WHEN 'pending_review' THEN 0 "
                          "WHEN 'approved' THEN 1 ELSE 2 END, id"):
        sources = [dict(s) for s in conn.execute(
            """SELECT s.quote, s.quote_verified, d.url, d.doc_type, d.published_at, d.company_id
               FROM link_sources s JOIN documents d ON d.id = s.document_id WHERE s.link_id=?""", (r["id"],))]
        links.append({**dict(r), "sources": sources})
    candidates = [dict(r) for r in conn.execute(
        """SELECT c.*, d.url, d.doc_type, d.published_at FROM link_candidates c JOIN documents d ON d.id = c.document_id
           WHERE c.status='needs_review' ORDER BY c.id""")]
    return {"nodes": nodes, "links": links, "candidates": candidates}


def _save(conn) -> None:
    conn.commit()
    state.save(conn)
    has_real_events = conn.execute("SELECT COUNT(*) FROM events WHERE is_sample=0").fetchone()[0] > 0
    export_site.export(conn, include_sample=not has_real_events)


def act_on_link(conn, link_id: str, body: dict) -> dict:
    row = conn.execute("SELECT * FROM links WHERE id=?", (link_id,)).fetchone()
    if not row:
        return {"error": "no such link"}
    action = body.get("action")
    if action == "edit":
        f = body.get("fields", {})
        if f.get("type") not in TYPES or f.get("confidence") not in CONFIDENCE:
            return {"error": "bad type or confidence"}
        for n in (f.get("from_node"), f.get("to_node")):
            if not conn.execute("SELECT 1 FROM nodes WHERE id=?", (n,)).fetchone():
                return {"error": f"unknown node {n}"}
        share = f.get("share")
        share = None if share in ("", None) else float(share)
        conn.execute("UPDATE links SET from_node=?, to_node=?, type=?, what=?, share=?, confidence=? WHERE id=?",
                     (f["from_node"], f["to_node"], f["type"], f.get("what") or None, share, f["confidence"], link_id))
    elif action in ("approve", "reject", "pending"):
        status = {"approve": "approved", "reject": "rejected", "pending": "pending_review"}[action]
        try:
            conn.execute("UPDATE links SET status=? WHERE id=?", (status, link_id))
        except Exception as exc:  # the database refuses approval without a verified source
            return {"error": str(exc)}
    else:
        return {"error": "unknown action"}
    _save(conn)
    return {"ok": True}


def act_on_candidate(conn, cand_id: int, body: dict) -> dict:
    c = conn.execute("SELECT * FROM link_candidates WHERE id=?", (cand_id,)).fetchone()
    if not c:
        return {"error": "no such candidate"}
    action = body.get("action")
    if action == "reject":
        conn.execute("UPDATE link_candidates SET status='rejected', reason=COALESCE(reason,'') || ' | rejected in review' WHERE id=?", (cand_id,))
    elif action == "placeholder":
        # An unnamed customer/supplier with a disclosed share ("one customer = 22% of revenue"):
        # shown on the company's page as an unnamed placeholder, as the build plan asks.
        if c["other_party"] or c["share"] is None or not c["quote_verified"]:
            return {"error": "only unnamed parties with a disclosed share and a verified quote can be shown as placeholders"}
        conn.execute("UPDATE link_candidates SET status='placeholder' WHERE id=?", (cand_id,))
    elif action == "link":
        other = body.get("other_node")
        if not conn.execute("SELECT 1 FROM nodes WHERE id=?", (other,)).fetchone():
            return {"error": "pick a node on the map"}
        if not c["quote_verified"]:
            return {"error": "this quote was not verified; it can't become a link"}
        if body.get("add_alias") and c["other_party"]:
            state.add_alias(conn, other, c["other_party"])
        from .ai.jobs import _merge_link
        a, b = (other, c["filer_node"]) if c["direction"] == "other_to_filer" and c["type"] == "supplies" else (c["filer_node"], other)
        doc = conn.execute("SELECT published_at FROM documents WHERE id=?", (c["document_id"],)).fetchone()
        link_id = _merge_link(conn, a, b, {"type": c["type"], "what": c["what"], "share": c["share"], "quote": c["quote"]},
                              {"document_id": c["document_id"], "published_at": doc["published_at"] if doc else None})
        conn.execute("UPDATE link_candidates SET status='linked', matched_node=?, link_id=? WHERE id=?", (other, link_id, cand_id))
    else:
        return {"error": "unknown action"}
    _save(conn)
    return {"ok": True}


class Handler(BaseHTTPRequestHandler):
    conn = None
    lock = threading.Lock()

    def log_message(self, *args):  # keep the terminal quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/review":
            with self.lock:
                return self._json(review_data(self.conn))
        if path in ("/", "/index.html"):
            return self._file(REVIEW_DIR / "index.html")
        if path.startswith("/review/"):
            return self._file(REVIEW_DIR / path[len("/review/"):])
        if path.startswith("/assets/"):
            return self._file(SITE_DIR / path.lstrip("/"))
        self._send(404, b"not found", "text/plain")

    def _file(self, p: Path):
        p = p.resolve()
        if not (str(p).startswith(str(REVIEW_DIR.resolve())) or str(p).startswith(str(SITE_DIR.resolve()))) or not p.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = {".html": "text/html", ".css": "text/css", ".js": "application/javascript"}.get(p.suffix, "application/octet-stream")
        self._send(200, p.read_bytes(), ctype + "; charset=utf-8")

    def do_POST(self):
        # Only accept requests from this page (simple guard against other websites posting to localhost).
        origin = self.headers.get("Origin", "")
        if origin and not origin.startswith(("http://localhost", "http://127.0.0.1")):
            return self._json({"error": "forbidden"}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        parts = self.path.strip("/").split("/")
        with self.lock:
            if len(parts) == 3 and parts[:2] == ["api", "link"]:
                return self._json(act_on_link(self.conn, parts[2], body))
            if len(parts) == 3 and parts[:2] == ["api", "candidate"]:
                return self._json(act_on_candidate(self.conn, int(parts[2]), body))
        self._json({"error": "not found"}, 404)


def serve(port: int = 8765, open_browser: bool = True) -> None:
    Handler.conn = state.ensure_db()
    Handler.conn.execute("PRAGMA foreign_keys = ON")
    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    print(f"Review queue running at {url}  (press Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Your decisions are saved in data/state/ - commit and push them so the daily run sees them.")
