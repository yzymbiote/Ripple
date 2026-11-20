"""EDINET collector (Japan): Ibiden, Ajinomoto, Disco, Advantest, Hitachi.

Switched OFF until you add a free key from https://api.edinet-fsa.go.jp
(EDINET_API_KEY in .env) and set RIPPLE_EDINET_ENABLED=1.

EDINET lists filings by day, so the collector walks the days since its last run
(the first run looks back 400 days to find the latest annual report), keeps the
filings from our companies, and downloads:
- annual securities reports  有価証券報告書  (docTypeCode 120)
- half-year reports          半期報告書      (160)  — Japan replaced quarterly reports with these in 2024
- quarterly reports          四半期報告書    (140)  — older filings
- extraordinary reports      臨時報告書      (180)

API (official, v2):
- GET /api/v2/documents.json?date=YYYY-MM-DD&type=2   list of that day's filings
- GET /api/v2/documents/{docID}?type=1                 zip with the filing (HTML in PublicDoc/)
The text stays in Japanese; quotes are checked against the original.
"""
from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import sqlite3
import zipfile

from .. import config, db
from ..text import html_to_text
from .http import PoliteSession

BASE = "https://api.edinet-fsa.go.jp/api/v2"
VIEW = "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?{doc_id}"
PER_SECOND = 3
FIRST_LOOKBACK_DAYS = 400
STATE_FILE = config.RAW_DIR / "edinet" / "state.json"

DOC_TYPES = {"120": "annual_report_jp", "160": "half_year_report_jp", "140": "quarterly_report_jp",
             "180": "extraordinary_report_jp"}


def enabled() -> tuple[bool, str]:
    if not config.EDINET_API_KEY:
        return False, "EDINET_API_KEY is not set (free key: https://api.edinet-fsa.go.jp)."
    if not config.EDINET_ENABLED:
        return False, "EDINET collector is switched off. Set RIPPLE_EDINET_ENABLED=1 in .env."
    return True, "ok"


def _session() -> PoliteSession:
    return PoliteSession({"User-Agent": "Ripple research tool"}, per_second=PER_SECOND)


def day_list(sess: PoliteSession, day: dt.date) -> list[dict]:
    data = sess.get(f"{BASE}/documents.json", params={"date": day.isoformat(), "type": 2,
                                                       "Subscription-Key": config.EDINET_API_KEY}).json()
    status = str(data.get("metadata", {}).get("status", data.get("statusCode", "200")))
    if status != "200":
        raise RuntimeError(f"EDINET error {status}: {data.get('metadata', {}).get('message') or data.get('message')}")
    return data.get("results") or []


def document_text(sess: PoliteSession, doc_id: str) -> tuple[str, bytes]:
    resp = sess.get(f"{BASE}/documents/{doc_id}", params={"type": 1, "Subscription-Key": config.EDINET_API_KEY})
    raw = resp.content
    parts = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in sorted(z.namelist()):
            if "PublicDoc" in name and name.lower().endswith((".htm", ".html")):
                parts.append(html_to_text(z.read(name)))
    return "\n".join(parts), raw


def wanted(results: list[dict], sec_codes: dict[str, str]) -> list[tuple[str, dict]]:
    """(company_id, filing) for filings by our companies of the kinds we keep."""
    out = []
    for r in results:
        cid = sec_codes.get((r.get("secCode") or "").strip())
        if cid and r.get("docTypeCode") in DOC_TYPES and r.get("withdrawalStatus", "0") == "0":
            out.append((cid, r))
    return out


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def collect(conn: sqlite3.Connection, log=print, today: dt.date | None = None) -> dict:
    ok, why = enabled()
    if not ok:
        return {"switched_off": why}
    sess = _session()
    today = today or dt.date.today()
    state = _load_state()
    last = state.get("last_day")
    start = dt.date.fromisoformat(last) + dt.timedelta(days=1) if last else today - dt.timedelta(days=FIRST_LOOKBACK_DAYS)
    sec_codes = {db.node_extra(r).get("edinet_sec_code"): r["id"] for r in conn.execute("SELECT * FROM nodes WHERE kind='company'")
                 if db.node_extra(r).get("filer") == "edinet"}
    summary = {"days_scanned": 0, "new_documents": 0, "errors": []}
    day = start
    while day <= today:
        try:
            results = day_list(sess, day)
        except Exception as exc:
            summary["errors"].append(f"{day}: {exc}")
            break  # stop here; the next run resumes from this day
        for cid, r in wanted(results, sec_codes):
            if conn.execute("SELECT 1 FROM documents WHERE source='edinet' AND external_id=?", (r["docID"],)).fetchone():
                continue
            try:
                text, raw = document_text(sess, r["docID"])
            except Exception as exc:
                summary["errors"].append(f"{cid} {r['docID']}: {exc}")
                continue
            raw_path = config.RAW_DIR / "edinet" / cid / f"{r['docID']}.zip.gz"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(gzip.compress(raw))
            doc_id = db.next_id(conn, "documents", "doc")
            conn.execute("""INSERT INTO documents (id, source, url, doc_type, company_id, published_at, collected_at, text, processed, external_id)
                            VALUES (?, 'edinet', ?, ?, ?, ?, ?, ?, 0, ?)""",
                         (doc_id, VIEW.format(doc_id=r["docID"]), DOC_TYPES[r["docTypeCode"]], cid,
                          (r.get("submitDateTime") or day.isoformat())[:10],
                          dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), text, r["docID"]))
            conn.commit()
            summary["new_documents"] += 1
            log(f"+ {cid:12s} {r.get('docDescription', '')[:30]} {day} -> {doc_id}")
        summary["days_scanned"] += 1
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({"last_day": day.isoformat()}))
        day += dt.timedelta(days=1)
    return summary
