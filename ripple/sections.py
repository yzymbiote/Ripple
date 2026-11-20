"""Section cutter.

The AI should not read whole filings (that wastes money). This cuts out only
the parts that talk about customers and suppliers:

- item_1   : Item 1 "Business" of a 10-K  (for a 20-F: Item 4 "Information on the Company")
- item_1a  : Item 1A "Risk Factors"        (for a 20-F: Item 3.D "Risk Factors"; for a 10-Q: Part II Item 1A)
- customer_concentration : every sentence anywhere in the filing that talks about
  customers/suppliers together with a share, "sole source", "depend", etc.
- full     : short documents (8-K, 6-K) are kept whole.

How headings are found: filings repeat "Item 1." in the table of contents and
again in the body. We find every heading, and for each section we keep the
candidate that produces the LONGEST section (the table-of-contents entry is
always tiny, so the real one wins).
"""
from __future__ import annotations

import re
import sqlite3

KEYWORDS = [
    "customer", "supplier", "sole source", "single source", "sole-source", "single-source",
    "% of revenue", "% of net revenue", "% of net sales", "% of total revenue", "depend",
    "manufactured by", "foundry", "foundries", "subcontract", "vendor", "concentration",
    # Korean
    "고객", "매출처", "공급", "거래처", "원재료", "의존",
    # Japanese
    "販売先", "仕入先", "顧客", "依存", "原材料", "調達",
]

# Korean / Japanese report headings: (section, start heading, end headings)
CJK_SECTIONS = {
    "annual_report_kr": [("item_1", r"II\.\s*사업의\s*내용", [r"III\.\s*재무에\s*관한\s*사항"])],
    "half_year_report_kr": [("item_1", r"II\.\s*사업의\s*내용", [r"III\.\s*재무에\s*관한\s*사항"])],
    "quarterly_report_kr": [("item_1", r"II\.\s*사업의\s*내용", [r"III\.\s*재무에\s*관한\s*사항"])],
    "annual_report_jp": [("item_1", r"事業の内容", [r"関係会社の状況", r"従業員の状況"]),
                         ("item_1a", r"事業等のリスク", [r"経営者による", r"研究開発活動"])],
    "half_year_report_jp": [("item_1a", r"事業等のリスク", [r"経営者による", r"経営上の重要な契約"])],
}
_CJK_RELATION = re.compile(r"고객|매출처|공급|거래처|販売先|仕入先|顧客|供給|調達")
_CJK_SHARE = re.compile(r"\d+(?:\.\d+)?\s*[%％]|비중|의존|割合|依存|主要")

_HEADING = re.compile(r"(?im)^[ \t]*(?:part\s+i+\s*[,.\-–—]?\s*)?item[ \t ]*(\d{1,2}[a-d]?)\b[ \t]*[.:\-–—]?")
_RISK_20F = re.compile(r"(?im)^[ \t]*(?:item\s*)?(?:3\.)?\s*D\.?[ \t]*risk[ \t]+factors\b|^[ \t]*risk[ \t]+factors[ \t]*$")

SHORT_DOC_LIMIT = 60_000  # characters; shorter documents are kept whole

_RELATION = re.compile(r"customer|supplier|vendor|sole[- ]source|single[- ]source|foundr|subcontract|"
                       r"manufactured (?:for us )?by|contract manufactur|distributor|hyperscaler", re.I)
_SHARE = re.compile(r"\d+(?:\.\d+)?\s*%|percent|accounted for|\bsole\b|single[- ]source|limited number of|"
                    r"substantially all|depend|concentrat|largest", re.I)


def _headings(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1).lower()) for m in _HEADING.finditer(text)]


def _longest(text: str, heads: list[tuple[int, str]], start_label: str, end_labels: set[str],
             start_positions: list[int] | None = None) -> str:
    starts = start_positions if start_positions is not None else [p for p, lab in heads if lab == start_label]
    best = ""
    for s in starts:
        end = next((p for p, lab in heads if p > s and lab in end_labels), None)
        if end is None:
            continue
        chunk = text[s:end]
        if len(chunk) > len(best):
            best = chunk
    return best.strip()


def keyword_hits(text: str) -> int:
    low = text.lower()
    return sum(low.count(k) for k in KEYWORDS)


