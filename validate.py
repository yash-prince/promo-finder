"""Deterministic checks on what the LLM proposed. LLMs are unreliable with exact numbers, so code owns them:

  * every start/end must match a REAL line boundary in the transcript (otherwise it was invented -> rejected)
  * clips are snapped to those boundaries, so a promo never cuts a line of dialogue in half
  * total length must be 20-60 s (auto-trimmed / extended where possible, otherwise rejected)
  * segments must be in order and not overlap
  * near-duplicate promos (same moment found twice) are removed
"""
from __future__ import annotations

from models import Candidate, Episode, Segment
from parser import to_seconds

MIN_LEN, MAX_LEN = 20.0, 60.0
SNAP_TOLERANCE = 2.0          # seconds: how far an LLM timestamp may be from a real boundary
TARGET_MAX = 58.0             # when trimming, aim a little under the limit


def _t(x) -> float:
    return float(x) if isinstance(x, (int, float)) else to_seconds(str(x))


def _content(ep: Episode):
    return [b for b in ep.beats if b.kind != "CAMERA"]


def _nearest(values: list[float], target: float):
    best = min(values, key=lambda v: abs(v - target))
    return best if abs(best - target) <= SNAP_TOLERANCE else None


def validate(raw: dict, ep: Episode, cand_id: str) -> tuple[Candidate | None, str]:
    """Returns (candidate, '') if usable, else (None, reason)."""
    beats = _content(ep)
    starts = sorted({b.start for b in beats})
    ends = sorted({b.end for b in beats})
    notes: list[str] = []
    segs: list[Segment] = []
    for s in raw.get("segments", []):
        try:
            rs, re_ = _t(s["start"]), _t(s["end"])
        except Exception:
            return None, "unreadable timestamp"
        ss, ee = _nearest(starts, rs), _nearest(ends, re_)
        if ss is None or ee is None:
            return None, f"timestamp not found in transcript ({s['start']}-{s['end']})"
        if ee <= ss:
            return None, "end before start"
        if abs(ss - rs) > 0.5 or abs(ee - re_) > 0.5:
            notes.append("timestamps snapped to line boundaries")
        segs.append(Segment(episode=ep.number, start=ss, end=ee))
    if not segs:
        return None, "no segments"
    segs.sort(key=lambda x: x.start)
    for a, b in zip(segs, segs[1:]):
        if b.start < a.end:
            return None, "segments overlap"

    total = sum(s.length for s in segs)
    if total > MAX_LEN:
        if len(segs) > 1:
            return None, f"multi-segment promo too long ({total:.0f}s)"
        later = [x for x in starts if x > segs[0].start and segs[0].end - x <= TARGET_MAX]
        if not later or segs[0].end - min(later) < MIN_LEN:
            return None, f"too long ({total:.0f}s) and cannot trim"
        segs[0].start = min(later)
        notes.append(f"auto-trimmed from {total:.0f}s (start moved later; hook line may differ from LLM's description)")
    elif total < MIN_LEN:
        # earlier line starts that make the promo land between MIN_LEN+2 and TARGET_MAX seconds
        ok = [x for x in starts if x < segs[0].start and MIN_LEN + 2 <= total + (segs[0].start - x) <= TARGET_MAX]
        if not ok:
            return None, f"too short ({total:.0f}s) and cannot extend"
        segs[0].start = max(ok)   # smallest extension that reaches the minimum
        notes.append(f"auto-extended from {total:.0f}s (start moved earlier; hook line may differ from LLM's description)")

    return Candidate(
        id=cand_id, segments=segs, hook=raw.get("hook", ""), cliffhanger=raw.get("cliffhanger", ""),
        why=raw.get("why", ""), hook_score=float(raw.get("hook_score", 5)),
        cliffhanger_score=float(raw.get("cliffhanger_score", 5)),
        standalone_score=float(raw.get("standalone_score", 5)), notes=notes,
    ), ""


def dedupe(cands: list[Candidate]) -> tuple[list[Candidate], int]:
    """Drop a candidate if >50% of it overlaps a better candidate from the same episode."""
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda c: -c.self_score):
        dup = False
        for k in kept:
            for a in c.segments:
                for b in k.segments:
                    if a.episode == b.episode:
                        ov = min(a.end, b.end) - max(a.start, b.start)
                        if ov > 0.5 * min(a.length, b.length):
                            dup = True
        if not dup:
            kept.append(c)
    return kept, len(cands) - len(kept)
