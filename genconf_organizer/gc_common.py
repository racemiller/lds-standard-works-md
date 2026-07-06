"""
Shared helpers for the General Conference scraper -> OpenWebUI pipeline.

Used by:
  - gc_json_to_markdown.py   (converts scraper JSON into Markdown for OpenWebUI)
  - validate_talks.py        (flags duplicated-stanza / repeated-text artifacts)

The scraper's JSON schema isn't fixed, so field extraction is deliberately
defensive: it matches common field names case-insensitively and degrades
gracefully when something is missing.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

# Candidate key names, in priority order, matched case-insensitively.
_FIELD_ALIASES = {
    "title":   ["title", "talk_title", "heading", "name"],
    "speaker": ["speaker", "author", "speaker_name", "by", "given_by"],
    "body":    ["text", "body", "content", "talk", "talk_text", "completion"],
    "url":     ["url", "link", "source", "source_url", "uri", "href"],
    "date":    ["date", "conference", "period", "published"],
}


def _get_field(obj: dict, kind: str):
    """Return the first matching value for a logical field, or None."""
    lowered = {str(k).lower(): v for k, v in obj.items()}
    for alias in _FIELD_ALIASES[kind]:
        val = lowered.get(alias)
        if val not in (None, "", []):
            return val
    return None


def extract_talks(data) -> list[dict]:
    """
    Normalize the many shapes scraper output can take into a flat list of
    talk dicts. Handles: a list of talks, a dict wrapping a list under a
    'talks'/'data'/'results' key, or a dict mapping ids -> talk objects.
    """
    if isinstance(data, list):
        return [t for t in data if isinstance(t, dict)]
    if isinstance(data, dict):
        for wrapper in ("talks", "data", "results", "items"):
            if isinstance(data.get(wrapper), list):
                return [t for t in data[wrapper] if isinstance(t, dict)]
        # dict-of-talks (id -> object)?
        values = list(data.values())
        if values and all(isinstance(v, dict) for v in values):
            return values
        # a single talk object
        if any(k.lower() in sum(_FIELD_ALIASES.values(), []) for k in data):
            return [data]
    return []


def load_json_any(path: Path) -> list[dict]:
    """Load talks from a .json (single document) or .jsonl (one per line)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        out = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                out.extend(extract_talks(json.loads(line)))
        return out
    return extract_talks(json.loads(text))


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTHS = {"04": "April", "10": "October"}
# /general-conference/2024/04/...  -> ("2024", "04")
_URL_DATE = re.compile(r"/general-conference/(\d{4})/(\d{2})\b")


def conference_folder(date_iso: str | None) -> str:
    """'2024-04' -> '2024-April'; missing/odd dates -> 'unknown-conference'.
    Note: 'YYYY-Month' sorts chronologically for April/October, since 'April'
    precedes 'October' alphabetically as well as on the calendar."""
    if not date_iso:
        return "unknown-conference"
    m = re.match(r"(\d{4})-(\d{2})", date_iso)
    if not m:
        return "unknown-conference"
    year, month = m.group(1), m.group(2)
    return f"{year}-{_MONTHS.get(month, month)}"


def derive_date(talk: dict, url: str | None):
    """
    Return (iso, conference_label) e.g. ("2024-04", "April 2024 General Conference").
    Prefers the year/month embedded in the talk URL (most reliable), then falls
    back to any explicit date-ish field. Returns (None, None) if undetermined.
    """
    candidates = []
    if url:
        candidates.append(url)
    raw_date = _get_field(talk, "date")
    if raw_date:
        candidates.append(str(raw_date))

    for c in candidates:
        m = _URL_DATE.search(c)
        if m:
            year, month = m.group(1), m.group(2)
            label_month = _MONTHS.get(month, month)
            return f"{year}-{month}", f"{label_month} {year} General Conference"
        # also accept a bare "YYYY-MM" or "YYYY/MM"
        m2 = re.search(r"(\d{4})[-/](\d{2})", c)
        if m2:
            year, month = m2.group(1), m2.group(2)
            label_month = _MONTHS.get(month, month)
            return f"{year}-{month}", f"{label_month} {year} General Conference"
    return None, None


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------

