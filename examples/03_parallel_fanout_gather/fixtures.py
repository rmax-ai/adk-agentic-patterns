"""Test fixtures for Pattern 03: Parallel Fan-Out/Gather."""

FIXTURES = {
    "security_eval": {
        "score": 8.5,
        "issues": ["Outdated TLS 1.1 on internal endpoints", "No bug bounty program"],
        "summary": "Good security posture with minor concerns around legacy protocol support.",
    },
    "legal_eval": {
        "score": 7.0,
        "issues": ["GDPR compliance documentation incomplete", "Indemnification clause too narrow"],
        "summary": "Adequate legal compliance with gaps in documentation and liability terms.",
    },
    "operational_eval": {
        "score": 9.0,
        "issues": ["Support SLA response time 1h above target"],
        "summary": "Highly operational vendor with strong uptime and mature incident response.",
    },
    "financial_eval": {
        "score": 6.5,
        "issues": ["Declining quarterly revenue", "High debt-to-equity ratio"],
        "summary": "Financially stable near-term but concerning trends in revenue and leverage.",
    },
    "synthesis": {
        "overall_score": 7.75,
        "recommendation": "conditional",
        "summary": (
            "Vendor shows strength in security and operations but has gaps in legal documentation "
            "and financial health. Recommend conditional approval with quarterly review."
        ),
    },
}

FAILING_FIXTURES = {
    **FIXTURES,
    "security_eval": None,  # Security evaluation fails
}
