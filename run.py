"""CLI entry point.

  python run.py --input "<folder of episode .txt files>" --out output
  python run.py --input ... --model groq/llama-3.3-70b-versatile       # swap model
  python run.py --input ... --mock                                    # offline plumbing test (no API key)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import llm
from evaluate import judge
from finder import find_all
from parser import load_folder
from ranker import rank
from report import write_all


def main() -> None:
    ap = argparse.ArgumentParser(description="Find the best promo clips in a microdrama screenplay folder.")
    ap.add_argument("--input", required=True, help="folder with one .txt screenplay per episode")
    ap.add_argument("--out", default="output")
    ap.add_argument("--model", default=llm.DEFAULT_MODEL, help="any LiteLLM model string")
    ap.add_argument("--top", type=int, default=15, help="how many promos to show in report.md")
    ap.add_argument("--limit", type=int, default=None, help="only first N episodes (quick tests)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--batch", type=int, default=5, help="episodes per LLM call (fewer calls = cheaper)")
    ap.add_argument("--rpm", type=int, default=8, help="max LLM requests/minute (free tiers are low)")
    ap.add_argument("--no-judge", action="store_true", help="skip the independent quality check")
    ap.add_argument("--mock", action="store_true", help="no LLM: heuristic stand-in, for testing only")
    a = ap.parse_args()

    llm.load_env()
    episodes = load_folder(a.input, a.limit)
    eps = {e.number: e for e in episodes}
    print(f"[1/5] parsed {len(episodes)} episodes")

    cands, log = find_all(episodes, a.model, a.workers, a.rpm, a.mock, a.batch)
    print(f"[2/5] {log['raw_candidates']} raw candidates -> {log['valid']} valid "
          f"({len(log['rejected'])} rejected, {log['duplicates_removed']} duplicates)")

    ranked = rank(cands, eps, a.model, a.rpm, a.mock)
    print(f"[3/5] ranked {len(ranked)} promos")

    stats = None
    if not a.mock and not a.no_judge and ranked:
        stats = judge(ranked, eps, a.model, a.rpm)
        print(f"[4/5] independent judge: top would_post {stats['top_k_would_post']}/{stats['top_k']}, "
              f"bottom {stats['bottom_k_would_post']}/{stats['bottom_k']}")
    else:
        print("[4/5] judge skipped")

    write_all(Path(a.out), ranked, eps, log, stats, "mock" if a.mock else a.model, a.top)
    print(f"[5/5] wrote {a.out}/report.md, promos.csv, promos.json, pipeline_log.json")


if __name__ == "__main__":
    main()
