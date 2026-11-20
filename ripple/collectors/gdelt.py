"""GDELT news collector (free, no key): recent English news that mentions anything on the map.

Uses the GDELT DOC 2.0 API (https://api.gdeltproject.org/api/v2/doc/doc), which asks
for at most one request every 5 seconds. So all map names are grouped into a few
combined searches ("SK hynix" OR "Micron" OR ...), spaced 6 seconds apart.

Each article is stored once (by URL) as a `news` document whose text is its
headline plus source and date. Articles about the same thing within 48 hours are
grouped: only the first headline per (node, near-identical title) is kept, so ten
outlets reporting one story don't look like ten events. Code then pre-filters
again when building the AI queue (must mention a node AND supply wording).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import time

import requests

from .. import db

API = "https://api.gdeltproject.org/api/v2/doc/doc"
WAIT_SECONDS = 10
TERMS_PER_QUERY = 12
MAX_RECORDS = 75

# Search terms. Ambiguous short names are made specific ("Meta Platforms", not "Meta").
EXTRA_TERMS = {
    "meta": "Meta Platforms", "amazon": "Amazon Web Services", "oracle": "Oracle data center", "disco": "Disco Corporation",
    "eaton": "Eaton Corporation", "linde": "Linde plc", "hubbell": "Hubbell", "quanta": "Quanta Services",
    "alphabet": "Google data center", "microsoft": "Microsoft data center", "amd": "Advanced Micro Devices",
    "ase": "ASE Technology", "hitachi": "Hitachi Energy", "samsung": "Samsung Electronics", "freeport": "Freeport-McMoRan",
    "air_products": "Air Products", "ajinomoto": "Ajinomoto Build-up Film", "schneider": "Schneider Electric",
    "helium": "helium shortage", "hbm": "high-bandwidth memory", "abf_film": "ABF substrate", "transformers": "transformer shortage",
    "copper": "copper supply", "bromine": "bromine", "lng": "LNG supply", "cowos": "CoWoS", "ras_laffan": "Ras Laffan",
}
SKIP_NODES = {"korea", "taiwan", "japan", "qatar"}  # countries alone are far too broad


def search_terms(conn: sqlite3.Connection) -> list[str]:
    terms = []
    for r in conn.execute("SELECT id, name, kind FROM nodes ORDER BY id"):
        if r["id"] in SKIP_NODES:
            continue
        terms.append(EXTRA_TERMS.get(r["id"], r["name"]))
    return sorted(set(terms))


def _query(terms: list[str]) -> str:
    quoted = " OR ".join(f'"{t}"' if " " in t or "-" in t else t for t in terms)
    return f"({quoted}) sourcelang:english"


def fetch(query: str, timespan: str = "1d", session: requests.Session | None = None, retries: int = 4) -> list[dict]:
    s = session or requests.Session()
    for attempt in range(retries):
        try:
            r = s.get(API, params={"query": query, "mode": "artlist", "format": "json", "maxrecords": MAX_RECORDS,
                                   "sort": "datedesc", "timespan": timespan}, timeout=60,
                      headers={"User-Agent": "Ripple research tool"})
        except requests.RequestException:
            time.sleep(WAIT_SECONDS * (attempt + 2))
            continue
        if r.status_code == 429 or "limit requests" in r.text[:200]:
            time.sleep(WAIT_SECONDS * (attempt + 2))
            continue
        r.raise_for_status()
        try:
            return r.json().get("articles", [])
        except ValueError:
            return []  # GDELT returns plain text for some errors (e.g. a query that is too short)
    raise RuntimeError("GDELT kept asking us to slow down (HTTP 429)")


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower())[:80]


def _date(seendate: str) -> str:
    # GDELT format: 20261120T031500Z
    return f"{seendate[:4]}-{seendate[4:6]}-{seendate[6:8]}" if seendate else dt.date.today().isoformat()


def collect(conn: sqlite3.Connection, timespan: str = "1d", log=print, sleep=time.sleep) -> dict:
    terms = search_terms(conn)
    groups = [terms[i:i + TERMS_PER_QUERY] for i in range(0, len(terms), TERMS_PER_QUERY)]
    since = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    recent_titles = {_norm_title(r["text"].split("\n", 1)[0]) for r in conn.execute(
        "SELECT text FROM documents WHERE source='gdelt' AND published_at >= ?", (since,))}
    summary = {"queries": 0, "articles_seen": 0, "new_documents": 0, "duplicates": 0, "errors": []}
    s = requests.Session()
    for i, group in enumerate(groups):
        if i:
            sleep(WAIT_SECONDS)
        try:
            arts = fetch(_query(group), timespan, s)
        except Exception as exc:
            summary["errors"].append(str(exc))
            continue
        summary["queries"] += 1
        for a in arts:
            summary["articles_seen"] += 1
            url, title = a.get("url"), (a.get("title") or "").strip()
            if not url or not title:
                continue
            nt = _norm_title(title)
            if nt in recent_titles or conn.execute(
                    "SELECT 1 FROM documents WHERE source='gdelt' AND external_id=?", (url,)).fetchone():
                summary["duplicates"] += 1
                continue
            recent_titles.add(nt)
            doc_id = db.next_id(conn, "documents", "doc")
            text = f"{title}\nSource: {a.get('domain', '')} ({a.get('sourcecountry', '')}), {a.get('language', '')}"
            conn.execute("""INSERT INTO documents (id, source, url, doc_type, company_id, published_at, collected_at, text, processed, external_id)
                            VALUES (?, 'gdelt', ?, 'news', NULL, ?, ?, ?, 1, ?)""",
                         (doc_id, url, _date(a.get("seendate", "")),
                          dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), text, url))
            summary["new_documents"] += 1
        conn.commit()
    return summary


def describe() -> str:
    return json.dumps({"api": API, "wait_seconds": WAIT_SECONDS, "terms_per_query": TERMS_PER_QUERY})