def slugify(text: str, max_len: int = 60) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "untitled"


# ---------------------------------------------------------------------------
# Body cleaning
# ---------------------------------------------------------------------------

def clean_body(body: str) -> str:
    """Normalize whitespace without guessing paragraph breaks that aren't there."""
    if not body:
        return ""
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r" *\n *", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


# ---------------------------------------------------------------------------
# Duplicate-text detection (the repeated-stanza artifact)
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?\u201d\u2019])\s+")


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    return [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]


def detect_duplication(text: str, min_len: int = 25, repeat_threshold: int = 3) -> dict:
    """
    Heuristic detector for the duplicated-stanza artifact.

    Returns a report dict with:
      - consecutive: list of sentences that appear back-to-back (strong signal)
      - repeated:    list of (sentence, count) appearing >= repeat_threshold times
      - score:       fraction of sentence-instances that are duplicates [0..1]
      - flagged:     bool, True if anything looks suspicious

    Short sentences (< min_len chars) are ignored so liturgical formulae like
    "in the name of Jesus Christ, amen." don't trip the detector.
    """
    sents = split_sentences(text)
    norm = [s.lower() for s in sents]

    consecutive = []
    for i in range(len(norm) - 1):
        if len(norm[i]) >= min_len and norm[i] == norm[i + 1]:
            consecutive.append(sents[i])

    counts = Counter(s for s in norm if len(s) >= min_len)
    first_seen = {}
    for s in sents:
        first_seen.setdefault(s.lower(), s)
    repeated = [
        (first_seen[s], c) for s, c in counts.items() if c >= repeat_threshold
    ]
    repeated.sort(key=lambda x: x[1], reverse=True)

    dup_instances = sum(c - 1 for c in counts.values() if c >= 2)
    score = dup_instances / max(1, len(sents))

    flagged = bool(consecutive) or bool(repeated) or score >= 0.15
    return {
        "consecutive": consecutive,
        "repeated": repeated,
        "score": round(score, 3),
        "sentence_count": len(sents),
        "flagged": flagged,
    }


def collapse_adjacent_duplicates(body: str) -> str:
    """
    CONSERVATIVE fix: collapse runs of immediately-adjacent identical lines (or
    sentences, when the body is a single block) down to one instance. This safely
    removes the most common artifact (stanza printed twice in a row) without
    touching legitimate refrains that are separated by other text. Files that are
    still flagged after this should be reviewed by hand.
    """
    if not body:
        return body

    if "\n" in body.strip():
        units, joiner = body.split("\n"), "\n"
    else:
        units, joiner = split_sentences(body), " "

    out = []
    last_nonempty = None  # compare across intervening blank lines too
    for u in units:
        norm = re.sub(r"\s+", " ", u).strip().lower()
        if norm == "":
            if out and out[-1].strip() == "":
                continue  # collapse runs of blank lines
            out.append(u)
            continue
        if norm == last_nonempty:
            if out and out[-1].strip() == "":
                out.pop()  # also drop the blank line that preceded the dup
            continue
        out.append(u)
        last_nonempty = norm

    while out and out[0].strip() == "":
        out.pop(0)
    while out and out[-1].strip() == "":
        out.pop()
    return joiner.join(out)


# ---------------------------------------------------------------------------
# Convenience: pull a normalized record out of a raw talk dict
# ---------------------------------------------------------------------------

def normalize_talk(talk: dict) -> dict:
    url = _get_field(talk, "url")
    iso, conference = derive_date(talk, url if isinstance(url, str) else None)
    speaker = (_get_field(talk, "speaker") or "").strip()
    if speaker[:3].lower() == "by ":  # defensive: scraper usually strips this already
        speaker = speaker[3:].strip()
    return {
        "title": (_get_field(talk, "title") or "").strip() or None,
        "speaker": speaker or None,
        "body": clean_body(_get_field(talk, "body") or ""),
        "url": url if isinstance(url, str) else None,
        "date_iso": iso,
        "conference": conference,
    }
