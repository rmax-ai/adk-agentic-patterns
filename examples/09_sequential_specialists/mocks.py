"""Mock data and helpers for Sequential Specialists pattern tests.

Provides scenario definitions mapping each test scenario to the
fixture keys used across the four specialist stages.
"""

from __future__ import annotations

from typing import Any

# ── Claim submission texts ─────────────────────────────────────────────────

CLAIM_TEXTS: dict[str, str] = {
    "valid_auto": (
        "Claim submission: Rear-end collision on June 1, 2026 at Main and 5th. "
        "Policy POL-AUTO-88723, claimant Jane Doe. Minor rear bumper damage, "
        "no injuries. Amount claimed: $3,500.00."
    ),
    "valid_property": (
        "Claim submission: Water damage from burst pipe on May 28, 2026. "
        "Policy POL-HOME-45129, claimant John Smith. Basement kitchen flooring "
        "and drywall damaged. Amount claimed: $8,200.00."
    ),
    "ineligible": (
        "Claim submission: Auto accident on June 15, 2026. "
        "Policy POL-AUTO-99999, claimant Bob Wilson. Hit guardrail on Highway 101. "
        "Amount claimed: $12,000.00."
    ),
    "fraud_suspicious": (
        "Claim submission: Vehicle theft on June 10, 2026. "
        "Policy POL-AUTO-33412, claimant Alice Reed. Stolen from mall parking lot. "
        "Amount claimed: $45,000.00."
    ),
}

# ── Scenario fixture mappings ──────────────────────────────────────────────
# Each scenario maps to the fixture keys used at each stage.
# Key naming: stage{1,2,3,4}_{scenario}

SCENARIO_FIXTURES: dict[str, dict[str, str]] = {
    "valid_auto": {
        "stage1": "stage1_valid_auto",
        "stage2": "stage2_approved_auto",
        "stage3": "stage3_clean_auto",
        "stage4": "stage4_approved_auto",
    },
    "valid_property": {
        "stage1": "stage1_valid_property",
        "stage2": "stage2_approved_property",
        "stage3": "stage3_clean_property",
        "stage4": "stage4_approved_property",
    },
    "ineligible": {
        "stage1": "stage1_ineligible",
        "stage2": "stage2_denied_lapsed",
    },
    "fraud_suspicious": {
        "stage1": "stage1_fraud_suspicious",
        "stage2": "stage2_approved_fraud",
        "stage3": "stage3_fraud_theft",
    },
}


def get_scenario_fixture(scenario: str, stage: str) -> str | None:
    """Get the fixture key for a given scenario and stage, or None."""
    mapping = SCENARIO_FIXTURES.get(scenario, {})
    return mapping.get(stage)


def get_claim_text(scenario: str) -> str:
    """Get claim submission text for a scenario, with fallback."""
    return CLAIM_TEXTS.get(scenario, CLAIM_TEXTS["valid_auto"])


# ── Valid scenarios set for validation ──────────────────────────────────────

_VALID_SCENARIOS = frozenset(SCENARIO_FIXTURES.keys())


def is_valid_scenario(scenario: str) -> bool:
    """Check if a scenario name is valid."""
    return scenario in _VALID_SCENARIOS
