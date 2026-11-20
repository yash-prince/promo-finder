"""Step 5: rank all valid candidates for the whole show with ONE LLM call.

The ranker is shown the real opening line and real final line of each clip (taken from the screenplay by code),
not just the finder's own description, so it can't be fooled by an over-optimistic self-description.
"""
from __future__ import annotations

import json

import llm
from models import Candidate, Ranked, Episode
from parser import clip_text, fmt
from prompts import RANKER_SYSTEM

POOL = 40   # only the best-looking candidates go to the ranker (keeps the prompt small)


def first_last(c: Candidate, eps: dict[int, Episode]) -> tuple[str, str]:
    lines_first = clip_text(eps[c.segments[0].episode], c.segments[0].start, c.segments[0].end).splitlines()
    lines_last = clip_text(eps[c.segments[-1].episode], c.segments[-1].start, c.segments[-1].end).splitlines()
    return (lines_first[0] if lines_first else ""), (lines_last[-1] if lines_last else "")


def rank(cands: list[Candidate], eps: dict[int, Episode], model: str, rpm: int, mock: bool) -> list[Ranked]:
    pool = sorted(cands, key=lambda c: -c.self_score)[:POOL]
    scores: dict[str, tuple[float, str]] = {}
    if not mock:
        items = []
        for c in pool:
            first, last = first_last(c, eps)
            items.append({"id": c.id, "episode": c.segments[0].episode, "duration_s": round(c.duration),
                          "opening_line": first, "final_line": last, "hook": c.hook, "cliffhanger": c.cliffhanger,
                          "self_scores": [c.hook_score, c.cliffhanger_score, c.standalone_score]})
        data = llm.ask_json(RANKER_SYSTEM, json.dumps(items, ensure_ascii=False), model, rpm)
        for r in data.get("ranking", []):
            scores[str(r.get("id"))] = (float(r.get("score", 0)), r.get("reason", ""))

    # LLM order first (by its score); anything it skipped falls back to the finder's own score
    def key(c: Candidate):
        if c.id in scores:
            return (1, scores[c.id][0])
        return (0, c.self_score * 10)
    ordered = sorted(pool, key=key, reverse=True)
    return [Ranked(candidate=c, rank=i, score=scores.get(c.id, (c.self_score * 10, ""))[0],
                   reason=scores.get(c.id, (0, "ranked by finder self-score only"))[1])
            for i, c in enumerate(ordered, 1)]
