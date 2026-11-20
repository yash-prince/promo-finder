"""Reads Kuku-style screenplay files and turns them into Episode objects (pure code, no LLM).

Entry layout we parse:
    **ACTION:**                      or   **LADY JULIANA (Confused, Breathless):**
    Start: (00:13.50) | End: (00:14.30)
    text...
Any folder of such files works (any show, any number of episodes).
"""
from __future__ import annotations

import re
from pathlib import Path

from models import Beat, Episode

ENTRY_RE = re.compile(r"^\*\*(?P<label>[^*]+?):\*\*\s*$")
TIME_RE = re.compile(r"Start:\s*\((?P<s>[\d:.]+)\)\s*\|\s*End:\s*\((?P<e>[\d:.]+)\)")
SCENE_RE = re.compile(r"^Scene heading:\s*(?P<h>.+)$")


def to_seconds(ts: str) -> float:
    """'01:13.50' -> 73.5 ; also accepts HH:MM:SS."""
    parts = [float(p) for p in ts.split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def fmt(sec: float) -> str:
    """73.5 -> '01:13.5'"""
    m, s = divmod(round(sec, 1), 60)
    return f"{int(m):02d}:{s:04.1f}"


def _kind(label: str) -> tuple[str, str]:
    up = label.upper()
    if up.startswith("CAMERA"):
        return "CAMERA", ""
    if up.startswith("ACTION"):
        return "ACTION", ""
    if up.startswith("SOUND"):
        return "SOUND", ""
    return "DIALOGUE", label.strip()      # speaker name + (emotion)


def parse_episode(path: Path, fallback_number: int) -> Episode:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    ep = Episode(number=fallback_number, path=str(path))
    m = re.search(r"EPISODE NUMBER:\s*(?:Episode\s*)?(\d+)", "\n".join(lines[:5]), re.I)
    if m:
        ep.number = int(m.group(1))
    for ln in lines[:10]:
        if ln.startswith("EPISODE LOGLINE:"):
            ep.logline = ln.split(":", 1)[1].strip()
        elif ln.startswith("CONTINUITY NOTES:"):
            ep.continuity = ln.split(":", 1)[1].strip()

    i = 0
    scene = ""
    while i < len(lines):
        sm = SCENE_RE.match(lines[i].strip())
        if sm:
            scene = sm.group("h")
        em = ENTRY_RE.match(lines[i].strip())
        if em and i + 1 < len(lines):
            tm = TIME_RE.search(lines[i + 1])
            if tm:
                kind, speaker = _kind(em.group("label"))
                j = i + 2
                text: list[str] = []
                while j < len(lines) and lines[j].strip() and not ENTRY_RE.match(lines[j].strip()):
                    text.append(lines[j].strip())
                    j += 1
                ep.beats.append(Beat(start=to_seconds(tm.group("s")), end=to_seconds(tm.group("e")),
                                     kind=kind, speaker=speaker, text=" ".join(text).strip('" ')))
                i = j
                continue
        i += 1
    ep.beats.sort(key=lambda b: (b.start, b.end))
    return ep


def load_folder(folder: str, limit: int | None = None) -> list[Episode]:
    files = sorted(Path(folder).glob("*.txt"))
    if not files:
        raise SystemExit(f"No .txt episode files found in {folder}")
    eps = [parse_episode(f, n + 1) for n, f in enumerate(files)]
    eps.sort(key=lambda e: e.number)
    return eps[:limit] if limit else eps


def compact(ep: Episode) -> str:
    """Token-light transcript for the LLM. Camera directions are dropped (noise for story judgement)."""
    out = []
    for b in ep.beats:
        if b.kind == "CAMERA":
            continue
        tag = f"{b.speaker}: " if b.kind == "DIALOGUE" else f"({b.kind.lower()}) "
        txt = f'"{b.text}"' if b.kind == "DIALOGUE" else b.text
        out.append(f"[{fmt(b.start)}-{fmt(b.end)}] {tag}{txt}")
    return "\n".join(out)


def clip_text(ep: Episode, start: float, end: float) -> str:
    """Transcript of just the content inside [start, end] — what a promo viewer would actually see."""
    out = []
    for b in ep.beats:
        if b.kind == "CAMERA" or b.start < start - 0.01 or b.end > end + 0.01:
            continue
        tag = f"{b.speaker}: " if b.kind == "DIALOGUE" else f"({b.kind.lower()}) "
        out.append(f"{tag}{b.text}")
    return "\n".join(out)
