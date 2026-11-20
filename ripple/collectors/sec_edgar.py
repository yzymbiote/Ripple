"""SEC EDGAR collector.

For each of the SEC filers on the map, download:
- the latest annual report (10-K, or 20-F / 40-F for foreign companies),
- the last N quarterly reports (10-Q; foreign filers file 6-K instead),
- recent 8-Ks (or 6-Ks) from the last 12 months.

Rules followed:
- The User-Agent (with a contact email) comes from the SEC_USER_AGENT
  environment variable. It is never written in the code.
- At most 8 requests per second (SEC's limit is 10).
- Nothing is overwritten: a filing already stored (same accession number) is skipped.
- The raw HTML is also kept (gzipped) in data/raw/sec_edgar/ so every claim
  can be traced back to exactly what was downloaded.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import sqlite3

from .. import config, db
from ..text import html_to_text
from .http import PoliteSession

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

ANNUAL_FORMS = ("10-K", "20-F", "40-F")
QUARTERLY_FORMS = ("10-Q",)
CURRENT_FORMS = ("8-K", "6-K")

_session: PoliteSession | None = None


class MissingUserAgent(RuntimeError):
    pass


def session() -> PoliteSession:
    global _session
    if _session is None:
        ua = config.SEC_USER_AGENT
        if not ua or "@" not in ua:
            raise MissingUserAgent(
                "SEC_USER_AGENT is not set (it must include a contact email). "
                "Add it to your environment or .env file, e.g. SEC_USER_AGENT=\"Ripple research you@example.com\"")
        _session = PoliteSession({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
                                 per_second=config.SEC_MAX_REQUESTS_PER_SECOND)
    return _session


def sec_companies(conn: sqlite3.Connection, only: list[str] | None = None) -> list[sqlite3.Row]:
    rows = conn.execute("SELECT * FROM nodes WHERE kind='company' ORDER BY id").fetchall()
    out = [r for r in rows if db.node_extra(r).get("filer") == "sec"]
    if only:
        out = [r for r in out if r["id"] in only]
    return out


def verify_ciks(conn: sqlite3.Connection) -> list[str]:
    """Compare each seed company's SEC number with SEC's own ticker list."""
    data = session().get(TICKERS_URL).json()
    by_ticker = {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}
    problems = []
    for row in sec_companies(conn):
        cik = db.node_extra(row).get("sec_cik")
        sec_cik = by_ticker.get((row["ticker"] or "").upper())
        if sec_cik is None:
            problems.append(f"{row['id']}: ticker {row['ticker']} not in SEC list (seed CIK {cik})")
        elif sec_cik != cik:
            problems.append(f"{row['id']}: seed CIK {cik} but SEC says {sec_cik}")
    return problems


def _recent_filings(sub: dict) -> list[dict]:
    r = sub["filings"]["recent"]
    keys = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument", "primaryDocDescription")
    return [dict(zip(keys, vals)) for vals in zip(*(r[k] for k in keys))]


def pick_filings(filings: list[dict], quarters: int = 4, include_8k: bool = True, max_8k: int = 8,
                 today: dt.date | None = None) -> list[dict]:
    """Choose which filings to download from a company's filing list (newest first)."""
    today = today or dt.date.today()
    cutoff = (today - dt.timedelta(days=365)).isoformat()
    chosen: list[dict] = []
    annual = next((f for f in filings if f["form"] in ANNUAL_FORMS), None)
    if annual:
        chosen.append(annual)
    chosen += [f for f in filings if f["form"] in QUARTERLY_FORMS][:quarters]
    if include_8k:
        chosen += [f for f in filings if f["form"] in CURRENT_FORMS and f["filingDate"] >= cutoff][:max_8k]
    return chosen


def _store(conn: sqlite3.Connection, company: sqlite3.Row, cik: int, f: dict) -> str | None:
    acc = f["accessionNumber"]
    exists = conn.execute("SELECT id FROM documents WHERE source='sec_edgar' AND external_id=?", (acc,)).fetchone()
    if exists:
        return None
    if not f.get("primaryDocument"):
        return None
    url = ARCHIVE_URL.format(cik=cik, acc=acc.replace("-", ""), doc=f["primaryDocument"])
    resp = session().get(url)
    raw = resp.content
    raw_path = config.RAW_DIR / "sec_edgar" / company["id"] / f"{acc}__{f['primaryDocument']}.gz"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(gzip.compress(raw))
    if f["primaryDocument"].lower().endswith((".htm", ".html", ".xml")):
        text = html_to_text(raw)
    else:
        text = raw.decode("utf-8", errors="replace")
    doc_id = db.next_id(conn, "documents", "doc")
    conn.execute(
        """INSERT INTO documents (id, source, url, doc_type, company_id, published_at, collected_at, text, processed, external_id)
           VALUES (?,?,?,?,?,?,?,?,0,?)""",
        (doc_id, "sec_edgar", url, f["form"], company["id"], f["filingDate"],
         dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), text, acc))
    conn.commit()
    return doc_id


def collect(conn: sqlite3.Connection, companies: list[str] | None = None, quarters: int = 4,
            include_8k: bool = True, max_8k: int = 8, log=print) -> dict:
    """Download new filings for the SEC filers. Returns a small summary."""
    summary = {"companies": 0, "new_documents": 0, "skipped_existing": 0, "errors": []}
    for company in sec_companies(conn, companies):
        cik = db.node_extra(company).get("sec_cik")
        try:
            sub = session().get(SUBMISSIONS_URL.format(cik=cik)).json()
        except Exception as exc:  # keep going with the next company
            summary["errors"].append(f"{company['id']}: {exc}")
            log(f"! {company['id']}: could not read filing list ({exc})")
            continue
        summary["companies"] += 1
        picked = pick_filings(_recent_filings(sub), quarters, include_8k, max_8k)
        for f in picked:
            try:
                doc_id = _store(conn, company, cik, f)
            except Exception as exc:
                summary["errors"].append(f"{company['id']} {f['accessionNumber']}: {exc}")
                log(f"! {company['id']} {f['form']} {f['filingDate']}: {exc}")
                continue
            if doc_id:
                summary["new_documents"] += 1
                log(f"+ {company['id']:18s} {f['form']:5s} {f['filingDate']}  -> {doc_id}")
            else:
                summary["skipped_existing"] += 1
    log(json.dumps(summary, indent=2))
    return summary
