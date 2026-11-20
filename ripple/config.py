"""Settings for Ripple.

Every key and secret is read from environment variables (or from a local
`.env` file that is NEVER committed). Nothing secret lives in the code.
See `.env.example` for the full list.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("RIPPLE_DB", DATA_DIR / "ripple.db"))
RAW_DIR = DATA_DIR / "raw"
SEED_FILE = DATA_DIR / "seed" / "nodes.json"


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from ROOT/.env into the environment (if present).

    Values already set in the real environment win.
    """
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    return value if value not in ("", None) else default


def flag(name: str) -> bool:
    """True when an on/off setting is switched on (1, true, yes, on)."""
    return (get(name, "") or "").lower() in {"1", "true", "yes", "on"}


# --- SEC EDGAR -------------------------------------------------------------
# SEC requires a User-Agent with a contact email. Read it from the environment.
# Stray line breaks or extra spaces (easy to type on a phone) would make SEC reject the request.
SEC_USER_AGENT = " ".join((get("SEC_USER_AGENT") or "").split()) or None
SEC_MAX_REQUESTS_PER_SECOND = 8  # SEC limit is 10/s; stay safely under it.

# --- Claude API (AI jobs) ----------------------------------------------------
ANTHROPIC_API_KEY = get("ANTHROPIC_API_KEY")
# Master switch: AI calls only happen when this is switched on AND a key exists.
AI_ENABLED = flag("RIPPLE_AI_ENABLED")
MODEL_LINK_EXTRACTOR = get("RIPPLE_MODEL_LINK_EXTRACTOR", "claude-haiku-5-5")
MODEL_EVENT_CHECKER = get("RIPPLE_MODEL_EVENT_CHECKER", "claude-haiku-5-5")
MODEL_RIPPLE_EXPLAINER = get("RIPPLE_MODEL_RIPPLE_EXPLAINER", "claude-opus-5-5")

# --- Other filing systems ----------------------------------------------------
OPENDART_API_KEY = get("OPENDART_API_KEY")
OPENDART_ENABLED = flag("RIPPLE_OPENDART_ENABLED")
EDINET_API_KEY = get("EDINET_API_KEY")
EDINET_ENABLED = flag("RIPPLE_EDINET_ENABLED")
AISSTREAM_API_KEY = get("AISSTREAM_API_KEY")  # used in a later phase
