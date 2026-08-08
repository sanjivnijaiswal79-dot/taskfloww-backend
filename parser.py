"""
backend/parser.py — Deterministic mock NLP parser for POST /tasks/quick-add.

Design note: role-based prompt structure
-----------------------------------------
The endpoint constructs a standard role-based LLM message structure —
a system message describing the parsing contract and a user message
carrying the free-text description — before calling this function.
That structure is preserved so the code looks identical whether the mock
or a real model answers the prompt.  This function simulates what an LLM
would return: it applies the same rule set described in the system message
and returns the same JSON-shaped dict a model call would produce.

Prompting technique: zero-shot
-------------------------------
The system message gives the model explicit rules (priority keyword groups,
date phrase order, title-stripping steps) without providing worked examples
inside the prompt.  This is zero-shot prompting: the model is told *what* to
do, not shown example input→output pairs.  Zero-shot keeps the prompt short
and the token cost predictable — every request pays the same fixed overhead
regardless of how many examples we could have listed.  Because the rules are
exhaustive and deterministic (no ambiguity about which group fires or which
phrase wins), an LLM following them reliably produces the same output as this
mock, making few-shot example pairs unnecessary.

Public API
----------
build_prompt(description: str) -> list[dict]
    Returns the role-based message list: [system_msg, user_msg].
    Used by the endpoint so the prompt structure is explicit in the code
    even when the mock is active.

parse_quick_add(description: str) -> dict
    Applies the deterministic algorithm and returns:
        {
            "title":         str,   # never empty; "Untitled task" if stripped result is blank
            "priority":      str,   # exactly "low" | "medium" | "high"
            "due_date_hint": str | None,  # matched phrase, lower-case, or None
        }

Algorithm (mirrors the system-message contract exactly)
--------------------------------------------------------
a. Build a lower-cased working copy for keyword matching; keep the
   original-cased description for the title step (d).

b. Priority — first matching group wins:
   (i)  "urgent" or "asap"           → "high"
   (ii) "whenever" or "low priority" → "low"
   (iii) default                      → "medium"
   Group (i) wins if both groups match.
   ALL group (i)/(ii) keywords are stripped from the title, not just the
   one that determined priority.

c. Due-date hint — first matching phrase wins (checked in this order):
   1. "today"
   2. "tomorrow"
   3. "next week"
   4. "next monday" … "next sunday"  (Monday-to-Sunday order)
   5. "monday" … "sunday"            (Monday-to-Sunday order; only if no
                                      "next <weekday>" matched above)
   Stored as-is (lower-case) in due_date_hint; None if nothing matches.

d. Title — start from the ORIGINAL-CASED description string; remove every
   occurrence of:
   • every group (i)/(ii) keyword ("urgent", "asap", "whenever",
     "low priority") — case-insensitive regex, whole-word for single words,
     exact phrase for multi-word keywords.
   • every occurrence of the matched date phrase from step (c), if any.
   Strip leading/trailing whitespace.  If empty or whitespace-only, use
   the literal string "Untitled task".
"""

import re
from typing import Optional

from dotenv import load_dotenv

# Load .env so USE_REAL_LLM and OPENAI_API_KEY are available via os.environ
load_dotenv()


# ─── keyword / phrase tables (ordered where order matters) ────────────────────

# Priority group (i): high
_HIGH_KEYWORDS = ["urgent", "asap"]

# Priority group (ii): low
_LOW_KEYWORDS = ["whenever", "low priority"]

# All priority-related phrases (used for stripping from title)
_PRIORITY_STRIP_TERMS = _HIGH_KEYWORDS + _LOW_KEYWORDS

