"""ModelResponse fixtures for Pattern 05: ReAct Loop.

Each scenario maps to a list of ModelResponse objects that are replayed
in sequence via ScriptedModel.set_response_sequence().

Fixtures cover:
- Happy path: metrics → logs → deployment history → diagnosis
- Budget exhausted: many tool calls without diagnosis
- Repeated action: same tool+args twice
- Non-convergence: model loops without progress
- Read-only enforcement: diagnosis submitted without external mutation
"""

from __future__ import annotations

from adk_patterns.models import text_response, tool_call_response

# ---------------------------------------------------------------------------
# Scenario response sequences
# Each entry is (scenario_key, list_of_ModelResponse)
# ---------------------------------------------------------------------------

SEQUENCES: dict[str, list] = {
    # --- Happy path: full diagnosis -----------------------------------------
    "default": [
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),
        tool_call_response("query_logs", {"service": "api-gateway", "timeframe": "last_15m"}),
        tool_call_response("get_deployment_history", {"service": "api-gateway"}),
        tool_call_response(
            "submit_diagnosis",
            {
                "diagnosis": "API Gateway is experiencing elevated error rates due to a recent deployment",
                "root_cause": "v2.4.1 deployment updated rate limiting config causing upstream timeouts",
            },
        ),
        text_response(
            "Diagnosis complete: The API Gateway incident is caused by the v2.4.1 deployment "
            "which updated rate limiting configuration, leading to upstream connection timeouts "
            "to the user-service. Elevated error rate of 12.3% confirmed via metrics and logs."
        ),
    ],
    "diagnosis_success": [
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),
        tool_call_response("query_logs", {"service": "api-gateway", "timeframe": "last_15m"}),
        tool_call_response("get_deployment_history", {"service": "api-gateway"}),
        tool_call_response(
            "submit_diagnosis",
            {
                "diagnosis": "API Gateway is experiencing elevated error rates due to a recent deployment",
                "root_cause": "v2.4.1 deployment updated rate limiting config causing upstream timeouts",
            },
        ),
        text_response(
            "Diagnosis complete: The API Gateway incident is caused by the v2.4.1 deployment "
            "which updated rate limiting configuration, leading to upstream connection timeouts "
            "to the user-service. Elevated error rate of 12.3% confirmed via metrics and logs."
        ),
    ],
    # --- Multi-step: check multiple services before diagnosis ----------------
    "multi_service_diagnosis": [
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),
        tool_call_response("query_metrics", {"service": "user-service", "metric": "error_rate"}),
        tool_call_response("query_logs", {"service": "api-gateway", "timeframe": "last_1h"}),
        tool_call_response("query_logs", {"service": "user-service", "timeframe": "last_1h"}),
        tool_call_response(
            "submit_diagnosis",
            {
                "diagnosis": "API Gateway is failing with upstream timeouts; user-service is healthy",
                "root_cause": "Recent deployment v2.4.1 introduced a connection pool issue in the gateway",
            },
        ),
        text_response(
            "Diagnosis complete: API Gateway has 12.3% error rate with 502 errors. "
            "User-service is healthy. Root cause is the v2.4.1 gateway deployment."
        ),
    ],
    # --- Budget exhausted: model keeps querying without diagnosis ------------
    "budget_exhausted": [
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "cpu_usage"}),
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "memory_usage"}),
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "latency_p99"}),
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "request_rate"}),
        # Never submits diagnosis — budget will be exhausted
        tool_call_response("query_metrics", {"service": "user-service", "metric": "cpu_usage"}),
    ],
    # --- Repeated action: same tool+args called twice -----------------------
    "repeated_action": [
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),  # repeated!
        tool_call_response("query_logs", {"service": "api-gateway", "timeframe": "last_15m"}),
        tool_call_response(
            "submit_diagnosis",
            {
                "diagnosis": "API Gateway error rate confirmed, logs indicate upstream timeouts",
                "root_cause": "Recent deployment caused upstream connection issues",
            },
        ),
        text_response(
            "Diagnosis complete: Repeated metric query was flagged. "
            "Diagnosis based on logs and available metrics."
        ),
    ],
    # --- Non-convergence: model loops without progress ----------------------
    "non_convergence": [
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),  # repeat detected
        text_response("Let me check the error rate again for api-gateway."),
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),  # and again
        text_response("I still need more data on api-gateway error rate."),
        # Will keep looping until budget exhausted
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),
        text_response("Let me check one more time."),
    ],
    # --- Submit diagnosis without external mutation (read-only check) -------
    "read_only_diagnosis": [
        tool_call_response("query_metrics", {"service": "api-gateway", "metric": "error_rate"}),
        tool_call_response("query_logs", {"service": "api-gateway", "timeframe": "last_15m"}),
        tool_call_response(
            "submit_diagnosis",
            {
                "diagnosis": "API Gateway incident confirmed with elevated error rate",
                "root_cause": "Deployment v2.4.1 introduced connection timeout issues",
            },
        ),
        text_response(
            "Diagnosis complete: API Gateway has 12.3% error rate. "
            "Logs show 502 Bad Gateway errors due to upstream timeouts. "
            "Root cause: recent deployment v2.4.1."
        ),
    ],
}

# ---------------------------------------------------------------------------
# User queries for each scenario
# ---------------------------------------------------------------------------

QUERIES: dict[str, str] = {
    "default": "There seems to be an incident with the API Gateway. Please investigate and diagnose the root cause.",
    "diagnosis_success": "There seems to be an incident with the API Gateway. Please investigate and diagnose the root cause.",
    "multi_service_diagnosis": "We're seeing user complaints about errors. Check the API Gateway and user-service for issues.",
    "budget_exhausted": "Investigate the API Gateway performance metrics and diagnose any issues.",
    "repeated_action": "Check the API Gateway error rate and investigate the incident.",
    "non_convergence": "There's a problem with api-gateway. Find the root cause.",
    "read_only_diagnosis": "Investigate the API Gateway incident and submit a diagnosis.",
}
