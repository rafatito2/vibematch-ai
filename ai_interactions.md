# AI Interactions Log

## Agentic workflow and reasoning traces

The agent in `src/agent.py` runs a fixed decision chain for every request and writes each intermediate step to `logs/traces.jsonl`:

1. `check_request`: guardrail on the raw text (refuse or continue)
2. `parse_request`: tool call to Gemini (or the keyword parser), with the validated profile, confidence and correction notes
3. `filter_explicit`: only when the profile asks for clean music
4. `retrieve_songs`: tool call to the Project 3 scorer
5. `retrieve_notes`: tool call to the genre notes
6. `confidence`: score plus which requested fields the top pick misses (this decides whether the model must admit a mismatch)
7. `check_explanation`: the draft and the problems found; on failure the problems are sent back for one revision
8. `fallback`: only if the draft failed twice or the model was unavailable

The traces from the README sample runs are committed in [`assets/agent_traces.jsonl`](assets/agent_traces.jsonl) (one JSON line per request), and the full terminal output with traces is in [`assets/sample_runs.txt`](assets/sample_runs.txt). Example, for a request the catalog can't fully satisfy:

```json
{"step": "check_request", "ok": true, "reason": "ok"}
{"step": "parse_request", "source": "llm", "prefs": {"genre": "pop", "mood": "confident", "energy": 0.8, "mood_tags": ["driving", "bright"]}, "confidence": 0.6, "notes": ["the catalog has no k-pop; showing the closest matches"]}
{"step": "retrieve_songs", "picks": ["Sunrise City (pop/happy)", "Gym Hero (pop/intense)", "Concrete Crown (hip hop/confident)"], "scores": [3.97, 3.05, 2.47]}
{"step": "retrieve_notes", "genres": ["pop", "hip hop"]}
{"step": "confidence", "value": 0.63, "top_pick_misses": ["mood 'confident'"]}
{"step": "check_explanation", "attempt": 1, "passed": true, "problems": [], "draft": "The catalog has no song that fits everything, but we can still build a great drive. ..."}
```

The revise path is covered by tests with a scripted model, since the real model passed the check on the first draft in all 9 answered evaluation cases. In `test_agent_revises_once_then_accepts` the first draft names "Lo-Fi Dreams Vol. 2" (not in the catalog), `check_explanation` returns `names 'Lo-Fi Dreams Vol. 2', which is not one of the recommended songs`, that problem is appended to the second prompt, and the corrected draft is accepted as `model (revised)`.

## Prompts used in the system

- **Parser** (`build_prompt` in `src/request_parser.py`): lists the allowed genres, moods and tags from the catalog, describes each JSON field, and gives six examples. Rules added after testing: "Leave genre null unless the user names a genre or the activity clearly calls for one" and "If the user states an energy level, keep it even when it seems to clash with the mood."
- **Explanation** (`build_explain_prompt` in `src/agent.py`): gives only the picked songs with their scorer reasons and the genre notes; requires exact titles in quotes, no outside facts, honesty about weak fits, 3–5 sentences. When the top pick misses a requested field it adds: "The catalog has no song that fits everything. Say this plainly in your first sentence."

## Specialization comparison

See the table in [`model_card.md`](model_card.md#specialization-few-shot-vs-baseline): few-shot 12/12 vs zero-shot 8/12 on the same cases.

## Working with the coding assistant

| Task I asked for | What it produced | What I changed or checked |
|---|---|---|
| Plan how to extend Project 3 into an AI system | Parse → retrieve → draft → check → revise agent, keep the scorer for ranking | Kept it; asked for an offline mode so it runs without a key |
| Write the explanation guardrail | Title checks for invented and unpicked songs, word limit | Added moods to the allowed quoted words after a false alarm risk |
| Confidence score | Genre + mood match only | Rejected after a contradictory request scored 0.58; energy now counts and a mismatch warning was added |
| Clean-request handling | Reused the Project 3 explicit penalty | Changed to a hard filter after "Gym Hero" appeared in a clean top 3 |
| Debug a failing evaluation case | Found 429 quota errors in the log, not a parser bug | Cross-check now also runs on the keyword fallback; evaluation waits between cases |
