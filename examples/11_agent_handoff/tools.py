"""Tool definitions and permission enforcement for Pattern 11: Agent Handoff.

Standalone reference copy — see agent.py for the authoritative definitions.
Support agent can access: lookup_customer, escalate
Refund specialist can access: lookup_refund, process_refund
"""

from __future__ import annotations
