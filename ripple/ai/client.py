"""One place where Ripple talks to Claude.

Safety switches:
- Nothing is sent unless RIPPLE_AI_ENABLED=1 AND ANTHROPIC_API_KEY is set.
- `dry_run=True` builds the exact request and returns it without sending.
- Every call's token use is written to the ai_usage table.
"""
from __future__ import annotations

import json
import sqlite3

from .. import config


class AIDisabled(RuntimeError):
    pass


def ai_ready() -> tuple[bool, str]:
    if not config.ANTHROPIC_API_KEY:
        return False, "ANTHROPIC_API_KEY is not set (add it to .env)."
    if not config.AI_ENABLED:
        return False, "AI calls are switched off. Set RIPPLE_AI_ENABLED=1 in .env to switch them on."
    return True, "ok"


def _client():
    ok, why = ai_ready()
    if not ok:
        raise AIDisabled(why)
    import anthropic  # imported here so the rest of Ripple works without the package
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def build_request(model: str, system: str, user: str, schema: dict, max_tokens: int = 16000,
                  effort: str | None = None) -> dict:
    output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": output_config,
    }


def _log(conn: sqlite3.Connection | None, job: str, model: str, usage, ref: str | None) -> None:
    if conn is None or usage is None:
        return
    conn.execute("INSERT INTO ai_usage (job, model, input_tokens, output_tokens, ref) VALUES (?,?,?,?,?)",
                 (job, model, getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None), ref))
    conn.commit()


def parse_json_reply(message) -> dict:
    if getattr(message, "stop_reason", None) == "refusal":
        raise RuntimeError(f"Claude declined this request: {getattr(message, 'stop_details', None)}")
    if getattr(message, "stop_reason", None) == "max_tokens":
        raise RuntimeError("Reply was cut off (max_tokens reached).")
    text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
    return json.loads(text)


def call_json(job: str, request: dict, conn: sqlite3.Connection | None = None, ref: str | None = None,
              stream: bool = False, fallback: bool = False) -> dict:
    """Send one request and return the parsed JSON reply."""
    client = _client()
    extra = {}
    if fallback:
        # Server-side fallback if the model declines (recommended for Opus-class models).
        extra = {"extra_headers": {"anthropic-beta": "server-side-fallback-2026-07-01"},
                 "extra_body": {"fallbacks": "default"}}
    if stream:
        with client.messages.stream(**request, **extra) as s:
            message = s.get_final_message()
    else:
        message = client.messages.create(**request, **extra)
    _log(conn, job, request["model"], getattr(message, "usage", None), ref)
    return parse_json_reply(message)
