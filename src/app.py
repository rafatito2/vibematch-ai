"""
VibeMatch AI command line app.

    python -m src.app "something chill to study to"
    python -m src.app "hype songs for the gym" --trace     # also print every agent step
    python -m src.app "rainy day music" --offline          # no API key: keyword parser + template

With no request argument it asks for one interactively.
"""

import argparse
import json

from dotenv import load_dotenv
from tabulate import tabulate

from src.agent import VibeMatchAgent, setup_logging
from src.llm import GeminiClient, LLMError


def make_llm(offline: bool):
    """Returns a Gemini client, or None (offline mode) if asked or if the key is missing."""
    if offline:
        return None
    try:
        return GeminiClient()
    except LLMError as exc:
        print(f"[warning] {exc} Running offline.")
        return None


def print_result(result: dict, show_trace: bool) -> None:
    """Prints the picks table, the explanation, confidence and any warnings."""
    print(f"\nRequest: {result['request']}")
    if result["status"] != "ok":
        print(f"VibeMatch: {result['message']}")
    else:
        print(f"Profile: {result['prefs']}")
        for note in result.get("parse_notes", []):
            print(f"[guardrail] {note}")
        rows = [[rank, song["title"], song["artist"], song["genre"], song["mood"], f"{score:.2f}"]
                for rank, (song, score, _) in enumerate(result["results"], start=1)]
        print(tabulate(rows, headers=["#", "Title", "Artist", "Genre", "Mood", "Score"], tablefmt="github"))
        print(f"\nWhy these ({result['explained_by']}):\n{result['explanation']}")
        print(f"\nConfidence: {result['confidence']:.2f}")
        for warning in result["warnings"]:
            print(f"[warning] {warning}")
    if show_trace:
        print("\nTrace:")
        for item in result["trace"]:
            print("  " + json.dumps(item, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="VibeMatch AI: music recommendations from a plain-language request")
    parser.add_argument("request", nargs="?", help="what you want to listen to")
    parser.add_argument("-k", type=int, default=3, help="how many songs to recommend")
    parser.add_argument("--offline", action="store_true", help="skip Gemini and use the keyword parser")
    parser.add_argument("--trace", action="store_true", help="print the agent's step trace")
    args = parser.parse_args()

    load_dotenv()
    setup_logging()
    agent = VibeMatchAgent(llm=make_llm(args.offline), k=args.k)
    request = args.request if args.request is not None else input("What do you want to listen to? ")
    print_result(agent.run(request), args.trace)


if __name__ == "__main__":
    main()
