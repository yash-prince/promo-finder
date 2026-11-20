"""Step 7: quality check. An INDEPENDENT 'new viewer' judge sees only the clip text (no show context, no finder scores).

If the judge often disagrees with the finder/ranker, the picks are not trustworthy -> the report says so.
We judge the top-K and a sample from the bottom of the ranked list, to check the ranking really separates good from weak.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import llm
from models import Episode, Ranked
from parser import clip_text
from prompts import JUDGE_SYSTEM


def judge(ranked: list[Ranked], eps: dict[int, Episode], model: str, rpm: int, top_k: int = 10, bottom_k: int = 5):
    sample = ranked[:top_k] + ranked[-bottom_k:] if len(ranked) > top_k + bottom_k else ranked

    clips = []
    for r in sample:
        nl = chr(10)
        text = f"{nl}---(cut to next moment)---{nl}".join(
            clip_text(eps[s.episode], s.start, s.end) for s in r.candidate.segments)
        clips.append(f"##### CLIP id={r.candidate.id}{nl}{text}")
    data = llm.ask_json(JUDGE_SYSTEM, (chr(10) * 2).join(clips), model, rpm, temperature=0.0)   # one call for all clips
    by_id = {str(j.get("id")): j for j in data.get("judgements", [])}
    for r in sample:
        r.judge = by_id.get(r.candidate.id)

    def avg(rs, k):
        vals = [float(r.judge.get(k, 0)) for r in rs if r.judge]
        return round(sum(vals) / len(vals), 1) if vals else None

    top, bottom = ranked[:top_k], ranked[-bottom_k:]
    stats = {
        "judged": len([r for r in ranked if r.judge]),
        "top_k_avg": {k: avg(top, k) for k in ("hook", "cliffhanger", "standalone")},
        "bottom_k_avg": {k: avg(bottom, k) for k in ("hook", "cliffhanger", "standalone")},
        "top_k_would_post": sum(bool(r.judge and r.judge.get("would_post")) for r in top),
        "bottom_k_would_post": sum(bool(r.judge and r.judge.get("would_post")) for r in bottom),
        "top_k": top_k, "bottom_k": bottom_k,
        "finder_vs_judge_hook_gap": round(sum(abs(r.candidate.hook_score - float(r.judge.get("hook", 0)))
                                              for r in sample if r.judge) / max(1, len([r for r in sample if r.judge])), 1),
    }
    return stats
