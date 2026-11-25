"""Turns a plain-language request into the prefs dict that score_song understands.

The model only fills in a JSON profile. Every field is then checked against the
real catalog, so a made-up genre or an energy of 7 never reaches the scorer.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("vibematch.parser")

FEW_SHOT_EXAMPLES = [
    (
        "something calm to read with, no lyrics",
        {"genre": "classical", "mood": "peaceful", "energy": 0.2, "likes_acoustic": True,
         "target_instrumentalness": 0.9, "mood_tags": ["tender", "spacious"],
         "allow_explicit": None, "unavailable": None, "off_topic": False, "confidence": 0.85},
    ),
    (
        "hype me up for leg day, nothing explicit, my kid is in the car",
        {"genre": "pop", "mood": "intense", "energy": 0.92, "likes_acoustic": False,
         "target_instrumentalness": None, "mood_tags": ["driving"],
         "allow_explicit": False, "unavailable": None, "off_topic": False, "confidence": 0.8},
    ),
    (
        "rainy sunday, feeling a bit down",
        {"genre": "folk", "mood": "melancholy", "energy": 0.3, "likes_acoustic": True,
         "target_instrumentalness": None, "mood_tags": ["tender", "dark"],
         "allow_explicit": None, "unavailable": None, "off_topic": False, "confidence": 0.7},
    ),
    (
        "upbeat stuff while I cook",
        {"genre": None, "mood": "happy", "energy": 0.7, "likes_acoustic": None,
         "target_instrumentalness": None, "mood_tags": ["bright"],
         "allow_explicit": None, "unavailable": None, "off_topic": False, "confidence": 0.6},
    ),
    (
        "some j-rock for my run",
        {"genre": "rock", "mood": "intense", "energy": 0.9, "likes_acoustic": None,
         "target_instrumentalness": None, "mood_tags": ["driving"],
         "allow_explicit": None, "unavailable": "j-rock", "off_topic": False, "confidence": 0.6},
    ),
    (
        "what's the capital of France?",
        {"genre": None, "mood": None, "energy": None, "likes_acoustic": None,
         "target_instrumentalness": None, "mood_tags": [],
         "allow_explicit": None, "unavailable": None, "off_topic": True, "confidence": 0.95},
    ),
]


def build_prompt(request: str, vocab: Dict[str, List[str]], few_shot: bool = True) -> str:
    """Builds the parsing prompt; few_shot=False gives the plain baseline used in the evaluation."""
    lines = [
        "You turn a music request into a JSON taste profile for a small song catalog.",
        f"Allowed genres: {', '.join(vocab['genres'])}.",
        f"Allowed moods: {', '.join(vocab['moods'])}.",
        f"Allowed mood_tags: {', '.join(vocab['tags'])}.",
        "Fields: genre, mood, energy (0.0 to 1.0), likes_acoustic (true/false/null),",
        "target_instrumentalness (0.0 to 1.0 or null), mood_tags (list), allow_explicit",
        "(false only if the user asks for clean music, otherwise null), off_topic (true if the",
        "request is not about music), unavailable (anything the user asked for that is not in",
        "the allowed lists, e.g. a genre the catalog lacks, otherwise null), confidence (0.0 to",
        "1.0, how sure you are).",
        "Leave genre null unless the user names a genre or the activity clearly calls for one.",
        "If the user states an energy level, keep it even when it seems to clash with the mood.",
        "Only use values from the allowed lists. Reply with the JSON object only.",
    ]
    if few_shot:
        lines.append("")
        lines.append("Examples:")
        for text, profile in FEW_SHOT_EXAMPLES:
            lines.append(f"Request: {text}")
            lines.append(f"JSON: {json.dumps(profile)}")
    lines.append("")
    lines.append(f"Request: {request}")
    lines.append("JSON:")
    return "\n".join(lines)


def catalog_vocab(songs: List[Dict]) -> Dict[str, List[str]]:
    """Lists the genres, moods and mood tags that actually exist in the catalog."""
    return {
        "genres": sorted({s["genre"].lower() for s in songs}),
        "moods": sorted({s["mood"].lower() for s in songs}),
        "tags": sorted({t for s in songs for t in s.get("mood_tags", [])}),
    }


def extract_json(text: str) -> Optional[Dict]:
    """Pulls the first {...} object out of a model reply, ignoring code fences and extra words."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def validate_profile(raw: Dict, vocab: Dict[str, List[str]]) -> Tuple[Dict, float, List[str]]:
    """Keeps only valid fields. Returns (prefs, confidence, notes about anything dropped)."""
    notes: List[str] = []
    prefs: Dict = {}

    for field, allowed in (("genre", vocab["genres"]), ("mood", vocab["moods"])):
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            value = value.strip().lower()
            if value in allowed:
                prefs[field] = value
            else:
                notes.append(f"dropped unknown {field} '{value}'")

    energy = raw.get("energy")
    if isinstance(energy, (int, float)) and not isinstance(energy, bool):
        if not 0.0 <= energy <= 1.0:
            notes.append(f"energy {energy} clamped to 0-1")
        prefs["energy"] = round(min(1.0, max(0.0, float(energy))), 2)

    if isinstance(raw.get("likes_acoustic"), bool):
        prefs["likes_acoustic"] = raw["likes_acoustic"]
    if raw.get("allow_explicit") is False:
        prefs["allow_explicit"] = False

    inst = raw.get("target_instrumentalness")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        prefs["target_instrumentalness"] = round(min(1.0, max(0.0, float(inst))), 2)

    tags = raw.get("mood_tags") or []
    if isinstance(tags, list):
        good = [t.lower() for t in tags if isinstance(t, str) and t.lower() in vocab["tags"]]
        bad = [t for t in tags if isinstance(t, str) and t.lower() not in vocab["tags"]]
        if good:
            prefs["mood_tags"] = good
        if bad:
            notes.append(f"dropped unknown mood tags {bad}")

    confidence = raw.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        confidence = 0.5
    confidence = min(1.0, max(0.0, float(confidence)))

    missing = raw.get("unavailable")
    if isinstance(missing, str) and missing.strip():
        notes.append(f"the catalog has no {missing.strip()}; showing the closest matches")

    # Every dropped field means the model guessed outside the catalog: trust it less.
    confidence = max(0.0, confidence - 0.15 * len(notes))
    if raw.get("off_topic") is True:
        prefs["off_topic"] = True
    return prefs, round(confidence, 2), notes


