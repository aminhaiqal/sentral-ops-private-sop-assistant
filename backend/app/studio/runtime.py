"""Approved skill sequences; no model-driven workflow routing or arbitrary execution."""

import asyncio
import json
import logging
import time
import traceback
from datetime import UTC, datetime

from pydantic import ValidationError

from app.config import Settings
from app.connections.drive import DriveService
from app.connections.provider import SETUP
from app.connections.store import ConnectionStore
from app.harness.store import now
from app.studio.models import BotConfig, RunResult
from app.studio.providers import Providers
from app.studio.registry import REGISTRY
from app.studio.safety import StudioError, redact
from app.studio.store import StudioNotFound, StudioStore, log_event

logger = logging.getLogger(__name__)


class Context:
    def __init__(self, store, row, state, settings, providers):
        self.store, self.state, self.settings, self.providers = store, state, settings, providers
        self.run_id, self.workspace, self.bot_id = row["id"], row["workspace"], row["bot_id"]

    def check(self, tools=()):
        row = self.store.row(self.workspace, self.run_id)
        if row["status"] != "running":
            raise StudioError("cancelled", "Execution was stopped.")
        try:
            current = self.store.bot(self.workspace, self.bot_id).configuration
        except StudioNotFound as exc:
            raise StudioError("permission_denied", "The bot was deleted.") from exc
        if not current.enabled or not set(tools).issubset(current.tools):
            raise StudioError(
                "permission_denied",
                "A required tool was revoked or the bot was disabled. Start a new run after reviewing its permissions.",
            )
        allowed = self.state["configuration"]["tools"]
        if not set(tools).issubset(allowed):
            raise StudioError(
                "permission_denied", "This tool was not granted when the run was submitted."
            )
        source = self.state["configuration"].get("drive_source")
        if source:
            if not self.settings.connections_configured:
                raise StudioError("configuration_error", SETUP, retryable=True)
            if (
                not current.drive_source
                or current.drive_source.connection_id != source["connection_id"]
                or not set(source["file_ids"]).issubset(current.drive_source.file_ids)
            ):
                raise StudioError(
                    "permission_denied",
                    "This bot's selected Drive account or files were revoked. Start a new run after reviewing permissions.",
                )
            ConnectionStore(self.store.tasks, self.settings).owned(
                self.workspace, source["connection_id"]
            )
        remaining = (
            datetime.fromisoformat(self.state["deadline_at"]) - datetime.now(UTC)
        ).total_seconds()
        if remaining <= 0:
            raise StudioError(
                "run_timeout",
                "This execution reached its time limit. Review saved results and start a new run.",
            )
        return max(0.1, min(remaining, self.settings.harness_request_timeout_seconds, 30))

    def checkpoint(self):
        if not self.store.checkpoint(self.run_id, self.state):
            raise StudioError("cancelled", "Execution was stopped.")

    def reserve(self, *, input_bound=0, output_bound=0, llm=False):
        usage, limits, pricing = self.state["usage"], self.state["limits"], self.state["pricing"]
        cost = None
        if pricing["input"] is not None and pricing["output"] is not None:
            cost = (input_bound * pricing["input"] + output_bound * pricing["output"]) / 1_000_000
        if (
            usage["api_calls"] >= limits["max_api_calls"]
            or (llm and usage["llm_calls"] >= limits["max_llm_calls"])
            or usage["charged_token_bound"] + input_bound + output_bound > limits["max_tokens"]
            or (cost is not None and usage["estimated_cost_usd"] + cost > limits["max_cost_usd"])
        ):
            raise StudioError(
                "budget_exceeded",
                "The run's API, token or configured AI spending limit was reached. Existing saved results are retained.",
            )
        usage["api_calls"] += 1
        if llm:
            usage["llm_calls"] += 1
            usage["unreported_llm_calls"] = usage.get("unreported_llm_calls", 0) + 1
        usage["charged_token_bound"] += input_bound + output_bound
        if cost is not None:
            usage["estimated_cost_usd"] += cost
        self.checkpoint()
        return input_bound + output_bound, cost

    def search(self, query, limit):
        timeout = self.check({"brave_search"})
        if not self.settings.brave_search_api_key:
            raise StudioError(
                "configuration_error",
                "Brave Search is not configured. Create a Web Search API key at https://api-dashboard.search.brave.com, set BRAVE_SEARCH_API_KEY on the backend and worker, and restart both services.",
                retryable=True,
            )
        self.reserve()
        return self.providers.search(query, limit, timeout)

    def drive_documents(self, source):
        timeout = self.check({"google_drive"})
        connections = ConnectionStore(self.store.tasks, self.settings)
        service = DriveService(connections, self.settings)
        connections.begin_operation(self.workspace, source.connection_id, "bot_read_files")

        def before_call():
            self.check({"google_drive"})
            self.reserve()

        try:
            documents = asyncio.run(service.context(self.workspace, source, before_call, timeout))
            self.check({"google_drive"})
            connections.record(self.workspace, source.connection_id, "bot_read_files", "completed")
            return documents
        except StudioError as exc:
            connections.record(self.workspace, source.connection_id, "bot_read_files", exc.code)
            raise

    def generate(self, schema, instructions, data):
        timeout = self.check({"llm"})
        if not self.settings.openai_api_key:
            raise StudioError(
                "configuration_error",
                "Set OPENAI_API_KEY, OPENAI_BASE_URL and OPENAI_CHAT_MODEL on the backend and worker. Use a model supporting Responses structured outputs.",
                retryable=True,
            )
        data = redact(data)
        # A conservative UTF-8 byte bound avoids a new tokenizer dependency. Reserve before
        # dispatch; a lost response or worker crash cannot reset spending to zero.
        input_bound = (
            len(json.dumps(data, ensure_ascii=False).encode())
            + len(instructions.encode())
            + len(json.dumps(schema.model_json_schema()).encode())
            + 1024
        )
        output_bound = 4000
        reserved, cost = self.reserve(input_bound=input_bound, output_bound=output_bound, llm=True)
        response = self.providers.generate(schema, instructions, data, timeout, output_bound)
        usage = self.state["usage"]
        if response.input_tokens is not None and response.output_tokens is not None:
            if min(response.input_tokens, response.output_tokens) < 0:
                raise StudioError(
                    "invalid_usage", "The AI provider returned invalid usage information."
                )
            usage["input_tokens"] += response.input_tokens
            usage["output_tokens"] += response.output_tokens
            usage["charged_token_bound"] += (
                response.input_tokens + response.output_tokens - reserved
            )
            usage["unreported_llm_calls"] -= 1
            if cost is not None:
                pricing = self.state["pricing"]
                usage["estimated_cost_usd"] += (
                    response.input_tokens * pricing["input"]
                    + response.output_tokens * pricing["output"]
                ) / 1_000_000 - cost
        self.checkpoint()
        if usage["charged_token_bound"] > self.state["limits"]["max_tokens"] or (
            usage["estimated_cost_usd"] is not None
            and usage["estimated_cost_usd"] > self.state["limits"]["max_cost_usd"]
        ):
            raise StudioError(
                "budget_exceeded",
                "Reported AI usage exceeded the reserved budget. Execution stopped before another call.",
            )
        if not response.completed:
            raise StudioError(
                "invalid_output",
                "The AI response was incomplete or refused. Use a smaller target or review the model configuration.",
            )
        try:
            return schema.model_validate_json(response.text, strict=True)
        except ValidationError as exc:
            raise StudioError(
                "invalid_output",
                "The AI response did not match the required output schema. Unvalidated results were not saved.",
            ) from exc


