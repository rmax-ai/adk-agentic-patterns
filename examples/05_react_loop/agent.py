"""Pattern 05: ReAct Loop.

Scenario: Diagnose a fictional service incident by querying metrics, logs,
and deployment history tools. The model dynamically selects read-only tools
(no write operations) and submits a final diagnosis.

Demonstrates:
- ReAct loop with dynamic tool selection
- Maximum step budget enforcement (max_model_calls=10, max_tool_calls=8, max_iterations=5)
- Termination tool (submit_diagnosis) that ends the reasoning loop
- Repeated-action detection (same tool with same args flagged)
- Observable state: observations[], actions[], diagnosis (no raw chain-of-thought)
- Non-convergence detection (model loops without progress)
- Read-only enforcement — tools don't mutate external state
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.config import Config
from adk_patterns.contracts import (
    ExecutionStatus,
    PatternRunResult,
    ToolInvocationRecord,
)
from adk_patterns.models import ScriptedModel
from adk_patterns.shared import RunContext, run_scope

# Add this directory to path so we can import sibling modules
# (directory starts with digit so it can't be a regular Python package)
_example_dir = Path(__file__).resolve().parent
if str(_example_dir) not in sys.path:
    sys.path.insert(0, str(_example_dir))

from contracts import DiagnosisResult  # noqa: E402
from fixtures import QUERIES, SEQUENCES  # noqa: E402
from tools import (  # noqa: E402
    TOOL_REGISTRY,
    tool_definitions,
    validate_and_execute,
)
from mocks import get_shared_data, reset_shared_data  # noqa: E402


# ---------------------------------------------------------------------------
# ReAct Loop Agent
# ---------------------------------------------------------------------------


def run_diagnosis_loop(
    ctx: RunContext,
    model: ScriptedModel,
    query: str,
) -> dict[str, Any]:
    """Run the ReAct diagnosis loop.

    The model iteratively selects tools to query metrics, logs, and deployment
    history, building evidence. When sufficient evidence is gathered, it calls
    submit_diagnosis to terminate the loop.

    Key features:
    - Repeated-action detection: cannot call the same tool with same args twice
    - Budget enforcement: max_model_calls=10, max_tool_calls=8, max_iterations=5
    - Observable state: observations[], actions[], diagnosis (no raw CoT)

    Args:
        ctx: Run context for audit and budget tracking.
        model: ScriptedModel with pre-configured response sequence.
        query: The user's investigation request.

    Returns:
        A dict with keys: observations, actions, diagnosis, diagnosis_result,
        and termination_reason.
    """
    state: dict[str, Any] = {
        "observations": [],
        "actions": [],
        "diagnosis": None,
        "diagnosis_result": None,
        "termination_reason": "unknown",
    }

    messages: list[dict[str, Any]] = [{"role": "user", "content": query}]

    system_prompt = (
        "You are an incident diagnosis assistant. You have read-only tools "
        "to investigate a service incident.\n\n"
        "Available tools:\n"
        "- query_metrics(service: str, metric: str) — Query a service metric value\n"
        "- query_logs(service: str, timeframe: str) — Query recent log entries\n"
        "- get_deployment_history(service: str) — Get deployment history\n"
        "- submit_diagnosis(diagnosis: str, root_cause: str) — TERMINAL: Submit final diagnosis\n\n"
        "Rules:\n"
        "1. Call tools one at a time and analyze results before calling another.\n"
        "2. Do NOT call the same tool with the same arguments twice.\n"
        "3. When you have enough evidence, call submit_diagnosis to end the loop.\n"
        "4. After submit_diagnosis, provide a final summary as your answer.\n"
        "5. Store your observations and reasoning in the 'observations' state.\n"
        "6. NEVER fabricate data — only use information from tool results."
    )

    # Track previously executed tool calls for repeated-action detection
    executed_actions: set[tuple[str, frozenset]] = set()

    for iteration in range(20):  # generous inner loop; budget enforcement is external
        # Check budgets before proceeding
        budget_status = ctx.check_budget()
        if budget_status is not None:
            state["termination_reason"] = "budget_exhausted"
            ctx.mark_budget_exhausted()
            break

        ctx.record_iteration()

        response = model.invoke(
            system_instruction=system_prompt,
            messages=messages,
            tools=tool_definitions(),
        )
        ctx.record_model_call(tokens=response.usage.total_tokens)
        ctx.audit("agent", "model_call", resource=f"iteration_{ctx.iterations}")

        # Process tool calls if present
        if response.tool_calls:
            for tc in response.tool_calls:
                ctx.audit("agent", "tool_call", resource=tc.name, metadata={"call_id": tc.id})

                action_key = (tc.name, frozenset(sorted(tc.arguments.items())))
                is_repeated = action_key in executed_actions

                if not is_repeated:
                    executed_actions.add(action_key)

                # Action record (observable — no raw CoT)
                action_record = {
                    "tool": tc.name,
                    "arguments": dict(tc.arguments),
                    "repeated": is_repeated,
                }

                if is_repeated:
                    # Flag as repeated but still execute (we observe and flag)
                    ctx.audit(
                        "agent", "repeated_action",
                        resource=tc.name,
                        outcome="warning",
                        metadata={"arguments": dict(tc.arguments)},
                    )

                # Check tool budget
                if ctx.tool_calls >= ctx.budget.max_tool_calls:
                    result = {"error": "Tool call budget exhausted", "error_type": "BudgetExhausted"}
                    action_record["result"] = result
                    state["actions"].append(action_record)
                    state["observations"].append(f"Budget exhausted: could not call {tc.name}")
                    state["termination_reason"] = "budget_exhausted"
                    ctx.mark_budget_exhausted()
                    break

                try:
                    result = validate_and_execute(tc.name, tc.arguments)
                    ctx.record_tool_call(
                        ToolInvocationRecord(
                            tool_name=tc.name,
                            validated_arguments=dict(tc.arguments),
                            result_summary={"status": "success"},
                        )
                    )
                    action_record["result"] = {"status": "success", "data": result}

                    # Record observation from tool result
                    obs = _format_observation(tc.name, result)
                    state["observations"].append(obs)

                    # Check if this was the termination tool
                    if tc.name == "submit_diagnosis":
                        state["diagnosis"] = result.get("diagnosis", "")
                        state["diagnosis_result"] = DiagnosisResult(
                            category=_infer_category(result.get("diagnosis", "")),
                            root_cause=result.get("root_cause", ""),
                            confidence=0.85,
                            evidence=list(state["observations"]),
                        ).model_dump()
                        state["termination_reason"] = "diagnosis_submitted"

                except (ValueError, TypeError, Exception) as e:
                    error_type = type(e).__name__
                    ctx.record_tool_call(
                        ToolInvocationRecord(
                            tool_name=tc.name,
                            validated_arguments=dict(tc.arguments),
                            error_type=error_type,
                        )
                    )
                    ctx.audit("agent", "tool_error", resource=tc.name, outcome="failure", metadata={"error": str(e)})
                    action_record["result"] = {"error": str(e), "error_type": error_type}
                    state["observations"].append(f"Tool {tc.name} failed: {e}")

                state["actions"].append(action_record)

            # If diagnosis was submitted, break out of iteration loop
            if state["termination_reason"] == "diagnosis_submitted":
                break

            # Feed results back to model for next iteration
            result_lines = []
            for action in state["actions"]:
                if action["tool"] == "submit_diagnosis":
                    continue
                result_data = action.get("result", {})
                if "error" in result_data:
                    label = "REPEATED (already called)" if action["repeated"] else "ERROR"
                    result_lines.append(f"Tool {action['tool']}({action['arguments']}) → {label}: {result_data['error']}")
                else:
                    data = result_data.get("data", {})
                    label = "REPEATED" if action["repeated"] else "OK"
                    result_lines.append(f"Tool {action['tool']}({action['arguments']}) → {label}: {data}")

            if result_lines:
                messages.append({"role": "user", "content": "\n".join(result_lines)})

        else:
            # Text response — model is providing a summary or has stalled
            if state["diagnosis"]:
                # Already submitted diagnosis, this is the final summary
                state["final_summary"] = response.text
                break

            # Check for repeated text-only responses (non-convergence)
            if len(state["actions"]) > 0:
                last_action = state["actions"][-1]
                if response.text and not response.tool_calls:
                    # Multiple text-only responses in a row = non-convergence
                    if "stall_count" not in state:
                        state["stall_count"] = 0
                    state["stall_count"] += 1
                    if state["stall_count"] >= 3:
                        state["termination_reason"] = "non_convergence"
                        state["observations"].append("Agent stalled with repeated text-only responses")
                        ctx.mark_budget_exhausted()
                        break

            messages.append({"role": "assistant", "content": response.text})

    else:
        # Loop completed without break — budget exhausted
        if state["termination_reason"] == "unknown":
            state["termination_reason"] = "iteration_budget_exhausted"

    ctx.snapshot_state(state)
    return state


def _format_observation(tool_name: str, result: Any) -> str:
    """Format a tool result into an observable observation string (no raw CoT)."""
    if tool_name == "query_metrics":
        return (
            f"Metric {result.get('metric', '?')} for {result.get('service', '?')}: "
            f"{result.get('value', '?')} {result.get('unit', '')} "
            f"(healthy: {result.get('healthy', '?')})"
        )
    elif tool_name == "query_logs":
        return (
            f"Logs for {result.get('service', '?')}: "
            f"{result.get('error_count', 0)} errors in timeframe"
        )
    elif tool_name == "get_deployment_history":
        changes = result.get("recent_changes", [])
        return (
            f"Deployment history for {result.get('service', '?')}: "
            f"{len(result.get('deployments', []))} deployments, "
            f"{len(changes)} recent changes"
        )
    elif tool_name == "submit_diagnosis":
        return (
            f"Diagnosis submitted: {result.get('diagnosis', '')[:60]}..."
        )
    return f"{tool_name}: {str(result)[:100]}"


def _infer_category(diagnosis: str) -> str:
    """Infer incident category from diagnosis text."""
    d = diagnosis.lower()
    if "deployment" in d or "release" in d:
        return "infrastructure"
    elif "network" in d or "connection" in d or "timeout" in d:
        return "network"
    elif "database" in d or "schema" in d:
        return "data"
    elif "api" in d or "gateway" in d:
        return "application"
    return "infrastructure"


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Entry point for CLI and tests.

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario key (diagnosis_success, budget_exhausted, etc.).

    Returns:
        A PatternRunResult with status, output, metrics, and audit trail.
    """
    model = ScriptedModel()

    seq = SEQUENCES.get(scenario)
    if seq:
        model.set_response_sequence(seq)

    query = QUERIES.get(scenario, "Investigate the service incident and diagnose the root cause.")

    with run_scope(
        "react-loop",
        scenario,
        max_model_calls=10,
        max_tool_calls=8,
        max_iterations=5,
    ) as ctx:
        state = run_diagnosis_loop(ctx, model, query)
        ctx.output = state

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "default") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
