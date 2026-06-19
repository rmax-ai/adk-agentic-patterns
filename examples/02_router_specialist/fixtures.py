"""Test fixtures for Pattern 02: Router-Specialist.

Standalone reference copy — see agent.py for the authoritative definitions.
Contains ScriptedModel fixture data for routing verdicts and
specialist responses, including a confusion-matrix test set.
"""

from __future__ import annotations

from .contracts import RouterVerdict, SpecialistOutput

# Confidence threshold for deterministic fallback
CONFIDENCE_THRESHOLD = 0.6

# -- Routing verdict fixtures (model-driven) --------------------------------

ROUTER_FIXTURES: dict[str, RouterVerdict] = {
    "billing_route": RouterVerdict(
        route="billing",
        confidence=0.92,
        reasoning="Customer mentions overcharge and invoice dispute",
    ),
    "account_route": RouterVerdict(
        route="account",
        confidence=0.89,
        reasoning="Customer cannot log in and needs password reset",
    ),
    "technical_route": RouterVerdict(
        route="technical",
        confidence=0.91,
        reasoning="Customer reports API errors and system downtime",
    ),
    "low_confidence": RouterVerdict(
        route="billing",
        confidence=0.45,
        reasoning="Weak signal — customer mentions 'pay' vaguely",
    ),
    "unknown_route": RouterVerdict(
        route="unknown_topic",
        confidence=0.35,
        reasoning="Customer query does not match any known category",
    ),
    "ambiguous": RouterVerdict(
        route="general",
        confidence=0.40,
        reasoning="Query spans billing, account, and technical topics",
    ),
}

# -- Confusion-matrix test set ----------------------------------------------

CONFUSION_MATRIX: dict[str, tuple[str, RouterVerdict]] = {
    "billing_as_account": (
        "billing",
        RouterVerdict(
            route="account",
            confidence=0.78,
            reasoning="Model misrouted — customer has billing question",
        ),
    ),
    "account_as_technical": (
        "account",
        RouterVerdict(
            route="technical",
            confidence=0.81,
            reasoning="Model misrouted — customer has account issue",
        ),
    ),
    "technical_as_billing": (
        "technical",
        RouterVerdict(
            route="billing",
            confidence=0.75,
            reasoning="Model misrouted — customer has technical issue",
        ),
    ),
}

# -- Specialist response fixtures -------------------------------------------

SPECIALIST_FIXTURES: dict[str, SpecialistOutput] = {
    "billing_handled": SpecialistOutput(
        specialist="billing",
        response="I've reviewed your invoice and processed a refund for the overcharge. You should see the credit within 3\u20135 business days.",
        tools_used=["lookup_invoice", "process_refund"],
    ),
    "account_handled": SpecialistOutput(
        specialist="account",
        response="I've reset your password. Please check your email for the temporary password and login instructions.",
        tools_used=["reset_password", "send_verification_email"],
    ),
    "technical_handled": SpecialistOutput(
        specialist="technical",
        response="I checked the API status. The 500 errors were caused by a temporary outage that has been resolved. Please retry your requests.",
        tools_used=["check_api_status", "query_logs"],
    ),
    "general_handled": SpecialistOutput(
        specialist="general",
        response="Thank you for your inquiry. I've forwarded your request to the appropriate team for review. A representative will follow up.",
        tools_used=[],
    ),
}

# -- Request texts -----------------------------------------------------------

REQUEST_TEXTS: dict[str, str] = {
    "billing_route": "I was overcharged on my last invoice and need a refund.",
    "account_route": "I can't log into my account after the password reset.",
    "technical_route": "Your API keeps returning 500 errors and timing out.",
    "low_confidence": "Pay.",
    "unknown_route": "What is the meaning of life?",
    "ambiguous": "I have questions about my bill and also can't access the dashboard.",
}
