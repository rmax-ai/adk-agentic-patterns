"""Mock tool implementations for Pattern 02: Router-Specialist.

Standalone reference copy — see agent.py for the authoritative definitions.
Each specialist has an isolated set of mock tools.
"""

from __future__ import annotations


# -- Billing tools -----------------------------------------------------------


def lookup_invoice(ctx: object, invoice_id: str) -> dict[str, object]:
    """Look up an invoice by ID."""
    return {"invoice_id": invoice_id, "amount": 149.99, "status": "paid", "overcharged": True}


def process_refund(ctx: object, invoice_id: str, amount: float) -> dict[str, object]:
    """Process a refund for a given invoice."""
    return {"invoice_id": invoice_id, "refund_amount": amount, "status": "processed", "estimated_credit_days": "3-5"}


# -- Account tools -----------------------------------------------------------


def reset_password(ctx: object, username: str) -> dict[str, object]:
    """Reset a user's password and send reset email."""
    return {"username": username, "status": "reset_initiated", "email_sent": True}


def send_verification_email(ctx: object, email: str) -> dict[str, object]:
    """Send a verification email to the user."""
    return {"email": email, "status": "sent"}


# -- Technical tools ---------------------------------------------------------


def check_api_status(ctx: object, service: str) -> dict[str, object]:
    """Check the current status of an API service."""
    return {
        "service": service,
        "status": "operational",
        "recent_incidents": ["500 errors from 14:30-14:45 UTC"],
        "uptime_pct": 99.95,
    }


def query_logs(ctx: object, service: str, timeframe: str) -> dict[str, object]:
    """Query service logs for a given timeframe."""
    return {
        "service": service,
        "timeframe": timeframe,
        "entries": [
            {"timestamp": "14:30:01", "level": "ERROR", "message": "HTTP 500 on /api/v1/orders"},
            {"timestamp": "14:35:12", "level": "ERROR", "message": "HTTP 500 on /api/v1/users"},
            {"timestamp": "14:45:00", "level": "INFO", "message": "Service restored"},
        ],
    }


# -- Tool registry (specialist -> allowed tools) -----------------------------

BILLING_TOOLS = {"lookup_invoice": lookup_invoice, "process_refund": process_refund}
ACCOUNT_TOOLS = {"reset_password": reset_password, "send_verification_email": send_verification_email}
TECHNICAL_TOOLS = {"check_api_status": check_api_status, "query_logs": query_logs}
GENERAL_TOOLS: dict[str, object] = {}

SPECIALIST_TOOL_MAP: dict[str, dict[str, object]] = {
    "billing": BILLING_TOOLS,
    "account": ACCOUNT_TOOLS,
    "technical": TECHNICAL_TOOLS,
    "general": GENERAL_TOOLS,
}