def step_input(skill_id, config, outputs):
    target = config.target
    if skill_id == "drive_context":
        return {"source": config.drive_source.model_dump()}
    if skill_id == "research":
        return {
            "industry": target.industry,
            "location": target.location,
            "limit": min(target.max_prospects * 2, 16),
        }
    if skill_id == "analyze":
        return {
            "objective": config.objective,
            "criteria": target.qualification_criteria,
            "candidates": outputs["research"]["candidates"],
            "minimum_score": target.minimum_score,
            "limit": target.max_prospects,
            "drive_context": outputs.get("drive_context", {}).get("documents", []),
        }
    if skill_id == "save":
        return {"prospects": outputs["analyze"]["qualified"]}
    if skill_id == "draft":
        return {
            "objective": config.objective,
            "offering": target.offering,
            "instructions": config.expected_results.description,
            "prospects": outputs["save"]["prospects"],
            "drive_context": outputs.get("drive_context", {}).get("documents", []),
        }
    raise StudioError("unsupported_skill", "The template references an unregistered skill.")


class StudioRuntime:
    def __init__(self, store: StudioStore, settings: Settings, providers=None):
        self.store, self.settings = store, settings
        self.providers = providers or Providers(settings)

    def run(self, row, stopping=lambda: False):
        state = json.loads(row["state"])
        ctx = Context(self.store, row, state, self.settings, self.providers)
        step = None
        try:
            config = BotConfig.model_validate(state["configuration"])
            outputs = {}
            for step in state["steps"]:
                if step["status"] == "completed":
                    outputs[step["skill_id"]] = step["output"]
                    continue
                if stopping():
                    self.store.checkpoint(row["id"], state, "queued")
                    return
                skill = REGISTRY.get(step["skill_id"])
                if skill is None or skill.id not in config.skills:
                    raise StudioError(
                        "unsupported_skill", "This skill is not registered for the bot template."
                    )
                if skill.effect not in {"read", "internal_write", "draft"}:
                    raise StudioError(
                        "approval_required",
                        "Consequential external actions require human approval and are not enabled in this version.",
                    )
                ctx.check(skill.tools)
                if step["attempts"] >= 3:
                    raise StudioError(
                        "retry_limit",
                        "This step reached its three-attempt limit. Review its error before starting a new run.",
                    )
                payload = step_input(skill.id, config, outputs)
                request = skill.input_schema.model_validate(payload, strict=True)
                step.update(
                    status="running",
                    attempts=step["attempts"] + 1,
                    started_at=now(),
                    completed_at=None,
                    error=None,
                    input=redact(request.model_dump()),
                )
                log_event(state, "step_started", f"{skill.name} started.", skill.id)
                ctx.checkpoint()
                # At most one automatic retry for transient read/AI errors. No arbitrary loops.
                try:
                    output = skill.handler(ctx, request)
                except StudioError as exc:
                    if (
                        not exc.retryable
                        or exc.code
                        not in {"provider_error", "provider_timeout", "provider_unavailable"}
                        or step["attempts"] >= 3
                    ):
                        raise
                    ctx.check(skill.tools)
                    step["attempts"] += 1
                    log_event(
                        state,
                        "step_retry",
                        "Temporary provider error; one bounded retry.",
                        skill.id,
                    )
                    ctx.checkpoint()
                    time.sleep(min(1, ctx.check(skill.tools)))
                    output = skill.handler(ctx, request)
                result = skill.output_schema.model_validate(
                    redact(output.model_dump()), strict=True
                )
                ctx.check(skill.tools)
                step.update(status="completed", completed_at=now(), output=result.model_dump())
                outputs[skill.id] = step["output"]
                log_event(state, "step_completed", f"{skill.name} completed.", skill.id)
                ctx.checkpoint()
                logger.info(
                    "studio_step_completed run_id=%s skill=%s attempts=%s",
                    row["id"],
                    skill.id,
                    step["attempts"],
                )
            saved, analysis, drafts = (
                outputs["save"],
                outputs["analyze"],
                outputs.get("draft", {"drafts": []}),
            )
            count = saved["saved_count"]
            draft_count = len(drafts["drafts"])
            draft_summary = (
                f"created {draft_count} outreach {'draft' if draft_count == 1 else 'drafts'}"
                if "draft" in config.skills
                else "outreach drafts were not requested"
            )
            state["result"] = RunResult(
                summary=f"Researched {analysis['evaluated_count']} sources, saved {count} qualified {'prospect' if count == 1 else 'prospects'}; {draft_summary}. No messages were sent.",
                qualified_count=count,
                evaluated_count=analysis["evaluated_count"],
                criteria_met=count >= config.expected_results.minimum_qualified
                and ("draft" not in config.skills or len(drafts["drafts"]) == count),
                criteria_note="Checks cover the required count, qualification score, source-matched names and quotes, deduplication, database persistence and draft coverage when selected. Natural-language criteria and business facts still need human review.",
                prospects=saved["prospects"],
                drafts=drafts["drafts"],
            ).model_dump()
            state.update(error=None, completed_at=now())
            log_event(state, "completed", state["result"]["summary"])
            self.store.checkpoint(row["id"], state, "completed")
        except Exception as exc:
            if isinstance(exc, StudioError):
                error = exc
            elif isinstance(exc, ValidationError):
                error = StudioError(
                    "validation_error",
                    "A step's input or output did not match its registered schema.",
                )
            else:
                error = StudioError(
                    "internal_error",
                    "Execution stopped because of an internal error. Check server logs using this run ID.",
                )
            # Avoid exception bodies: provider exceptions may contain credentials or source data.
            logger.warning(
                "studio_run_failed run_id=%s code=%s exception_type=%s",
                row["id"],
                error.code,
                type(exc).__name__,
            )
            if error.code == "internal_error":
                logger.error(
                    "studio_internal_error run_id=%s frames=%s",
                    row["id"],
                    [
                        (frame.filename, frame.lineno, frame.name)
                        for frame in traceback.extract_tb(exc.__traceback__)[-8:]
                    ],
                )
            detail = {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable and (step is None or step["attempts"] < 3),
            }
            if step is not None and step["status"] != "completed":
                step.update(status="failed", completed_at=now(), error=detail)
            state.update(error=detail, completed_at=now())
            log_event(state, "failed", error.message, step["skill_id"] if step else None)
            self.store.checkpoint(row["id"], state, "failed")
