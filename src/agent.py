"""VibeMatch agent: plan, retrieve, draft, check, and revise once before answering.

Steps for one request:
  1. check the request (guardrail)
  2. parse it into a taste profile (Gemini with few-shot examples, keyword fallback)
  3. retrieve songs from the catalog with the Project 3 scorer (diversity on)
  4. retrieve genre notes for those songs (second source)
  5. draft an explanation grounded only in steps 3 and 4
  6. check the draft; if it fails, send the problems back and revise once
  7. if it still fails, answer with the scorer's own reasons instead
Every step is written to a trace that is saved in logs/traces.jsonl.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.guardrails import check_explanation, check_request, template_explanation
from src.knowledge import load_genre_notes, notes_for_songs
from src.recommender import load_songs, recommend_songs
from src.request_parser import parse_request

log = logging.getLogger("vibematch.agent")

LOW_CONFIDENCE = 0.45


def setup_logging(log_dir: str = "logs") -> None:
    """Writes INFO and above to logs/vibematch.log (the terminal stays clean)."""
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(log_dir, "vibematch.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_explain_prompt(request: str, results, notes: Dict[str, str], problems: Optional[List[str]] = None) -> str:
    """Prompt for the explanation. The model sees only the picked songs and their genre notes."""
    lines = [
        "You are VibeMatch, a music assistant. Explain to the listener why these songs fit their request.",
        f'Listener request: "{request}"',
        "",
        "Recommended songs (the ONLY songs you may mention):",
    ]
    for rank, (song, score, reasons) in enumerate(results, start=1):
        lines.append(
            f'{rank}. "{song["title"]}" by {song["artist"]}: genre {song["genre"]}, mood {song["mood"]}, '
            f"energy {song['energy']:.2f}, score {score:.2f}. Scorer reasons: {reasons}"
        )
    lines.append("")
    lines.append("Genre notes:")
    for genre, note in notes.items():
        lines.append(f"- {genre}: {note}")
    lines += [
        "",
        "Rules:",
        "- Mention songs only by the exact titles above, in double quotes. Do not name any other song or artist.",
        "- Use only facts from the list and the genre notes. Do not invent lyrics, release dates or stories.",
        "- If a song is a weak fit for the request, say so honestly.",
        "- 3 to 5 sentences, under 100 words, plain text, no headings or bullet points.",
    ]
    if problems:
        lines.append("")
        lines.append("Your previous draft was rejected for these reasons. Fix them:")
        lines += [f"- {p}" for p in problems]
    return "\n".join(lines)


class VibeMatchAgent:
    """Runs the full request -> recommendation -> checked explanation workflow."""

    def __init__(self, llm=None, songs_path: str = "data/songs.csv",
                 notes_path: str = "data/genre_notes.md", k: int = 3,
                 trace_path: Optional[str] = "logs/traces.jsonl", few_shot: bool = True):
        self.llm = llm
        self.songs = load_songs(songs_path)
        self.notes = load_genre_notes(notes_path)
        self.k = k
        self.trace_path = trace_path
        self.few_shot = few_shot

    def run(self, request: str) -> Dict:
        """Returns a dict with status, picks, explanation, confidence and the step trace."""
        trace: List[Dict] = []

        def step(name: str, **detail) -> None:
            trace.append({"step": name, **detail})
            log.info("step %s %s", name, detail)

        ok, reason = check_request(request)
        step("check_request", ok=ok, reason=reason)
        if not ok:
            return self._finish(request, trace, status="refused", message=f"Request refused: {reason}.")

        prefs, parse_conf, notes, source = parse_request(request, self.songs, self.llm, self.few_shot)
        step("parse_request", source=source, prefs=prefs, confidence=parse_conf, notes=notes)
        if prefs.get("off_topic"):
            return self._finish(request, trace, status="refused",
                                message="That doesn't look like a music request, so I won't guess a playlist.")
        if not any(key in prefs for key in ("genre", "mood", "energy")):
            return self._finish(request, trace, status="refused",
                                message="I couldn't tell what kind of music you want. Try naming an activity, mood or genre.")

        # Guardrail: "clean" is a hard rule, not a score penalty. The Project 3 penalty
        # still let an explicit song into the top 3 when it matched genre and mood.
        candidates = self.songs
        if prefs.get("allow_explicit") is False:
            candidates = [s for s in self.songs if not s.get("explicit")]
            step("filter_explicit", removed=len(self.songs) - len(candidates))

        results = recommend_songs(prefs, candidates, self.k, diversity=True)
        picks = [song for song, _, _ in results]
        step("retrieve_songs", picks=[f"{s['title']} ({s['genre']}/{s['mood']})" for s in picks],
             scores=[score for _, score, _ in results])

        genre_notes = notes_for_songs(picks, self.notes)
        step("retrieve_notes", genres=list(genre_notes))

        confidence = self._confidence(prefs, parse_conf, picks)
        step("confidence", value=confidence)

        explanation, explained_by = self._explain(request, results, genre_notes, step)
        warnings = []
        if confidence < LOW_CONFIDENCE:
            warnings.append("Low confidence: the catalog has no close match for this request.")
        return self._finish(request, trace, status="ok", prefs=prefs, results=results,
                            explanation=explanation, explained_by=explained_by,
                            confidence=confidence, warnings=warnings, parse_notes=notes)

    def _explain(self, request, results, genre_notes, step):
        """Draft, check, revise once, then fall back to the template."""
        if self.llm is None:
            step("draft", skipped="no model (offline)")
            return template_explanation(results), "template"
        picks = [song for song, _, _ in results]
        problems = None
        for attempt in (1, 2):
            try:
                draft = self.llm.generate(build_explain_prompt(request, results, genre_notes, problems), temperature=0.4)
            except Exception as exc:
                step("draft", attempt=attempt, error=str(exc)[:120])
                break
            problems = check_explanation(draft, picks, self.songs)
            step("check_explanation", attempt=attempt, passed=not problems, problems=problems, draft=draft)
            if not problems:
                return draft, "model" if attempt == 1 else "model (revised)"
        step("fallback", reason="explanation failed the checks or the model was unavailable")
        return template_explanation(results), "template"

    @staticmethod
    def _confidence(prefs: Dict, parse_conf: float, picks: List[Dict]) -> float:
        """Mix of how sure the parser was and whether the top song matches the asked genre, mood and energy."""
        top = picks[0] if picks else {}
        asked = [key for key in ("genre", "mood", "energy") if key in prefs]
        matched = 0
        for key in asked:
            if key == "energy":
                matched += abs(top.get("energy", 0.0) - prefs["energy"]) <= 0.2
            else:
                matched += top.get(key, "").lower() == prefs[key]
        match_share = matched / len(asked) if asked else 0.5
        return round(0.6 * parse_conf + 0.4 * match_share, 2)

    def _finish(self, request: str, trace: List[Dict], **result) -> Dict:
        """Attaches the trace, saves it to the trace file and returns the result."""
        result["request"] = request
        result["trace"] = trace
        if self.trace_path:
            os.makedirs(os.path.dirname(self.trace_path) or ".", exist_ok=True)
            record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "request": request, "status": result["status"], "trace": trace}
            with open(self.trace_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return result