def concentration_sentences(text: str, max_sentences: int = 80) -> str:
    """Sentences that mention a customer/supplier relationship together with a share or dependency."""
    flat = re.sub(r"\s+", " ", text)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“(])", flat)
    out, seen = [], set()
    for s in sentences:
        s = s.strip()
        if not (20 <= len(s) <= 1500):
            continue
        if _RELATION.search(s) and _SHARE.search(s):
            key = s.lower()
            if key not in seen:
                seen.add(key)
                out.append(s)
        if len(out) >= max_sentences:
            break
    return "\n".join(out)


def _cut_by_regex(text: str, start_pat: str, end_pats: list[str]) -> str:
    """Longest chunk from a start heading to the next end heading (skips tables of contents)."""
    best = ""
    ends = [m.start() for p in end_pats for m in re.finditer(p, text)]
    for m in re.finditer(start_pat, text):
        end = min((e for e in ends if e > m.start()), default=None)
        if end is not None and end - m.start() > len(best):
            best = text[m.start():end]
    return best.strip()


def cjk_concentration(text: str, max_sentences: int = 80) -> str:
    sentences = re.split(r"(?<=[。.!?])\s*", re.sub(r"\s+", " ", text))
    out = [s.strip() for s in sentences if 10 <= len(s.strip()) <= 600 and _CJK_RELATION.search(s) and _CJK_SHARE.search(s)]
    return "\n".join(dict.fromkeys(out[:max_sentences]))


def cut(text: str, doc_type: str) -> dict[str, str]:
    """Return {section_name: text} for one document."""
    if doc_type in CJK_SECTIONS or doc_type.endswith(("_kr", "_jp")):
        out = {name: _cut_by_regex(text, a, b) for name, a, b in CJK_SECTIONS.get(doc_type, [])}
        if len(text) <= SHORT_DOC_LIMIT and not doc_type.startswith("annual"):
            out["full"] = text
        out["customer_concentration"] = cjk_concentration(text)
        return {k: v for k, v in out.items() if v}
    heads = _headings(text)
    out: dict[str, str] = {}
    dt = doc_type.upper()
    if dt in ("10-K", "10-K/A"):
        out["item_1"] = _longest(text, heads, "1", {"1a", "1b", "1c", "2"})
        out["item_1a"] = _longest(text, heads, "1a", {"1b", "1c", "2", "3"})
    elif dt in ("20-F", "20-F/A", "40-F"):
        out["item_1"] = _longest(text, heads, "4", {"4a", "5"})
        risk_starts = [m.start() for m in _RISK_20F.finditer(text)]
        out["item_1a"] = _longest(text, heads, "", {"4", "4a"}, start_positions=risk_starts)
    elif dt in ("10-Q", "10-Q/A"):
        out["item_1a"] = _longest(text, heads, "1a", {"2", "3", "4", "5", "6"})
    if len(text) <= SHORT_DOC_LIMIT and dt not in ("10-K", "20-F", "40-F"):
        out["full"] = text
    out["customer_concentration"] = concentration_sentences(text)
    return {k: v for k, v in out.items() if v and len(v) > 200 or (k == "customer_concentration" and v)}


def cut_all(conn: sqlite3.Connection, redo: bool = False) -> int:
    if redo:
        conn.execute("DELETE FROM document_sections WHERE processed = 0")
        conn.execute("DELETE FROM document_sections WHERE document_id IN (SELECT id FROM documents WHERE source='sample')")
    docs = conn.execute(
        """SELECT id, doc_type, text FROM documents d
           WHERE text IS NOT NULL AND source != 'sample' AND NOT EXISTS (SELECT 1 FROM document_sections s WHERE s.document_id = d.id)"""
    ).fetchall()
    for d in docs:
        for name, body in cut(d["text"], d["doc_type"]).items():
            conn.execute(
                "INSERT OR IGNORE INTO document_sections (document_id, section, text, keyword_hits) VALUES (?,?,?,?)",
                (d["id"], name, body, keyword_hits(body)))
    # Sections rebuilt from data/state/ have no text: refill them from re-downloaded documents.
    empty = conn.execute(
        """SELECT s.id, s.section, d.text, d.doc_type FROM document_sections s JOIN documents d ON d.id = s.document_id
           WHERE s.text = '' AND d.text IS NOT NULL""").fetchall()
    for s in empty:
        body = cut(s["text"], s["doc_type"]).get(s["section"], "")
        conn.execute("UPDATE document_sections SET text=? WHERE id=?", (body, s["id"]))
    conn.commit()
    return len(docs)
