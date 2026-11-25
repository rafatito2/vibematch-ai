"""
Evaluation harness: runs the agent on the fixed cases in data/eval_cases.json and prints pass/fail.

    python -m src.evaluate              # few-shot parser (the real system)
    python -m src.evaluate --compare    # also run the plain zero-shot prompt and compare
    python -m src.evaluate --offline    # keyword parser only, no API key needed

Each case states what a correct answer must satisfy (status, allowed genres or moods for the
top pick, energy range, no explicit songs, a warning shown). A case passes only if all hold.
"""

import argparse
import json
import time
from typing import Dict, List

from dotenv import load_dotenv
from tabulate import tabulate

from src.agent import VibeMatchAgent, setup_logging
from src.app import make_llm


def judge(case: Dict, result: Dict) -> List[str]:
    """Returns the list of failed checks for one case (empty means pass)."""
    fails = []
    if result["status"] != case["status"]:
        return [f"status {result['status']} (expected {case['status']})"]
    if case["status"] != "ok":
        return fails
    top = result["results"][0][0]
    if "top_genres" in case and top["genre"] not in case["top_genres"]:
        fails.append(f"top genre {top['genre']}")
    if "top_moods" in case and top["mood"] not in case["top_moods"]:
        fails.append(f"top mood {top['mood']}")
    if "energy_min" in case and top["energy"] < case["energy_min"]:
        fails.append(f"top energy {top['energy']} < {case['energy_min']}")
    if "energy_max" in case and top["energy"] > case["energy_max"]:
        fails.append(f"top energy {top['energy']} > {case['energy_max']}")
    if case.get("no_explicit") and any(song.get("explicit") for song, _, _ in result["results"]):
        fails.append("explicit song recommended")
    if case.get("must_warn") and not (result["warnings"] or result.get("parse_notes")):
        fails.append("no warning shown")
    return fails


def run(agent: VibeMatchAgent, cases: List[Dict], delay: float = 0.0) -> Dict:
    """Runs every case and returns the rows for the table plus summary numbers."""
    rows, passed, confidences, first_try, fallbacks = [], 0, [], 0, 0
    for case in cases:
        result = agent.run(case["request"])
        time.sleep(delay)  # the free Gemini tier allows only a few calls per minute
        fails = judge(case, result)
        passed += not fails
        top = "-"
        if result["status"] == "ok":
            song = result["results"][0][0]
            top = f"{song['title']} ({song['genre']}, {song['energy']:.2f})"
            confidences.append(result["confidence"])
            first_try += result["explained_by"] == "model"
            fallbacks += result["explained_by"] == "template"
        rows.append([case["request"][:45], result["status"], top,
                     f"{result.get('confidence', 0):.2f}" if result["status"] == "ok" else "-",
                     "PASS" if not fails else "FAIL: " + "; ".join(fails)])
    answered = len(confidences)
    return {
        "rows": rows, "passed": passed, "total": len(cases),
        "avg_confidence": sum(confidences) / answered if answered else 0.0,
        "first_try": first_try, "fallbacks": fallbacks, "answered": answered,
    }


def print_report(label: str, report: Dict) -> None:
    """Prints the per-case table and a one-line summary."""
    print(f"\n=== {label} ===")
    print(tabulate(report["rows"], headers=["Request", "Status", "Top pick", "Conf", "Result"],
                   tablefmt="github"))
    print(f"\nPassed {report['passed']}/{report['total']} | average confidence "
          f"{report['avg_confidence']:.2f} | explanations accepted on first draft "
          f"{report['first_try']}/{report['answered']} | template fallbacks {report['fallbacks']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate VibeMatch AI on predefined requests")
    parser.add_argument("--cases", default="data/eval_cases.json")
    parser.add_argument("--offline", action="store_true", help="keyword parser only")
    parser.add_argument("--compare", action="store_true", help="also run the zero-shot baseline prompt")
    parser.add_argument("--delay", type=float, default=6.0, help="seconds to wait between cases when online")
    args = parser.parse_args()

    load_dotenv()
    setup_logging()
    with open(args.cases, encoding="utf-8") as handle:
        cases = json.load(handle)
    llm = make_llm(args.offline)

    label = "offline keyword parser" if llm is None else "few-shot parser (default)"
    delay = 0.0 if llm is None else args.delay
    print_report(label, run(VibeMatchAgent(llm=llm), cases, delay))
    if args.compare and llm is not None:
        print_report("zero-shot baseline parser", run(VibeMatchAgent(llm=llm, few_shot=False), cases, delay))
    if llm is not None:
        print(f"\nModel calls made: {llm.calls} (includes retries)")


if __name__ == "__main__":
    main()
