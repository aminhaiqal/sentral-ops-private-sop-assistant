export type SkillId = "research" | "analyze" | "save" | "draft";
export type ToolId = "brave_search" | "llm" | "database";
export type StudioConfig = {
  template_id: "lead_research_v1";
  name: string;
  objective: string;
  skills: SkillId[];
  tools: ToolId[];
  trigger: "manual";
  enabled: boolean;
  target: {
    industry: string;
    location: string;
    qualification_criteria: string;
    offering: string;
    max_prospects: number;
    minimum_score: number;
  };
  expected_results: { description: string; minimum_qualified: number };
};
export type StudioError = { code: string; message: string; retryable: boolean };
export type StudioRunSummary = {
  id: string;
  bot_id: string;
  bot_name: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  error: StudioError | null;
  result_count: number;
  usage: {
    api_calls: number;
    llm_calls: number;
    input_tokens: number;
    output_tokens: number;
    charged_token_bound: number;
    unreported_llm_calls: number;
    estimated_cost_usd: number | null;
  };
};
export type StudioBot = {
  id: string;
  configuration: StudioConfig;
  revision: number;
  created_at: string;
  updated_at: string;
  last_run: StudioRunSummary | null;
};
export type Prospect = {
  id: string;
  candidate_id: string;
  company_name: string;
  url: string;
  source_title: string;
  score: number;
  reason: string;
  evidence_quote: string;
  missing_information: string[];
  researched_at: string;
  verification: string;
};
export type OutreachDraft = { prospect_id: string; subject: string; body: string };
export type StudioRun = StudioRunSummary & {
  configuration: StudioConfig;
  steps: {
    skill_id: SkillId;
    status: "pending" | "running" | "completed" | "failed" | "skipped";
    attempts: number;
    started_at: string | null;
    completed_at: string | null;
    input: Record<string, unknown> | null;
    output: Record<string, unknown> | null;
    error: StudioError | null;
  }[];
  result: {
    summary: string;
    qualified_count: number;
    evaluated_count: number;
    criteria_met: boolean;
    criteria_note: string;
    prospects: Prospect[];
    drafts: OutreachDraft[];
  } | null;
  logs: { at: string; kind: string; skill_id: SkillId | null; message: string }[];
  approvals: { id: string; action: string; status: string }[];
  limits: {
    max_steps: number;
    max_api_calls: number;
    max_llm_calls: number;
    max_tokens: number;
    max_cost_usd: number | null;
    timeout_seconds: number;
  };
};
export type StudioCatalog = {
  templates: {
    id: string;
    name: string;
    description: string;
    version: number;
    skill_sequence: SkillId[];
    required_tools: ToolId[];
    triggers: string[];
  }[];
  skills: {
    id: SkillId;
    name: string;
    description: string;
    required_tools: ToolId[];
    input_schema: object;
    output_schema: object;
    configuration_schema: object | null;
    effect: string;
  }[];
  tools: { id: ToolId; name: string; configured: boolean; effect: string; setup: string }[];
  manual_only: boolean;
  credentials: string;
  limits: {
    max_prospects: number;
    max_steps: number;
    max_api_calls: number;
    max_llm_calls: number;
    max_tokens: number;
  };
};
