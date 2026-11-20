"""Data structures shared by every step of the pipeline."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class Beat(BaseModel):
    """One timed entry of the screenplay: a dialogue line, an action, a sound cue or a camera note."""
    start: float
    end: float
    kind: str            # DIALOGUE | ACTION | SOUND | CAMERA
    speaker: str = ""    # only for DIALOGUE
    text: str = ""


class Episode(BaseModel):
    number: int
    path: str
    logline: str = ""
    continuity: str = ""
    beats: list[Beat] = Field(default_factory=list)

    @property
    def duration(self) -> float:
        return max((b.end for b in self.beats), default=0.0)


class Segment(BaseModel):
    episode: int
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


class Candidate(BaseModel):
    """A possible promo. May be built from several segments (in playing order)."""
    id: str = ""
    segments: list[Segment]
    hook: str = ""
    cliffhanger: str = ""
    why: str = ""
    hook_score: float = 5
    cliffhanger_score: float = 5
    standalone_score: float = 5
    notes: list[str] = Field(default_factory=list)   # what validation changed / flagged

    @property
    def duration(self) -> float:
        return sum(s.length for s in self.segments)

    @property
    def self_score(self) -> float:
        return 0.4 * self.hook_score + 0.4 * self.cliffhanger_score + 0.2 * self.standalone_score


class Ranked(BaseModel):
    candidate: Candidate
    rank: int
    score: float
    reason: str = ""
    judge: Optional[dict] = None
