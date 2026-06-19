"""Test fixtures for Pattern 00."""

FIXTURES = {
    "billing_issue": {"category": "billing", "confidence": 0.95, "reasoning": "Customer mentions charges"},
    "account_issue": {"category": "account", "confidence": 0.90, "reasoning": "Login and password reset"},
    "technical_issue": {"category": "technical", "confidence": 0.88, "reasoning": "API errors"},
    "ambiguous": {"category": "general", "confidence": 0.45, "reasoning": "Multiple categories"},
}
