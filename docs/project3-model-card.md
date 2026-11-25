# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name

**VibeMatch 1.0**

---

## 2. Intended Use

VibeMatch suggests the top 5 songs from a small catalog for a listener who states a favorite genre, a favorite mood and a target energy level. It is a classroom simulation for learning how content-based recommenders work.

It assumes the user can describe their taste in a few fixed fields and that the taste does not change.

**Not intended for:** real listeners, real catalogs, or any decision about which artists get exposure. It has no listening history, and its weights were picked by hand.

---

## 3. How the Model Works

Every song gets points for how well it fits the listener:

- Same genre as the listener's favorite: 2 points.
- Same mood: 1 point.
- Energy: up to 1.5 points. The closer the song's energy is to what the listener asked for, the more it earns. A louder song is not automatically better.
- Acoustic or not: up to 0.5 points, only if the listener said they care.

Listeners can also ask for extras: a favorite decade, mood tags such as "nostalgic", popular songs or hidden gems, instrumental music, and no explicit songs (explicit songs lose 2 points).

After every song has a score, the list is sorted from highest to lowest and the top 5 are shown with the reasons for each score.

Changes from the starter: the starter returned the first songs in the file with a placeholder explanation. I wrote the scoring, the ranking, the explanations, three alternative ranking modes, and a diversity option.

---

## 4. Data

- 20 songs in `data/songs.csv`: the 10 from the starter plus 10 I added.
- 17 genres. Lofi has 3 songs, pop has 2, and the other 15 have 1 each.
- 15 moods. Chill has 3 songs; happy, intense and relaxed have 2 each.
- 15 columns per song. I added `popularity`, `release_decade`, `mood_tags`, `instrumentalness` and `explicit`.
- All songs are made up. The numbers were assigned by hand, not measured from audio.
- Missing: lyrics, language, listening history, skips, and most of the world's genres.

---

## 5. Strengths

- Listeners whose taste fits one label get sensible results. Chill Lofi returns three lofi tracks, then ambient and jazz, which is what I would expect.
- Energy closeness works. A listener asking for 0.35 is never pushed toward loud songs.
- Every recommendation can be explained. The reasons column shows exactly where the points came from, so a wrong result is easy to trace.

---

## 6. Limitations and Bias

The biggest weakness I found is that genre and mood together (3.0 points) always beat energy (1.5 points at most). For the "Sad but Hyper" profile, a listener asking for energy 0.95 gets a slow blues song with energy 0.33 as the top pick, because it is the only blues song in the catalog. The catalog itself is also uneven: lofi listeners have three real matches and every other genre has one or two, so most users see one good result followed by songs chosen on energy alone. Labels are matched as exact text, so "indie pop" earns nothing for a "pop" fan, and a genre that is not in the catalog ("k-pop") fails without telling the user. This is how a filter bubble starts in a simple system: the label the user typed decides almost everything, and nearby music never gets a chance.

The diversity option helps with one part of this. When it is on, a song loses 1.5 points for each song by the same artist already in the list and 0.75 for each song in the same genre. That keeps one artist or genre from filling the whole list and gives songs from other genres a slot they would never win on score alone. It is fairer to the smaller artists in the catalog, but it cannot fix the missing data.

---

## 7. Evaluation

I ran seven profiles and read the top 5 for each. The full output is in the [README](README.md#profile-runs).

| Pair | What changed and why |
| --- | --- |
| High-Energy Pop vs Chill Lofi | No songs in common. Pop wants energy near 0.85; lofi wants 0.35 and acoustic sound. |
| High-Energy Pop vs Deep Intense Rock | Three songs in common (Gym Hero, Sunrise City, Storm Runner) because both want high energy. The order differs because genre and mood points go to different songs. |
| Chill Lofi vs Deep Intense Rock | Nothing in common. They sit at opposite ends of the energy scale. |
| Chill Lofi vs Focus Session | Same genre, but the "focused" mood and the mellow/steady tags move Focus Flow from third to first. |
| High-Energy Pop vs Clean Workout | Gym Hero matches the workout profile best, but the explicit penalty drops it below Sunrise City. |
| Sad but Hyper vs Deep Intense Rock | Both ask for energy 0.95. Rock gets a loud top pick; the blues fan gets a quiet one because the label wins. |
| Ghost Genre vs High-Energy Pop | With no genre match possible, the list is decided by mood and energy only and the top score falls from 4.46 to 2.11. |

**Why Gym Hero shows up for Happy Pop:** it is tagged pop, and a genre match is worth 2 points while a mood match is worth 1. So an intense pop song (3.38) outranks Rooftop Lights (2.37), which is actually happy but is labeled "indie pop". The system trusts the genre label more than the mood.

**Experiment:** I doubled the energy weight and halved genre. The order of the top 5 stayed the same, but Rooftop Lights closed to 0.03 points behind Gym Hero, and songs with no label match nearly doubled their scores. It was different, not clearly more accurate.

**What surprised me:** the weight shift changed the scores a lot and the order not at all. With 20 songs there are not enough close competitors for weights to reorder much.

I also wrote 15 pytest tests that check the scoring rules, the sort order, the modes and the diversity penalty.

---

## 8. Future Work

- Treat related genres as partial matches ("indie pop" and "pop") instead of exact text.
- Warn the user when their genre or mood does not exist in the catalog.
- Scale the genre weight down when the energy gap is very large, so "Sad but Hyper" gets a better answer.
- Learn the profile from likes and skips instead of typing it by hand.

---

## 9. Personal Reflection

My biggest learning moment was the "Sad but Hyper" profile. I had written the weights myself and they looked reasonable, and the system still recommended a slow song to someone asking for high energy. The rule was working exactly as written. The problem was a combination of preferences I had not thought about when I chose 2.0 and 1.5.

AI tools helped most with the repetitive parts: generating extra songs in CSV format, suggesting the Strategy pattern for the ranking modes, and formatting the table. I had to double-check the output every time. The starter import in `main.py` did not work with `python -m src.main`, the table printed 1.50 as 1.5 until I turned off number parsing, and the linter caught a loop variable that shadowed an import. I also checked the scores by hand for a few songs to make sure the reasons added up to the total.

What surprised me is how much a few additions and a sort can feel like a recommendation. The Chill Lofi list looks like something a real app would show, and there is no learning in it at all. That makes me read "recommended for you" differently: it may be a label match and a number.

Next I would add listening history, even a fake one, to see how collaborative filtering changes the results for the profiles that fail here.