# Date phrases — order matters; earlier entries win.
# "next <weekday>" entries MUST be checked before bare weekday entries.
_DATE_PHRASES = [
    "today",
    "tomorrow",
    "next week",
    "next monday",
    "next tuesday",
    "next wednesday",
    "next thursday",
    "next friday",
    "next saturday",
    "next sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


# ─── helpers ──────────────────────────────────────────────────────────────────

def _contains(text_lower: str, phrase: str) -> bool:
    """
    Return True if *phrase* appears in *text_lower* as a whole-word match
    (for single-word phrases) or an exact substring match (for multi-word
    phrases).

    Multi-word phrases (e.g. "next friday", "low priority") are matched as
    exact substrings because the space already acts as a natural boundary.
    Single-word phrases (e.g. "urgent", "asap") are matched as whole words
    so that "urgently" does not trigger the "urgent" rule.
    """
    if " " in phrase:
        # Multi-word: require exact substring (boundaries provided by spaces)
        return phrase in text_lower
    else:
        # Single-word: require whole-word boundary
        return bool(re.search(r"\b" + re.escape(phrase) + r"\b", text_lower))


def _strip_term(text: str, phrase: str) -> str:
    """
    Remove every occurrence of *phrase* from *text* (case-insensitive).

    For multi-word phrases:  exact substring, case-insensitive.
    For single-word phrases: whole-word boundary, case-insensitive.

    Returns the text with the phrase(s) removed (not stripped of surrounding
    whitespace — that is done once at the end of parse_quick_add).
    """
    if " " in phrase:
        return re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)
    else:
        return re.sub(r"\b" + re.escape(phrase) + r"\b", "", text, flags=re.IGNORECASE)


# ─── public API ───────────────────────────────────────────────────────────────

def build_prompt(description: str) -> list[dict]:
    """
    Build the role-based message list for the quick-add parsing task.

    Returns a list of two dicts:
        [
            {"role": "system", "content": "<parsing contract>"},
            {"role": "user",   "content": "<the free-text description>"},
        ]

    This structure is identical to what you would send to any OpenAI-compatible
    chat-completion endpoint.  The endpoint calls this function before invoking
    the parser so the prompt structure is explicit in the code regardless of
    whether the mock or a real model is active.
    """
    system_content = (
        "You are a task-management assistant that converts free-text task descriptions "
        "into structured JSON objects. "
        "For every input you must output exactly three fields:\n"
        "  - title:         the description with priority/date keywords removed, trimmed. "
        "If the result is empty, use the literal string 'Untitled task'.\n"
        "  - priority:      one of 'low', 'medium', 'high'. "
        "Detect 'urgent'/'asap' → 'high'; 'whenever'/'low priority' → 'low'; default 'medium'. "
        "The first matching group wins.\n"
        "  - due_date_hint: the first matched date phrase from the text "
        "('today', 'tomorrow', 'next week', 'next <weekday>', or bare '<weekday>'), "
        "lower-case, or null if none is present.\n"
        "Strip ALL priority keyword occurrences and ALL occurrences of the matched "
        "date phrase from the title — not just the one that decided priority.\n"
        "Respond with a JSON object only — no explanation."
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user",   "content": description},
    ]


def parse_quick_add(description: str) -> dict:
    """
    Deterministic mock parser — simulates an LLM response following the
    system-message contract defined in build_prompt().

    Parameters
    ----------
    description : str
        The raw free-text description from the request body.

    Returns
    -------
    dict with keys:
        "title"         : str   — never empty; falls back to "Untitled task"
        "priority"      : str   — "low" | "medium" | "high"
        "due_date_hint" : str | None
    """
    # ── (a) working copies ────────────────────────────────────────────────────
    lower = description.lower()
    original = description          # kept for original-cased title stripping

    # ── (b) priority ──────────────────────────────────────────────────────────
    has_high = any(_contains(lower, kw) for kw in _HIGH_KEYWORDS)
    has_low  = any(_contains(lower, kw) for kw in _LOW_KEYWORDS)

    if has_high:
        priority = "high"
    elif has_low:
        priority = "low"
    else:
        priority = "medium"

    # ── (c) due-date hint ─────────────────────────────────────────────────────
    due_date_hint: Optional[str] = None
    for phrase in _DATE_PHRASES:
        if _contains(lower, phrase):
            due_date_hint = phrase   # already lower-case
            break

    # ── (d) title ─────────────────────────────────────────────────────────────
    # Start from the original-cased string.
    title = original

    # Strip ALL group (i)/(ii) keywords wherever they appear.
    for term in _PRIORITY_STRIP_TERMS:
        title = _strip_term(title, term)

    # Strip ALL occurrences of the matched date phrase (if any).
    if due_date_hint is not None:
        title = _strip_term(title, due_date_hint)

    # Trim and apply placeholder fallback.
    title = title.strip()
    if not title:
        title = "Untitled task"

    return {
        "title":         title,
        "priority":      priority,
        "due_date_hint": due_date_hint,
    }
