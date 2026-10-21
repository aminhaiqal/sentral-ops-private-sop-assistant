from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


SkillId = Literal["research", "analyze", "save", "draft"]
ToolId = Literal["brave_search", "llm", "database"]
SEQUENCE: tuple[SkillId, ...] = ("research", "analyze", "save", "draft")


class LeadTarget(Schema):
    industry: str = Field(min_length=2, max_length=160)
    location: str = Field(min_length=2, max_length=160)
    qualification_criteria: str = Field(min_length=5, max_length=2000)
    offering: str = Field(min_length=5, max_length=1200)
    max_prospects: int = Field(default=5, ge=1, le=8)
    minimum_score: int = Field(default=70, ge=0, le=100)


class ExpectedResults(Schema):
    description: str = Field(min_length=5, max_length=1200)
    minimum_qualified: int = Field(default=1, ge=0, le=8)


class BotConfig(Schema):
    template_id: Literal["lead_research_v1"] = "lead_research_v1"
    name: str = Field(min_length=1, max_length=80)
    objective: str = Field(min_length=10, max_length=2000)
    skills: list[SkillId] = Field(default_factory=lambda: list(SEQUENCE), max_length=4)
    tools: list[ToolId] = Field(
        default_factory=lambda: ["brave_search", "llm", "database"], max_length=3
    )
    trigger: Literal["manual"] = "manual"
    target: LeadTarget
    expected_results: ExpectedResults
    enabled: bool = True

    @model_validator(mode="after")
    def supported_template(self):
        if self.skills not in [list(SEQUENCE), list(SEQUENCE[:-1])]:
            raise ValueError(
                "Lead Research requires Research, Analyze and Save, followed by optional Draft. Other sequences are not supported."
            )
        if len(set(self.tools)) != len(self.tools):
            raise ValueError("Select each tool only once.")
        if self.expected_results.minimum_qualified > self.target.max_prospects:
            raise ValueError("The required prospect count cannot exceed the result limit.")
        return self


class RunRequest(Schema):
    idempotency_key: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class Candidate(Schema):
    id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=240)
    url: str = Field(min_length=8, max_length=2000)
    excerpt: str = Field(min_length=10, max_length=1200)


class ResearchInput(Schema):
    industry: str
    location: str
    limit: int = Field(ge=1, le=16)


class ResearchOutput(Schema):
    candidates: list[Candidate] = Field(max_length=16)
    queries: list[str] = Field(max_length=2)


class AnalyzeInput(Schema):
    objective: str
    criteria: str
    candidates: list[Candidate] = Field(max_length=16)
    minimum_score: int
    limit: int


class Assessment(Schema):
    candidate_id: str
    company_name: str = Field(min_length=1, max_length=160)
    qualified: bool
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=5, max_length=700)
    evidence_quote: str = Field(max_length=600)
    missing_information: list[str] = Field(max_length=5)


class Assessments(Schema):
    assessments: list[Assessment] = Field(max_length=16)


class Prospect(Schema):
    candidate_id: str
    company_name: str
    url: str
    score: int
    reason: str
    evidence_quote: str
    missing_information: list[str]
    source_title: str
    researched_at: str
    verification: Literal["search_source_matched"] = "search_source_matched"


class AnalyzeOutput(Schema):
    qualified: list[Prospect] = Field(max_length=8)
    assessments: list[Assessment] = Field(max_length=16)
    evaluated_count: int = Field(ge=0, le=16)
    rejected_count: int = Field(ge=0, le=16)
    duplicate_count: int = Field(ge=0, le=16)


class SaveInput(Schema):
    prospects: list[Prospect] = Field(max_length=8)


class SavedProspect(Prospect):
    id: str


class SaveOutput(Schema):
    prospects: list[SavedProspect] = Field(max_length=8)
    saved_count: int


class DraftInput(Schema):
    objective: str
    offering: str
    instructions: str
    prospects: list[SavedProspect] = Field(max_length=8)


class OutreachDraft(Schema):
    prospect_id: str
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=20, max_length=2200)


class DraftOutput(Schema):
    drafts: list[OutreachDraft] = Field(max_length=8)


class ApprovalRequest(Schema):
    id: str
    action: str
    status: Literal["pending", "approved", "rejected"]
    # No external write tools are registered in V1, so the runtime returns an empty list.


class RunError(Schema):
    code: str
    message: str
    retryable: bool


class ExecutionStep(Schema):
    skill_id: SkillId
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    attempts: int
    started_at: str | None
    completed_at: str | None
    input: dict | None
    output: dict | None
    error: RunError | None


class Usage(Schema):
    api_calls: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    charged_token_bound: int = 0
    unreported_llm_calls: int = 0
    estimated_cost_usd: float | None = None


class RunResult(Schema):
    summary: str
    qualified_count: int
    evaluated_count: int
    criteria_met: bool
    criteria_note: str
    prospects: list[SavedProspect]
    drafts: list[OutreachDraft]


RunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class RunSummary(Schema):
    id: str
    bot_id: str
    bot_name: str
    status: RunStatus
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str
    error: RunError | None
    usage: Usage
    result_count: int


class RunView(RunSummary):
    configuration: BotConfig
    steps: list[ExecutionStep]
    result: RunResult | None
    logs: list[dict]
    approvals: list[ApprovalRequest]
    limits: dict


class StudioBot(Schema):
    id: str
    configuration: BotConfig
    revision: int
    created_at: str
    updated_at: str
    last_run: RunSummary | None
