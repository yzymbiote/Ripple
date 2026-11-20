"""Text helpers shared by the collectors, section cutter and quote checker."""
from __future__ import annotations

import re
import unicodedata

import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

BLOCK_TAGS = ["p", "div", "tr", "li", "br", "table", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "ul", "ol", "center", "title"]


def html_to_text(html: str | bytes) -> str:
    """Turn a filing's HTML into readable plain text, one paragraph per line.

    Inline XBRL tags are kept inline so sentences aren't broken apart; the hidden
    XBRL header is dropped. Table cells are joined with ' | '.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    for tag in soup.find_all(lambda t: t.name and t.name.lower() in ("ix:header",)):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
        tag.decompose()
    for td in soup.find_all(["td", "th"]):
        td.insert_after(" | ")
    for el in soup.find_all(BLOCK_TAGS):
        el.insert_before("\n")
        el.insert_after("\n")
    raw = soup.get_text("")
    lines = []
    for line in raw.split("\n"):
        line = re.sub(r"[ \t\r\f\v  ​]+", " ", line).strip()
        line = re.sub(r"(\s*\|\s*)+$", "", line)          # trailing empty cells
        line = re.sub(r"^(\|\s*)+", "", line)
        line = re.sub(r"(\|\s*){2,}", "| ", line)
        if line and line != "|":
            lines.append(line)
    return "\n".join(lines)


_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
           " ": " ", " ": " "}


def normalize(s: str) -> str:
    """Normalise text for word-for-word comparison: unify quotes/dashes, collapse whitespace, lowercase."""
    s = unicodedata.normalize("NFKC", s)
    for a, b in _QUOTES.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def quote_in_text(quote: str, text: str) -> bool:
    """True if `quote` appears word for word in `text` (ignoring whitespace, case and curly quotes)."""
    q = normalize(quote)
    return bool(q) and q in normalize(text)
