"""Pattern 08: Bounded Loop Agent.

Scenario: Draft and validate a compliance report until all required sections
are present, using a bounded loop with explicit iteration budgets.

The agent drafts a compliance report, validates it against a required checklist,
and iteratively improves the draft until all sections pass or the budget is exhausted.

Required sections: executive_summary, methodology, findings, recommendations, signatures

State keys: draft, missing_sections[], iteration, status
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from adk_patterns.config import Config
from adk_patterns.contracts import ExecutionStatus, PatternRunResult
from adk_patterns.models import ScriptedModel, structured_response
from adk_patterns.shared import RunContext, run_scope


# ── Contracts ───────────────────────────────────────────────────────────────

REQUIRED_SECTIONS = frozenset({
    "executive_summary",
    "methodology",
    "findings",
    "recommendations",
    "signatures",
})


class SectionValidation(BaseModel):
    """Validation result for a compliance report draft."""

    missing: list[str] = Field(
        default_factory=list,
        description="List of missing or invalid sections",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Suggestions for improvement",
    )

    @property
    def is_valid(self) -> bool:
        """Return True if all required sections are present."""
        return len(self.missing) == 0


class ComplianceReport(BaseModel):
    """A compliance report with sections keyed by name."""

    sections: dict[str, str] = Field(
        default_factory=dict,
        description="Report sections keyed by section name",
    )
    complete: bool = Field(default=False, description="Whether the report is complete")
    issues: list[str] = Field(
        default_factory=list,
        description="Outstanding issues with the report",
    )


# ── Fixture data ────────────────────────────────────────────────────────────

# Iteration 1: first draft — missing several sections
DRAFT_1 = structured_response({
    "sections": {
        "executive_summary": "This report covers the compliance audit results for Q2 2026.",
        "methodology": "We used a risk-based approach to assess controls across all domains.",
    },
    "complete": False,
    "issues": [
        "findings section is missing",
        "recommendations section is missing",
        "signatures section is missing",
    ],
})

# Validation for draft 1 — 3 missing sections
VALIDATION_1 = structured_response({
    "missing": ["findings", "recommendations", "signatures"],
    "suggestions": [
        "Add a findings section documenting audit results",
        "Add a recommendations section with actionable remediation steps",
        "Add a signatures section for stakeholder approval",
    ],
})

# Iteration 2: second draft — still missing signatures
DRAFT_2 = structured_response({
    "sections": {
        "executive_summary": "This report covers the compliance audit results for Q2 2026.",
        "methodology": "We used a risk-based approach to assess controls across all domains.",
        "findings": "Three critical findings were identified: missing MFA on admin accounts, outdated TLS certificates, and lack of audit logging.",
        "recommendations": "1. Enforce MFA on all admin accounts within 30 days. 2. Update TLS certificates before expiry. 3. Implement centralized audit logging.",
    },
    "complete": False,
    "issues": [
        "signatures section is missing",
    ],
})

# Validation for draft 2 — 1 missing section
VALIDATION_2 = structured_response({
    "missing": ["signatures"],
    "suggestions": [
        "Add a signatures section with stakeholder approval fields",
    ],
})

# Iteration 3: final draft — all sections present
DRAFT_3 = structured_response({
    "sections": {
        "executive_summary": "This report covers the compliance audit results for Q2 2026.",
        "methodology": "We used a risk-based approach to assess controls across all domains.",
        "findings": "Three critical findings were identified: missing MFA on admin accounts, outdated TLS certificates, and lack of audit logging.",
        "recommendations": "1. Enforce MFA on all admin accounts within 30 days. 2. Update TLS certificates before expiry. 3. Implement centralized audit logging.",
        "signatures": "Approved by: John Doe (CISO), Jane Smith (Audit Lead), Date: 2026-06-20",
    },
    "complete": True,
    "issues": [],
})

# Validation for draft 3 — all sections present
VALIDATION_3 = structured_response({
    "missing": [],
    "suggestions": ["All required sections are present. Report is ready for submission."],
})

# Non-converging: keeps returning the same incomplete draft
DRAFT_STUCK = structured_response({
    "sections": {
        "executive_summary": "This report covers the compliance audit results.",
        "methodology": "Risk-based approach used.",
    },
    "complete": False,
    "issues": ["findings, recommendations, and signatures sections are missing"],
})

VALIDATION_STUCK = structured_response({
    "missing": ["findings", "recommendations", "signatures"],
    "suggestions": ["Add all missing sections"],
})


# ── Response sequences ─────────────────────────────────────────────────────

# Converging sequence: draft → validate → draft → validate → draft → validate → pass
CONVERGING_SEQUENCE = [
    DRAFT_1,    # 1: first draft
    VALIDATION_1,  # 2: validate — 3 missing
    DRAFT_2,    # 3: second draft
    VALIDATION_2,  # 4: validate — 1 missing
    DRAFT_3,    # 5: third draft (complete)
    VALIDATION_3,  # 6: validate — all pass
]

# Non-converging sequence: draft → validate → draft → validate → ...
# Each iteration still has missing sections, eventually budget exhausted
NON_CONVERGING_SEQUENCE = [
    DRAFT_1, VALIDATION_1,
    DRAFT_2, VALIDATION_2,
    DRAFT_2, VALIDATION_2,
    DRAFT_2, VALIDATION_2,
    DRAFT_2, VALIDATION_2,
]

# Immediate pass sequence: first draft is already complete
IMMEDIATE_PASS_SEQUENCE = [
    DRAFT_3,    # 1: first draft is already complete
    VALIDATION_3,  # 2: validate — all pass
]


# ── Scene helpers ──────────────────────────────────────────────────────────

SEQUENCES: dict[str, list] = {
    "converges": CONVERGING_SEQUENCE,
    "budget_exhausted": NON_CONVERGING_SEQUENCE,
    "stop_on_pass": IMMEDIATE_PASS_SEQUENCE,
}


# ── Core functions ─────────────────────────────────────────────────────────


def _validate_draft(
    draft: dict[str, Any],
) -> SectionValidation:
    """Validate a compliance report draft against the required checklist.

    Checks which required sections are present in the draft.
    """
    sections = draft.get("sections", {})
    present = set(sections.keys())
    missing = sorted(REQUIRED_SECTIONS - present)

    suggestions = []
    for section in missing:
        suggestions.append(f"Add the '{section}' section to the report")

    if not missing:
        suggestions.append("All required sections are present. Report is ready for submission.")

    return SectionValidation(missing=missing, suggestions=suggestions)


def _draft_report(
    ctx: RunContext,
    model: ScriptedModel,
    iteration: int,
    feedback: str = "",
) -> ComplianceReport | None:
    """Draft or improve a compliance report.

    Uses the scripted model to produce a ComplianceReport.
    On iteration 0, drafts from scratch. On subsequent iterations,
    incorporates validation feedback to improve the draft.
    """
    ctx.audit("draft", "model_call", resource=f"draft_iteration_{iteration}")
    ctx.record_model_call(tokens=100)

    if iteration == 0:
        instruction = (
            "Draft a compliance report with the following required sections: "
            f"{', '.join(sorted(REQUIRED_SECTIONS))}. "
            "Return a structured ComplianceReport."
        )
    else:
        instruction = (
            f"Improve the compliance report draft based on this feedback: {feedback}. "
            "Ensure all required sections are present: "
            f"{', '.join(sorted(REQUIRED_SECTIONS))}."
        )

    response = model.invoke(
        system_instruction=instruction,
        messages=[{"role": "user", "content": f"__FIXTURE__:draft_{iteration} {instruction}"}],
    )

    ctx.audit("draft", "model_response", outcome="success")

    data = response.structured_output
    if data is None:
        ctx.audit("draft", "validation_failed", outcome="failure", metadata={"reason": "no_structured_output"})
        ctx.mark_failed("Draft: model returned no structured output")
        return None

    try:
        report = ComplianceReport(**data)
    except Exception as e:
        ctx.audit("draft", "validation_failed", outcome="failure", metadata={"errors": str(e)})
        ctx.mark_failed(f"Draft: schema validation failed — {e}")
        return None

    return report


# ── Main bounded loop ──────────────────────────────────────────────────────


def run(
    config: Config | None = None,
    scenario: str = "converges",
) -> PatternRunResult:
    """Execute the bounded-loop compliance report workflow.

    The agent iteratively drafts and validates a compliance report until:
    - All required sections pass validation (SUCCEEDED), or
    - The iteration budget is exhausted (BUDGET_EXHAUSTED)

    Args:
        config: Application configuration (uses defaults if None).
        scenario: Test scenario ('converges', 'budget_exhausted', 'stop_on_pass').

    Returns:
        PatternRunResult with the final report state or partial result.
    """
    model = ScriptedModel()

    seq = SEQUENCES.get(scenario, CONVERGING_SEQUENCE)
    model.set_response_sequence(seq)

    with run_scope(
        "bounded-loop-agent",
        scenario,
        max_model_calls=6,
        max_tool_calls=50,
        max_iterations=5,
    ) as ctx:
        state: dict[str, Any] = {
            "draft": {},
            "missing_sections": list(REQUIRED_SECTIONS),
            "iteration": 0,
            "status": "in_progress",
        }

        feedback = ""

        while True:
            # Check budget before each iteration
            budget_status = ctx.check_budget()
            if budget_status is not None:
                ctx.status = ExecutionStatus.BUDGET_EXHAUSTED
                ctx.failure_reason = f"Budget exhausted after {ctx.iterations} iterations"
                state["status"] = "BUDGET_EXHAUSTED"

                # Ensure missing_sections is populated
                if not state["missing_sections"]:
                    state["missing_sections"] = list(REQUIRED_SECTIONS)
                break

            ctx.record_iteration()
            iteration = state["iteration"]

            # ── Step 1: Draft the report ──────────────────────────────────
            report = _draft_report(ctx, model, iteration, feedback)
            if report is None:
                state["status"] = "FAILED"
                break

            state["draft"] = report.model_dump()

            # ── Step 2: Validate the draft ────────────────────────────────
            ctx.audit("validate", "model_call", resource=f"validate_iteration_{iteration}")
            ctx.record_model_call(tokens=50)

            response = model.invoke(
                system_instruction=(
                    "Validate the compliance report draft against the required section checklist. "
                    f"Required sections: {', '.join(sorted(REQUIRED_SECTIONS))}"
                ),
                messages=[{"role": "user", "content": f"__FIXTURE__:validate_{iteration} {report.model_dump_json()}"}],
            )

            ctx.audit("validate", "model_response", outcome="success")

            validation_data = response.structured_output
            if validation_data is None:
                # Fall back to programmatic validation
                validation = _validate_draft(report.model_dump())
            else:
                try:
                    validation = SectionValidation(**validation_data)
                except Exception:
                    validation = _validate_draft(report.model_dump())

            state["missing_sections"] = validation.missing
            feedback = "; ".join(validation.suggestions)

            # ── Step 3: Check convergence ─────────────────────────────────
            if validation.is_valid:
                state["status"] = "PASSED"
                break

            # Prepare for next iteration
            state["iteration"] += 1

        ctx.snapshot_state(state)
        ctx.output = state

    return ctx.to_result()


def main(config: Config | None = None, scenario: str = "converges") -> PatternRunResult:
    """Standard entry point called by CLI."""
    return run(config=config, scenario=scenario)
