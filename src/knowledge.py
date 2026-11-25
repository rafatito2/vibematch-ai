"""Second retrieval source: listening notes per genre from data/genre_notes.md."""

from typing import Dict, List


def load_genre_notes(path: str = "data/genre_notes.md") -> Dict[str, str]:
    """Reads the notes file and returns {genre: note text}, one entry per '## genre' section."""
    notes: Dict[str, str] = {}
    current = None
    lines: List[str] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("## "):
                if current:
                    notes[current] = " ".join(lines).strip()
                current = line[3:].strip().lower()
                lines = []
            elif current and line.strip():
                lines.append(line.strip())
    if current:
        notes[current] = " ".join(lines).strip()
    return notes


def notes_for_songs(songs: List[Dict], notes: Dict[str, str]) -> Dict[str, str]:
    """Returns the notes for each distinct genre in the picked songs, in pick order."""
    selected: Dict[str, str] = {}
    for song in songs:
        genre = song["genre"].lower()
        if genre in notes and genre not in selected:
            selected[genre] = notes[genre]
    return selected
