from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import SourceSnippet

TaskStatus = Literal[
    "queued", "running", "needs_input", "completed", "failed", "cancelled", "limit_reached"
]


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    goal: str = Field(min_length=3, max_length=4000)
    completion_criteria: str = Field(min_length=3, max_length=2000)
    context: str = Field(default="", max_length=16000)
    bot_id: str | None = Field(default=None, min_length=1, max_length=64)


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=8000)


class Artifact(BaseModel):
    id: str
    title: str
    content: str
    sha256: str


class TaskEvent(BaseModel):
    kind: str
    detail: str
    at: datetime


class TaskSummary(BaseModel):
    id: str
    goal: str
    completion_criteria: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    turns: int
    tokens: int
    max_turns: int
    max_tokens: int
    summary: str
    exception: str


class TaskView(TaskSummary):
    bot_id: str | None = None
    memory_ids: list[str] = Field(default_factory=list)
    context: str
    artifacts: list[Artifact]
    sources: list[SourceSnippet]
    events: list[TaskEvent]
