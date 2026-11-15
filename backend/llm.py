"""The non-Gnani model: OpenCode Go (`deepseek-v4.1-flash`) for reply chips.

Why a second provider exists at all: Prisma gives us the caller's language and
Timbre speaks the reply, but neither can write a contextual reply chip in that
language. One short chat completion does.

Verified facts (14 Nov 2026):

- Base `https://opencode.ai/inference/go/openai/v1`, model `deepseek-v4.1-flash`.
- The Go endpoint requires a stable `x-opencode-session` header; without it the
  API answers `400 MissingSessionID`.
- `https://opencode.ai/zen/v1` is pay-as-you-go and answered `402` with this key;
  the `-free` model answered `429`. The Go endpoint answered `200` in ~3 s.
- Key: `LLM_API_KEY` in `pashyanti/backend/.env` (gitignored). It never leaves
  this process — not to the browser, not into a log line, not into a message.
- `deepseek-v4.1-flash` is a **reasoning** model: with its default thinking on,
  a one-line answer spends 300–400 reasoning tokens and takes 4–7 s. Sending
  `"thinking": {"type": "disabled"}` returns the same shape in **2.1–3.2 s**
  (measured five lines, 14 Nov). Chips are a hint, not truth — the two safety
  chips are deterministic — so latency wins here.

Every function returns None on any failure. The call must never wait on this
module: `Call` keeps the static locale chips, so a slow or dead model only means
the page shows what it showed before the feature existed.
"""
from __future__ import annotations

import json
import os
import re
import uuid

import requests

import gnani  # noqa: F401  (loads .env so LLM_API_KEY is visible, like gnani.py)

BASE = os.environ.get("LLM_BASE_URL",
                      "https://opencode.ai/inference/go/openai/v1")
MODEL = os.environ.get("LLM_MODEL", "deepseek-v4.1-flash")
TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "6"))
# Stable for the process; one conversation per server run in this build.
SESSION = os.environ.get("LLM_SESSION") or f"pashyanti-{uuid.uuid4().hex[:8]}"

# For the prompt only: the model is told the language, not a code it must guess.
_LANGUAGES = {
    "en": "English",
    "hi": "Hindi (Devanagari script)",
    "bn": "Bengali",
    "mr": "Marathi (Devanagari script)",
    "gu": "Gujarati",
    "pa": "Punjabi (Gurmukhi script)",
    "or": "Odia",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
}


def available() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


def _post(messages, max_tokens=200):
    """One chat completion, or None. Never raises, never logs the key."""
    key = os.environ.get("LLM_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            f"{BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "x-opencode-session": SESSION,
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0,
                "thinking": {"type": "disabled"},
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        return None


def _unfenced(text: str) -> str:
    body = (text or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```[a-zA-Z]*\s*", "", body)
        body = re.sub(r"\s*```$", "", body)
    return body


def _json(text: str):
    """A JSON value from a bare or ```fenced``` answer, or None."""
    if not text:
        return None
    body = _unfenced(text)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    start, end = body.find("["), body.rfind("]")
    if start >= 0 and end > start:
        try:
            return json.loads(body[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _json_object(text: str):
    """An object from a bare or ```fenced``` answer, or None."""
    if not text:
        return None
    body = _unfenced(text)
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        start, end = body.find("{"), body.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(body[start:end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def summary(lines, lang: str = "en") -> dict | None:
    """{who, agreed, next} for the end-of-call card, or None.

    The card is for the **user**, so `lang` is the UI locale, not the caller's
    language. Empty strings are left to the caller: `Call.end_call` keeps the
    extractive value instead of blanking a field the model could not fill.
    """
    transcript = "\n".join(
        f"{'caller' if ln.get('who') == 'caller' else 'user'}: {ln.get('text', '')}"
        for ln in lines
    ).strip()
    if not transcript:
        return None
    language = _LANGUAGES.get(
        (lang or "en").split("-")[0].lower(), "English")
    system = (
        "You summarise a conversation between a user who is Deaf or cannot "
        "speak and another person in the same room. Return ONLY a compact JSON "
        "object with exactly three string fields: \"who\" (who is speaking, at "
        "most 60 characters), \"agreed\" (what was agreed, at most 90), and "
        "\"next\" (what happens next, at most 90). Use only facts present in the "
        "transcript; never invent names, times, amounts or promises. If a field "
        f"is not in the transcript, use an empty string. Write in {language}."
    )
    data = _json_object(_post([
        {"role": "system", "content": system},
        {"role": "user", "content": f"Transcript:\n{transcript}"},
    ], max_tokens=300) or "")
    if data is None:
        return None
    out = {}
    for key, limit in (("who", 60), ("agreed", 90), ("next", 90)):
        value = data.get(key)
        if not isinstance(value, str):
            return None
        out[key] = " ".join(value.split())[:limit]
    return out


def direct_reply(line: str, lang: str | None, context=()) -> str | None:
    """One short reply in the caller's language, or None.

    `context` is the recent caller lines, oldest first, for continuity. The
    model is told to use only facts in the line: a plausible invention read out
    loud by the app is worse than no suggestion.
    """
    text = " ".join((line or "").split())
    if not text:
        return None
    language = _LANGUAGES.get(
        (lang or "en").split("-")[0].lower(), "the caller's language")
    recent = "\n".join(f"caller: {c}" for c in list(context)[-3:])
    system = (
        "You suggest ONE reply for a person who is Deaf or cannot speak and is "
        "talking to someone face to face. You are given the other person's last "
        "line, and sometimes the previous lines. Return ONLY a JSON array with "
        "one string: a short reply this person could say next, at most 40 "
        f"characters, in {language}, in that language's own script. Use only "
        "facts present in the line. Never invent a name, a number, a time, a "
        "price or a promise. If no direct reply fits, return []."
    )
    prompt = recent + "\n" if recent else ""
    content = _post([
        {"role": "system", "content": system},
        {"role": "user", "content": f"{prompt}last line: {text}"},
    ])
    value = _json(content or "")
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, str) and item.strip():
            return item
    return None
