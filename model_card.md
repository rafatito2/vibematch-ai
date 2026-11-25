# Model Card: VibeMatch AI

## Overview

- **What it does:** turns a plain-language music request into three songs from a 20-song catalog, with a short grounded explanation, a confidence score and warnings.
- **Base project:** Project 3, Music Recommender Simulation (VibeMatch 1.0). The scorer and catalog are unchanged.
- **Models:** Gemini `gemini-3.5-flash-lite` (fallback `gemini-2.5-flash-lite`) for parsing and explanations. Ranking is the deterministic Project 3 scorer, not a model.
- **Data:** `data/songs.csv` (20 fictional songs, 17 genres) and `data/genre_notes.md` (one listening note per genre, written by me).
- **Intended use:** a class project and portfolio demo of grounding, guardrails and evaluation. Not a real music service.

## Specialization: few-shot vs baseline

The parser prompt has six examples that show the JSON format, leaving genre empty when the user doesn't imply one, keeping a stated energy level, and reporting things the catalog lacks. The baseline is the same prompt with no examples (`few_shot=False`). Same 12 requests, same model, run back to back (`python -m src.evaluate --compare`):

| | Few-shot (used) | Zero-shot baseline |
|---|---|---|
| Cases passed | **12 / 12** | 8 / 12 |
| Average confidence | 0.80 | 0.86 |
| "reggaeton for a party" | latin, Fuego Lento | edm, Laser Bloom |
| "rainy sunday, feeling a bit down" | folk / melancholy, Paper Boats | lofi / chill, Library Rain |
| "k-pop for a road trip" | reports "no k-pop" | no warning |
| "sad songs but with super high energy" | high-energy picks + warning | slow blues song first (energy 0.33) |

The baseline was wrong more often and more confident while doing it.

## Limitations and biases

- **Tiny catalog.** 20 songs and mostly one song per genre, so "the best match" is often the only match. Lofi and pop listeners get real choices; blues, metal or reggae fans get one song and two fillers.
- **The model fills in things nobody asked for.** For "k-pop for a road trip" it added the mood "confident", and the warning then says the top pick "misses the requested mood 'confident'", which the user never requested.
- **Confidence is about the parsed profile, not the person.** If the parser misreads the request and the catalog matches the misread version, confidence is still high. The energy cross-check only covers words I listed.
- **English and Western genre labels only.** Requests in Spanish or for genres outside the list fall back to the closest label (k-pop becomes pop).
- **Explanation check is shallow.** It catches invented or unpicked song titles, but not a wrong fact about a picked song (for example claiming a song has lyrics when its instrumentalness is high).

## Misuse and how I limit it

- **Prompt injection or using it as a free chatbot.** Off-topic requests are refused, requests over 300 characters are refused, and common injection phrases are blocked before any model call. The model only ever sees a fixed prompt with the request inserted, and its output is parsed as JSON or checked before being shown.
- **Inappropriate songs for kids.** "Clean" requests remove explicit songs before ranking instead of just lowering their score.
- **Trusting it too much.** Every answer shows a confidence score and a warning when nothing fits, and the explanation is required to say so in its first sentence.
- **Leaking the API key.** The key lives in `.env`, which is git-ignored; `.env.example` has a placeholder.

## What surprised me in testing

- The zero-shot prompt was **more** confident and **less** accurate. If I had used the model's own confidence I would have shipped the worse version.
- The few-shot examples help and also leak: "rainy sunday → energy 0.3" made the model answer 0.3 for "sad but super high energy". Fixing one case with an example can break a nearby one.
- The quota error (429) during my first evaluation run made it look like the parser was wrong. The log showed it had silently fallen back to keywords. Without logging I would have "fixed" the wrong thing.
- Grounding worked better than I expected: across the evaluation, every explanation passed the invented-song check on the first draft. The revise loop mostly mattered in the mismatch case, where the first draft didn't admit that no song fit.

## Collaboration with AI

I built this with Claude Code as my coding assistant in the terminal. I used it to plan the agent steps, write the first versions of the modules and tests, and debug the evaluation. I ran every command, read the outputs and decided what stayed.

- **Accepted:** keeping ranking in the Project 3 scorer and using Gemini only to parse and explain, with every parsed field validated against the catalog. It kept the system testable without a key, and the validation is what caught "k-pop" and out-of-range energy values.
- **Rejected / revised:** the first confidence formula it wrote only compared the top song's genre and mood with the request. My test for "sad but super high energy" got 0.58, which said "fairly sure" about a playlist with no sad, high-energy song. I had it count energy too and added the "no song fully matches" warning. I also didn't keep the Project 3 explicit *penalty* for clean requests: after seeing "Gym Hero" in a clean top 3, I changed it to a hard filter.
- **Gemini itself:** when asked for k-pop it quietly returned pop, which looks helpful but hides that the catalog can't do what was asked. I changed the prompt to report it and show a warning instead.

## Future improvements

1. A bigger catalog with several songs per genre, so confidence reflects real choice.
2. Mark which profile fields the user actually asked for vs. what the model inferred, and only warn about the asked ones.
3. Check explanation facts against the song data (energy, instrumentalness, explicit) instead of only titles.
4. Spanish support, since most people I'd show this to would ask in Spanish.
