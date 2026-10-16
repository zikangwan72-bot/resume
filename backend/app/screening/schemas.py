from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScreeningJobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    rejection_conditions: list[str] = Field(default_factory=list)
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    status: Literal["active", "inactive"] = "active"


class ScreeningJobUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    rejection_conditions: list[str] | None = None
    scoring_weights: dict[str, float] | None = None
    status: Literal["active", "inactive"] | None = None


class ScreeningTagSuggestionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5000)
    required_skills: list[str] = Field(default_factory=list, max_length=30)


class ScreeningJobResponse(ScreeningJobCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class ReviewUpdate(BaseModel):
    human_status: Literal["pending_review", "approved", "rejected", "needs_follow_up"]
    review_note: str | None = Field(default=None, max_length=5000)
