from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class RecommendationFilters(BaseModel):
    start_date: date | None = None
    end_date: date | None = None


class Recommendation(BaseModel):
    code: str
    title: str
    priority: Literal["high", "medium", "low"]
    rationale: str
    affected_count: int = Field(ge=0)
    affected_users: list[str] = Field(default_factory=list)
    evidence: dict[str, int | float | str] = Field(default_factory=dict)


class RecommendationReport(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    data_available: bool
    recommendations: list[Recommendation]
    source_limitations: list[str] = Field(default_factory=list)
