"""OpenDART collector (Korea): SK hynix, Samsung Electronics, Hanmi Semiconductor, HD Hyundai Electric.

Switched OFF until you add a free key from https://opendart.fss.or.kr
(OPENDART_API_KEY in .env) and set RIPPLE_OPENDART_ENABLED=1.

What it downloads for each Korean company on the map:
- periodic reports (pblntf_ty=A): annual 사업보고서, half-year 반기보고서, quarterly 분기보고서
- major supply-contract disclosures (단일판매ㆍ공급계약체결) from exchange filings (pblntf_ty=I)

API used (all official, documented at https://opendart.fss.or.kr/guide/main.do):
- corpCode.xml  : zip listing every company's 8-digit corp_code and its stock code
- list.json     : filings for one company in a date range
- document.xml  : zip with the original filing (XML/HTML)
Filings stay in Korean; the link extractor reads the original text and the quote
check runs against it, as the build plan asks.
"""
from __future__ import annotations

import datetime as dt
import gzip
import io
import sqlite3
import zipfile

from bs4 import BeautifulSoup

from .. import config, db
from ..text import html_to_text
from .http import PoliteSession

BASE = "https://opendart.fss.or.kr/api"
DOC_VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
PER_SECOND = 5
LOOKBACK_DAYS = 400

ANNUAL = "사업보고서"
HALF = "반기보고서"
QUARTER = "분기보고서"
SUPPLY_CONTRACT = "공급계약"


def enabled() -> tuple[bool, str]:
    if not config.OPENDART_API_KEY:
        return False, "OPENDART_API_KEY is not set (free key: https://opendart.fss.or.kr)."
    if not config.OPENDART_ENABLED:
        return False, "OpenDART collector is switched off. Set RIPPLE_OPENDART_ENABLED=1 in .env."
    return True, "ok"


def _session() -> PoliteSession:
    return PoliteSession({"User-Agent": "Ripple research tool"}, per_second=PER_SECOND)


def doc_type_for(report_nm: str) -> str | None:
    if ANNUAL in report_nm:
        return "annual_report_kr"
    if HALF in report_nm:
        return "half_year_report_kr"
    if QUARTER in report_nm:
        return "quarterly_report_kr"
    if SUPPLY_CONTRACT in report_nm:
        return "supply_contract_kr"
    return None


def corp_codes(sess: PoliteSession) -> dict[str, str]:
    """stock code (e.g. '000660') -> DART corp_code (8 digits)."""
    resp = sess.get(f"{BASE}/corpCode.xml", params={"crtfc_key": config.OPENDART_API_KEY})
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        xml = z.read(z.namelist()[0])
    soup = BeautifulSoup(xml, "lxml-xml")
    out = {}
    for item in soup.find_all("list"):
        stock = (item.find("stock_code").text or "").strip()
        if stock:
            out[stock] = item.find("corp_code").text.strip()
    return out


def list_filings(sess: PoliteSession, corp_code: str, kind: str, start: dt.date, end: dt.date) -> list[dict]:
    out, page = [], 1
    while True:
        data = sess.get(f"{BASE}/list.json", params={
            "crtfc_key": config.OPENDART_API_KEY, "corp_code": corp_code, "pblntf_ty": kind,
            "bgn_de": start.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
            "page_no": page, "page_count": 100}).json()
        if data.get("status") == "013":  # no filings in range
            return out
        if data.get("status") != "000":
            raise RuntimeError(f"OpenDART error {data.get('status')}: {data.get('message')}")
        out += data.get("list", [])
        if page >= int(data.get("total_page", 1)):
            return out
        page += 1


def document_text(sess: PoliteSession, rcept_no: str) -> tuple[str, bytes]:
    resp = sess.get(f"{BASE}/document.xml", params={"crtfc_key": config.OPENDART_API_KEY, "rcept_no": rcept_no})
    raw = resp.content
    parts = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in sorted(z.namelist()):
            if name.lower().endswith((".xml", ".htm", ".html")):
                parts.append(html_to_text(z.read(name)))
    return "\n".join(parts), raw


def pick(filings: list[dict]) -> list[dict]:
    """Latest annual report, last 4 half/quarterly reports, supply contracts from the last year."""
    filings = sorted(filings, key=lambda f: f["rcept_dt"], reverse=True)
    annual = [f for f in filings if doc_type_for(f["report_nm"]) == "annual_report_kr"][:1]
    periodic = [f for f in filings if doc_type_for(f["report_nm"]) in ("half_year_report_kr", "quarterly_report_kr")][:4]
    contracts = [f for f in filings if doc_type_for(f["report_nm"]) == "supply_contract_kr"][:10]
    return annual + periodic + contracts


def collect(conn: sqlite3.Connection, log=print) -> dict:
    ok, why = enabled()
    if not ok:
        return {"switched_off": why}
    sess = _session()
    codes = corp_codes(sess)
    end = dt.date.today()
    start = end - dt.timedelta(days=LOOKBACK_DAYS)
    summary = {"new_documents": 0, "errors": []}
    companies = [r for r in conn.execute("SELECT * FROM nodes WHERE kind='company'") if db.node_extra(r).get("filer") == "opendart"]
    for company in companies:
        stock = db.node_extra(company).get("dart_stock_code")
        corp = codes.get(stock)
        if not corp:
            summary["errors"].append(f"{company['id']}: stock code {stock} not found in DART list")
            continue
        try:
            filings = list_filings(sess, corp, "A", start, end) + [
                f for f in list_filings(sess, corp, "I", end - dt.timedelta(days=365), end) if SUPPLY_CONTRACT in f["report_nm"]]
        except Exception as exc:
            summary["errors"].append(f"{company['id']}: {exc}")
            continue
        for f in pick(filings):
            if conn.execute("SELECT 1 FROM documents WHERE source='opendart' AND external_id=?", (f["rcept_no"],)).fetchone():
                continue
            try:
                text, raw = document_text(sess, f["rcept_no"])
            except Exception as exc:
                summary["errors"].append(f"{company['id']} {f['rcept_no']}: {exc}")
                continue
            raw_path = config.RAW_DIR / "opendart" / company["id"] / f"{f['rcept_no']}.zip.gz"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(gzip.compress(raw))
            doc_id = db.next_id(conn, "documents", "doc")
            d = f["rcept_dt"]
            conn.execute("""INSERT INTO documents (id, source, url, doc_type, company_id, published_at, collected_at, text, processed, external_id)
                            VALUES (?, 'opendart', ?, ?, ?, ?, ?, ?, 0, ?)""",
                         (doc_id, DOC_VIEW.format(rcept_no=f["rcept_no"]), doc_type_for(f["report_nm"]), company["id"],
                          f"{d[:4]}-{d[4:6]}-{d[6:]}", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                          text, f["rcept_no"]))
            conn.commit()
            summary["new_documents"] += 1
            log(f"+ {company['id']:20s} {f['report_nm'][:30]} {d} -> {doc_id}")
    return summary
