"""OPTIONAL backup: answer the daily queue with a free model instead of the Claude Code session.

OFF by default. To switch it on, put in .env:
    RIPPLE_BACKUP_AI=openrouter      (or: gemini)
    OPENROUTER_API_KEY=...           free account at openrouter.ai, use a model ending in ":free"
    GEMINI_API_KEY=...               free tier key from aistudio.google.com
    RIPPLE_BACKUP_MODEL=...          optional; defaults below

Then:  python -m ripple ai-backup   (writes ai_work/results.json)
       python -m ripple ai-import   (same checkers as always)

Notes:
- Free models are weaker than Claude; the code checkers still throw out any quote
  that isn't word for word in the filing, and any company that isn't on the map.
- Free tiers may log or train on what you send. Everything sent here is public
  (SEC filings, news headlines), but keep that in mind.
- Free model names change often. If a call fails with "model not found", set
  RIPPLE_BACKUP_MODEL to a current free model listed on the provider's site.
"""
from __future__ import annotations

import json
import re

import requests

from .. import config
from ..queue import QUEUE_FILE, RESULTS_FILE
from . import prompts

DEFAULT_MODELS = {"openrouter": "meta-llama/llama-3.3-70b-instruct:free", "gemini": "gemini-2.5-flash"}


def provider() -> tuple[str | None, str]:
    p = (config.get("RIPPLE_BACKUP_AI", "off") or "off").lower()
    if p in ("off", "", "none", "0"):
        return None, "Backup AI is off (set RIPPLE_BACKUP_AI=openrouter or gemini in .env)."
    if p == "openrouter" and not config.get("OPENROUTER_API_KEY"):
        return None, "OPENROUTER_API_KEY is not set."
    if p == "gemini" and not config.get("GEMINI_API_KEY"):
        return None, "GEMINI_API_KEY is not set."
    if p not in DEFAULT_MODELS:
        return None, f"Unknown backup provider '{p}' (use openrouter or gemini)."
    return p, "ok"


def _json_from(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)  # free models sometimes wrap JSON in prose or ``` fences
    return json.loads(m.group(0) if m else text)


def ask(p: str, system: str, user: str, schema: dict) -> dict:
    model = config.get("RIPPLE_BACKUP_MODEL") or DEFAULT_MODELS[p]
    user = user + "\n\nReturn only JSON matching this schema:\n" + json.dumps(schema)
    if p == "openrouter":
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", timeout=180,
                          headers={"Authorization": f"Bearer {config.get('OPENROUTER_API_KEY')}"},
                          json={"model": model, "messages": [{"role": "system", "content": system},
                                                             {"role": "user", "content": user}],
                                "response_format": {"type": "json_object"}})
        r.raise_for_status()
        return _json_from(r.json()["choices"][0]["message"]["content"])
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", timeout=180,
                      headers={"x-goog-api-key": config.get("GEMINI_API_KEY")},
                      json={"systemInstruction": {"parts": [{"text": system}]},
                            "contents": [{"role": "user", "parts": [{"text": user}]}],
                            "generationConfig": {"responseMimeType": "application/json"}})
    r.raise_for_status()
    return _json_from(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def run() -> dict:
    p, why = provider()
    if not p:
        return {"switched_off": why}
    queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    if queue["status"] != "ready":
        return {"message": f"queue is {queue['status']}; nothing to do"}
    results = {"queue_id": queue["queue_id"], "answered_by": f"backup:{p}", "job1": [], "job2": [], "job3": []}
    errors = []
    for t in queue["job1_link_extractor"]:
        user = prompts.LINK_EXTRACTOR_USER.format(company_name=t["company_name"], doc_type=t["doc_type"],
                                                  published_at=t["published_at"], section=t["section"], section_text=t["text"])
        try:
            results["job1"].append({"task_id": t["task_id"], **ask(p, prompts.LINK_EXTRACTOR_SYSTEM, user, prompts.LINK_EXTRACTOR_SCHEMA)})
        except Exception as exc:
            errors.append(f"{t['task_id']}: {exc}")
    for t in queue["job2_event_checker"]:
        listing = ", ".join(f"{k}: {v}" for k, v in t["matched_nodes"].items())
        user = prompts.EVENT_CHECKER_USER.format(matched_nodes=listing, headline_and_summary=t["text"])
        try:
            results["job2"].append({"task_id": t["task_id"], **ask(p, prompts.EVENT_CHECKER_SYSTEM, user, prompts.EVENT_CHECKER_SCHEMA)})
        except Exception as exc:
            errors.append(f"{t['task_id']}: {exc}")
    for t in queue["job3_ripple_explainer"]:
        user = prompts.RIPPLE_EXPLAINER_USER.format(
            event_title=t["title"], event_type=t["event_type"], severity=t["severity"], started_at=t["started_at"],
            event_source_snippets=json.dumps(t["sources"], ensure_ascii=False),
            paths_with_scores_and_quotes=json.dumps(t["companies_reached"], ensure_ascii=False, indent=1))
        try:
            results["job3"].append({"task_id": t["task_id"], **ask(p, prompts.RIPPLE_EXPLAINER_SYSTEM, user, prompts.RIPPLE_EXPLAINER_SCHEMA)})
        except Exception as exc:
            errors.append(f"{t['task_id']}: {exc}")
    RESULTS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"written": str(RESULTS_FILE), "errors": errors}
