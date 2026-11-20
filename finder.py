"""Step 3: ask the LLM for promo candidates, one call per episode (parallel), then validate them with code."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import llm
from models import Candidate, Episode
from parser import compact, fmt
from prompts import FINDER_SYSTEM, finder_user
from validate import dedupe, validate


def build_summaries(episodes: list[Episode]) -> str:
    return "\n".join(f"Ep {e.number}: {e.logline or '(no summary)'}" for e in episodes)


def _mock_candidates(ep: Episode) -> list[dict]:
    """Offline stand-in for the LLM (for testing the plumbing only): the last ~40s of an episode
    (microdrama episodes tend to end on a cliffhanger) and the line-dense window with most '!' and '?'."""
    beats = [b for b in ep.beats if b.kind != "CAMERA"]
    if not beats:
        return []
    end = beats[-1].end
    out = [{"segments": [{"start": fmt(max(0, end - 40)), "end": fmt(end)}], "hook": "mock", "cliffhanger": "mock",
            "why": "mock: episode ending", "hook_score": 6, "cliffhanger_score": 7, "standalone_score": 5}]
    best = max(beats, key=lambda b: b.text.count("!") + b.text.count("?"))
    out.append({"segments": [{"start": fmt(best.start), "end": fmt(best.start + 35)}], "hook": "mock", "cliffhanger": "mock",
                "why": "mock: emotional peak", "hook_score": 5, "cliffhanger_score": 5, "standalone_score": 5})
    return out


def find_all(episodes: list[Episode], model: str, workers: int, rpm: int, mock: bool, batch_size: int = 5, api_key: str | None = None):
    summaries = build_summaries(episodes)
    by_num = {e.number: e for e in episodes}

    def one(batch: list[Episode]):
        if mock:
            return [(ep, _mock_candidates(ep)) for ep in batch]
        sep = chr(10) * 2
        text = sep.join(f"=== EPISODE {e.number} (length {e.duration:.0f}s) ==={chr(10)}{compact(e)}" for e in batch)
        data = llm.ask_json(FINDER_SYSTEM, finder_user(summaries, text), model, rpm, api_key=api_key)
        grouped: dict[int, list] = {e.number: [] for e in batch}
        for c in data.get("candidates", []):
            try:
                if int(c.get("episode")) in grouped:
                    grouped[int(c["episode"])].append(c)
            except (TypeError, ValueError):
                pass
        return [(e, grouped[e.number]) for e in batch]

    batches = [episodes[i:i + batch_size] for i in range(0, len(episodes), batch_size)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = [r for part in pool.map(one, batches) for r in part]

    valid: list[Candidate] = []
    log = {"episodes": len(episodes), "raw_candidates": 0, "rejected": [], "auto_adjusted": 0, "duplicates_removed": 0}
    for ep, raw in results:
        per_ep: list[Candidate] = []
        for k, r in enumerate(raw, 1):
            log["raw_candidates"] += 1
            cand, why = validate(r, by_num[ep.number], f"E{ep.number:02d}-{k}")
            if cand is None:
                log["rejected"].append({"id": f"E{ep.number:02d}-{k}", "reason": why})
            else:
                per_ep.append(cand)
                log["auto_adjusted"] += any("auto-" in n for n in cand.notes)
        per_ep, removed = dedupe(per_ep)
        log["duplicates_removed"] += removed
        valid += per_ep
    log["valid"] = len(valid)
    return valid, log