# Offline fallback: plain keyword rules, used when there is no API key or the API fails.
KEYWORD_RULES = [
    (("study", "studying", "focus", "homework", "coding", "code"),
     {"genre": "lofi", "mood": "focused", "energy": 0.4, "target_instrumentalness": 0.85}),
    (("sleep", "meditate", "meditation"), {"genre": "ambient", "mood": "chill", "energy": 0.2}),
    (("read", "reading"), {"genre": "classical", "mood": "peaceful", "energy": 0.2}),
    (("gym", "workout", "run", "running", "lift", "hype", "cardio"),
     {"genre": "pop", "mood": "intense", "energy": 0.9}),
    (("party", "dance", "dancing"), {"genre": "latin", "mood": "playful", "energy": 0.85}),
    (("sad", "down", "rainy", "cry", "breakup"), {"genre": "folk", "mood": "melancholy", "energy": 0.3}),
    (("drive", "driving", "night drive", "road trip"), {"genre": "synthwave", "mood": "moody", "energy": 0.7}),
    (("dinner", "date", "romantic"), {"genre": "r&b", "mood": "romantic", "energy": 0.45}),
    (("chill", "relax", "relaxing", "coffee", "cooking"), {"genre": "jazz", "mood": "relaxed", "energy": 0.4}),
    (("happy", "upbeat", "sunny"), {"genre": "pop", "mood": "happy", "energy": 0.8}),
]


def keyword_parse(request: str, vocab: Dict[str, List[str]]) -> Tuple[Dict, float, List[str]]:
    """Rule-based parser: first keyword rule that matches wins; a genre named outright overrides it."""
    text = request.lower()
    words = set(re.findall(r"[a-z&]+", text))
    prefs: Dict = {}
    for keys, profile in KEYWORD_RULES:
        if any((k in words) if " " not in k else (k in text) for k in keys):
            prefs = dict(profile)
            break
    for genre in sorted(vocab["genres"], key=len, reverse=True):
        if re.search(rf"\b{re.escape(genre)}\b", text):
            prefs["genre"] = genre
            break
    if re.search(r"\b(clean|no explicit|nothing explicit|kid|kids)\b", text):
        prefs["allow_explicit"] = False
    if not prefs:
        return {}, 0.0, ["no keyword matched"]
    prefs.setdefault("energy", 0.5)
    return prefs, 0.5, []


HIGH_ENERGY_WORDS = ("high energy", "high-energy", "energetic", "hype", "fast", "intense", "pump")
LOW_ENERGY_WORDS = ("low energy", "low-energy", "calm", "slow", "quiet", "sleep", "soft")


def cross_check_energy(request: str, prefs: Dict, confidence: float, notes: List[str]):
    """Overrides the parsed energy when it contradicts energy words in the request itself.

    Found in testing: for "sad songs but with super high energy" the few-shot model copied
    the low energy from the "rainy sunday" example and returned 0.3.
    """
    text = request.lower()
    energy = prefs.get("energy")
    if energy is None:
        return prefs, confidence
    if any(w in text for w in HIGH_ENERGY_WORDS) and energy < 0.6:
        notes.append(f"request asks for high energy but the profile had {energy}; using 0.85")
        prefs["energy"] = 0.85
        confidence = max(0.0, confidence - 0.2)
    elif any(w in text for w in LOW_ENERGY_WORDS) and energy > 0.6:
        notes.append(f"request asks for low energy but the profile had {energy}; using 0.3")
        prefs["energy"] = 0.3
        confidence = max(0.0, confidence - 0.2)
    return prefs, round(confidence, 2)


def parse_request(request: str, songs: List[Dict], llm=None, few_shot: bool = True):
    """Returns (prefs, confidence, notes, source). source is 'llm' or 'keywords'."""
    vocab = catalog_vocab(songs)
    if llm is not None:
        try:
            reply = llm.generate(build_prompt(request, vocab, few_shot))
            raw = extract_json(reply)
            if raw is None:
                log.warning("parser: reply was not JSON: %r", reply[:120])
            else:
                prefs, confidence, notes = validate_profile(raw, vocab)
                prefs, confidence = cross_check_energy(request, prefs, confidence, notes)
                log.info("parser: llm prefs=%s confidence=%.2f notes=%s", prefs, confidence, notes)
                return prefs, confidence, notes, "llm"
        except Exception as exc:
            log.warning("parser: llm failed, using keywords: %s", exc)
    prefs, confidence, notes = keyword_parse(request, vocab)
    prefs, confidence = cross_check_energy(request, prefs, confidence, notes)
    log.info("parser: keyword prefs=%s", prefs)
    return prefs, confidence, notes, "keywords"
