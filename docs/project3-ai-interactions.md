# AI Interactions Log

Tool used: Claude Code (agent mode in the terminal).

---

## Agentic Workflow (SF8)

**What task did you give the agent?**

Add five new attributes to every song in the catalog and update the scoring so they count, without changing the results for profiles that do not use them.

**Prompts used:**

> Add these columns to data/songs.csv for all 20 songs: popularity (0-100), release_decade, mood_tags (pipe separated, like "nostalgic|warm"), instrumentalness (0-1) and explicit (0 or 1). Then update load_songs and score_song in src/recommender.py. The new attributes should only add or remove points when the user profile includes a matching preference, so the existing profiles keep the same scores. Each rule must add its own reason string. Add tests.

> Add two profiles to main.py that use the new attributes: one for focus music and one for a workout with no explicit songs.

**What did the agent generate or change?**

- `data/songs.csv`: five new columns on all 20 rows.
- `src/recommender.py`: new weights, new optional fields on `Song` and `UserProfile`, parsing of `mood_tags` and `explicit` in `load_songs`, and a helper `_score_advanced()` called from `score_song`.
- `src/main.py`: "Focus Session" and "Clean Workout" profiles.
- `tests/test_recommender.py`: three new tests.

**What did you verify or fix manually?**

- Ran the five original profiles before and after. The scores were identical, which confirmed the new rules stay off unless asked for.
- Added the Focus Flow reasons by hand (2.00 + 1.00 + 1.50 + 0.50 + 1.00 + 0.21 + 0.49 = 6.70) and it matched the printed score.
- Checked that Gym Hero loses exactly 2.00 in the Clean Workout profile.
- The starter tests build `Song` with only the original 10 fields, so the new fields needed default values or the tests would break.
- flake8 flagged a loop variable named `field` that shadowed the dataclass import. Renamed it to `column`.

---

## Design Pattern (SF10)

**Which design pattern did you use?**

Strategy.

**How did AI help you brainstorm or implement it?**

I attached `recommender.py` and asked how to support several ranking modes without copying `score_song` or filling it with `if mode == ...` branches. The AI offered two options: a plain dictionary of weight sets, or a small Strategy class per mode. I went with the classes because each mode gets a name and a description that `main.py` can print, and a future mode could override `score()` completely instead of only changing weights. I kept the scoring math in one function so the modes cannot drift apart.

**How does the pattern appear in your final code?**

- `ScoringStrategy` in `src/recommender.py` is the base class (balanced mode). It has `name`, `description`, `weights` and a `score()` method.
- `GenreFirst`, `MoodFirst` and `EnergyFocused` are subclasses that change the weights.
- `STRATEGIES` maps each name to an instance.
- `recommend_songs(..., strategy=...)` calls `strategy.score()` for every song.
- `src/main.py` picks the strategy with `--mode`.
