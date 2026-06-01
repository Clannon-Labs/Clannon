"""Bridge legacy message dictionaries into the current PydanticAI runtime.

The terminal loop still speaks in simple OpenAI-style message dictionaries.
This module translates that history, chooses provider fallbacks, and calls the
central `vraksha_agent` without making the loop own orchestration details.
"""

from __future__ import annotations

import logging

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from src.agent.bootstrap import bootstrap_vraksha
from src.agent.runtime import vraksha_agent
from src.error_handlers.extract import extract_error_info
from src.providers import get_model_priorities

logger = logging.getLogger(__name__)


def agent_bridge(messages: list[dict]) -> str:
    """Run the central agent against legacy loop messages and return text output."""
    deps = bootstrap_vraksha()
    pydantic_history = []
    last_query = "Hello"

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "user":
            pydantic_history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            last_query = content
        elif role == "assistant":
            pydantic_history.append(ModelResponse(parts=[TextPart(content=content)]))

    if pydantic_history and isinstance(pydantic_history[-1], ModelRequest):
        pydantic_history.pop()

    model_chain = get_model_priorities("orchestrator")
    if not model_chain:
        return "ERROR: No valid API keys found. Please check your .env file."

    last_error = None
    provider_errors = []
    attempted_models = []

    for model_candidate in model_chain:
        model_inst = None
        try:
            model_inst = model_candidate.instantiate()
            if not model_inst:
                raise RuntimeError(
                    f"Provider {model_candidate} could not be initialized."
                )

            attempted_models.append(model_inst)
            logger.info("Attempting run with: %s", model_inst)
            result = vraksha_agent.run_sync(
                last_query,
                deps=deps,
                model=model_inst,
                message_history=pydantic_history if pydantic_history else None,
            )
            return result.output

        except Exception as exc:
            failed_model = model_inst or model_candidate
            last_error = extract_error_info(exc, failed_model)
            provider_errors.append((str(failed_model), last_error))
            logger.warning(
                "Provider %s failed | status=%s | model=%s | error=%s%s",
                failed_model,
                last_error["status_code"],
                last_error["model_name"],
                last_error["message"],
                f" | help={last_error['help_url']}" if last_error["help_url"] else "",
            )

    return _format_provider_failure(
        provider_errors=provider_errors,
        last_error=last_error,
        attempted_models=attempted_models,
        model_chain=model_chain,
    )


def _format_provider_failure(
    *,
    provider_errors: list[tuple[str, dict]],
    last_error: dict | None,
    attempted_models: list[object],
    model_chain: list[object],
) -> str:
    """Build a readable error report after every configured provider fails."""
    primary_failure = provider_errors[0][1] if provider_errors else last_error
    primary_provider = provider_errors[0][0] if provider_errors else "unknown"

    if primary_failure is None:
        return "ERROR: No providers were attempted."

    retry_line = (
        f"        > Retry    : Provider suggested retrying after "
        f"{primary_failure['retry_after']}"
        if primary_failure.get("retry_after")
        else ""
    )
    help_line = (
        f"        > Help     : {primary_failure['help_url']}"
        if primary_failure.get("help_url")
        else ""
    )
    detail_lines = primary_failure.get("details") or []
    primary_details = "\n".join(
        f"            {line}"
        for line in detail_lines[:4]
    )
    primary_details_block = (
        f"        > Details  :\n{primary_details}" if primary_details else ""
    )
    failure_lines = "\n".join(
        (
            f"        > {provider}: "
            f"{error['category']} | status={error['status_code']} | "
            f"model={error['model_name']} | {error['message']}"
        )
        for provider, error in provider_errors
    )

    attempted = ", ".join(str(m) for m in attempted_models)
    configured = ", ".join(str(m) for m in model_chain)

    return f"""
        Vraksha: COGNITIVE BLOCKAGE DETECTED
        ------------------------------------------------------------
        I could not complete the request because every configured provider failed.

        PRIMARY FAILURE:
        > Provider : {primary_provider}
        > Status   : {primary_failure["status_code"]}
        > Model    : {primary_failure["model_name"]}
        > Cause    : {primary_failure["likely_cause"]}
        > Error    : {primary_failure["message"]}
{primary_details_block}
{retry_line}
{help_line}

        WHAT TO DO:
        > {primary_failure["suggested_fix"]}

        PROVIDER ATTEMPTS:
{failure_lines}

        FALLBACK STATUS:
        > Attempted Providers: {attempted or configured}
        ------------------------------------------------------------
    """
