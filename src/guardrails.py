"""Checks on the way in (the request) and on the way out (the model's explanation)."""

import re
from typing import Dict, List, Tuple

MAX_REQUEST_CHARS = 300
MAX_EXPLANATION_WORDS = 120

INJECTION_PATTERNS = (
    "ignore previous", "ignore all previous", "ignore the above", "system prompt",
    "you are now", "disregard your instructions",
)


def check_request(request: str) -> Tuple[bool, str]:
    """Returns (ok, reason). Rejects empty, overly long and prompt-injection style requests."""
    text = (request or "").strip()
    if not text:
        return False, "empty request"
    if len(text) > MAX_REQUEST_CHARS:
        return False, f"request is longer than {MAX_REQUEST_CHARS} characters"
    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in lowered:
            return False, f"request looks like an instruction to the model ('{pattern}')"
    return True, "ok"


def _quoted_phrases(text: str) -> List[str]:
    """Titles the model put in quotes or bold, which is how it names songs."""
    found = re.findall(r'"([^"\n]{2,60})"|“([^”\n]{2,60})”|\*\*([^*\n]{2,60})\*\*', text)
    return [next(part for part in groups if part).strip() for groups in found]


def check_explanation(text: str, picks: List[Dict], catalog: List[Dict]) -> List[str]:
    """Returns a list of problems; an empty list means the explanation passed."""
    problems: List[str] = []
    if not text or not text.strip():
        return ["explanation is empty"]

    lowered = text.lower()
    picked_titles = {s["title"].lower() for s in picks}
    catalog_titles = {s["title"].lower() for s in catalog}
    known_names = picked_titles | {
        value.lower() for s in picks for value in (s["artist"], s["genre"], s["mood"])
    }

    for title in sorted(catalog_titles - picked_titles):
        if re.search(rf"\b{re.escape(title)}\b", lowered):
            problems.append(f"mentions '{title}', which is in the catalog but was not recommended")

    for phrase in _quoted_phrases(text):
        if phrase.lower() not in known_names:
            problems.append(f"names '{phrase}', which is not one of the recommended songs")

    if not any(title in lowered for title in picked_titles):
        problems.append("does not mention any of the recommended songs")

    words = len(text.split())
    if words > MAX_EXPLANATION_WORDS:
        problems.append(f"too long ({words} words, limit {MAX_EXPLANATION_WORDS})")
    return problems


def template_explanation(results: List[Tuple[Dict, float, str]]) -> str:
    """Plain explanation built only from the scorer's own reasons. Used when the model fails."""
    lines = []
    for song, score, reasons in results:
        main = "; ".join(reasons.split("; ")[:2])
        lines.append(f'"{song["title"]}" by {song["artist"]} ({song["genre"]}, score {score:.2f}): {main}.')
    return "\n".join(lines)
