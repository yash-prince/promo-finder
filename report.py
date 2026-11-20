"""Step 6: write the outputs an editor can use: report.md (readable), promos.csv (sheet), promos.json (machine)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from models import Episode, Ranked
from parser import clip_text, fmt


def _segs(r: Ranked) -> str:
    return " + ".join(f"Ep{s.episode} {fmt(s.start)}-{fmt(s.end)}" for s in r.candidate.segments)


def write_all(out: Path, ranked: list[Ranked], eps: dict[int, Episode], log: dict, eval_stats: dict | None,
              model: str, top_n: int) -> None:
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for r in ranked:
        c = r.candidate
        rows.append({"rank": r.rank, "id": c.id, "score": r.score, "duration_s": round(c.duration, 1),
                     "segments": [s.model_dump() for s in c.segments], "hook": c.hook, "cliffhanger": c.cliffhanger,
                     "why_it_works": c.why, "ranking_reason": r.reason, "notes": c.notes, "judge": r.judge})
    (out / "promos.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with open(out / "promos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "episode(s)", "segments (start-end)", "duration_s", "hook", "cliffhanger",
                    "why_it_works", "ranking_reason", "flags"])
        for r in ranked:
            c = r.candidate
            w.writerow([r.rank, ",".join(str(s.episode) for s in c.segments), _segs(r), round(c.duration, 1),
                        c.hook, c.cliffhanger, c.why, r.reason, "; ".join(c.notes)])

    md = [f"# Promo report\n", f"Model: `{model}` · episodes: {log['episodes']} · "
          f"raw candidates: {log['raw_candidates']} · valid after checks: {log['valid']} · ranked: {len(ranked)}\n",
          f"## Top {min(top_n, len(ranked))} promos (post in this order)\n"]
    for r in ranked[:top_n]:
        c = r.candidate
        md.append(f"### #{r.rank} — {_segs(r)}  ({c.duration:.0f}s)")
        md.append(f"- **Hook:** {c.hook}\n- **Cliffhanger:** {c.cliffhanger}\n- **Why it works:** {c.why}")
        md.append(f"- **Why this rank:** {r.reason}")
        if c.notes:
            md.append(f"- ⚠ **Flags:** {'; '.join(sorted(set(c.notes)))}")
        if r.judge:
            j = r.judge
            md.append(f"- **Independent judge (sees only the clip):** hook {j.get('hook')}/10, cliffhanger "
                      f"{j.get('cliffhanger')}/10, standalone {j.get('standalone')}/10, would post: "
                      f"{j.get('would_post')}; main problem: {j.get('problem')}")
        first = clip_text(eps[c.segments[0].episode], c.segments[0].start, c.segments[0].end).splitlines()
        last = clip_text(eps[c.segments[-1].episode], c.segments[-1].start, c.segments[-1].end).splitlines()
        md.append(f"- **Clip opens:** {first[0] if first else ''}\n- **Clip ends:** {last[-1] if last else ''}\n")

    md.append("## Pipeline checks (code)\n")
    md.append(f"- Rejected by validator: {len(log['rejected'])} (invented timestamps, bad length, overlaps)")
    md.append(f"- Auto-trimmed/extended to fit 20-60s: {log['auto_adjusted']} (flagged with ⚠ above)")
    md.append(f"- Near-duplicates removed: {log['duplicates_removed']}")
    for rj in log["rejected"][:15]:
        md.append(f"  - {rj['id']}: {rj['reason']}")
    if eval_stats:
        md.append("\n## Independent judge: does the ranking separate good from weak?\n")
        md.append(f"```json\n{json.dumps(eval_stats, indent=2)}\n```")
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")
    (out / "pipeline_log.json").write_text(json.dumps({**log, "evaluation": eval_stats}, indent=2), encoding="utf-8")
