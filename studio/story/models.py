"""Pydantic models for the three handoff answers (one per task) with precise field errors for the answering session."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _M(BaseModel):
    model_config = ConfigDict(extra="allow")


class Fact(_M):
    id: str
    claim: str
    figure: float | int | str | None = None
    unit: str = ""
    year: int | str | None = None
    source_url: str = ""
    quote_snippet: str = ""
    is_estimate: bool


class HookVariant(_M):
    hook_type: str
    line: str
    why: str = ""
    score: dict[str, int] = Field(default_factory=dict)


class Beat(_M):
    n: int
    chapter: str
    seconds: float
    device: str
    key_fact: str = ""
    emotion: str = "neutral"
    purpose: str = ""
    fact_ids: list[str] = Field(default_factory=list)


class Loop(_M):
    id: str
    question: str
    plant: int
    payoff: int


class Ending(_M):
    callback: str
    takeaway: str
    cta_question: str
    next_video: str


class Outline(_M):
    audience_question: str
    big_idea: str
    promise: str
    title_promise: str
    arc: str | dict[str, Any]
    beats: list[Beat]
    loops: list[Loop]
    ending: Ending
    thumbnail_ideas: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class StoryPlan(_M):
    """Task 1 answer: facts + outline + 8 scored hook variants."""
    facts: list[Fact]
    outline: Outline
    hooks: list[HookVariant]


class SegmentModel(_M):
    chapter: str = ""
    narration: str
    visual_keywords: list[str] = Field(default_factory=list)
    est_seconds: float
    fact_ids: list[str] = Field(default_factory=list)


class ScriptModel(_M):
    """Task 2 answer (the script package); deeper rules stay in script.validate_package."""
    topic: str = ""
    titles: list[dict[str, Any]]
    segments: list[SegmentModel]
    sources: list[dict[str, Any]] = Field(default_factory=list)


class SwipePoint(_M):
    segment: int
    quote: str
    why: str
    fix: str


class StoryReview(_M):
    """Task 3 answer: rubric scores, swipe-away moments and the rewritten package."""
    scores: dict[str, int]
    verdict: str
    swipe_points: list[SwipePoint]
    fixes: list[str] = Field(default_factory=list)
    revised: dict[str, Any]


def model_problems(model: type[BaseModel], data: Any) -> list[str]:
    """Plain-language field errors, e.g. `outline.beats[2].seconds: Input should be a valid number`."""
    try:
        model.model_validate(data)
    except ValidationError as exc:
        out = []
        for e in exc.errors():
            loc = ".".join(f"[{p}]" if isinstance(p, int) else str(p) for p in e["loc"]).replace(".[", "[")
            what = "is missing" if e["type"] == "missing" else e["msg"]
            out.append(f"{loc or 'answer'}: {what} (expected {_expected(e)})")
        return out[:15]
    return []


def _expected(e: dict) -> str:
    t = e["type"]
    return {"missing": "a value", "int_parsing": "an integer", "float_parsing": "a number",
            "string_type": "a string", "bool_parsing": "true or false", "list_type": "a list",
            "dict_type": "an object"}.get(t, "see the JSON shape in the prompt")
