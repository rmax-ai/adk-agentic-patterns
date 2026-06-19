"""Fixtures for Pattern 12: Shared Workspace / Blackboard.

Provides scripted model responses for claim contributions and synthesis.
"""

from __future__ import annotations

from adk_patterns.models import structured_response

FIXTURES = {
    "claim_researcher_01": structured_response(
        {
            "id": "claim_001",
            "author": "researcher_01",
            "text": "The Arctic sea ice extent has declined at an average rate of 13% per decade since 1979.",
            "evidence": "NSIDC Sea Ice Index, Satellite observations 1979-2024",
            "confidence": 0.92,
            "status": "pending",
            "version": 1,
        }
    ),
    "claim_researcher_02": structured_response(
        {
            "id": "claim_002",
            "author": "researcher_02",
            "text": "Atmospheric CO2 concentrations exceeded 420 ppm in 2024, the highest in recorded history.",
            "evidence": "NOAA Mauna Loa Observatory, Keeling Curve data 2024",
            "confidence": 0.98,
            "status": "pending",
            "version": 1,
        }
    ),
    "claim_researcher_03": structured_response(
        {
            "id": "claim_003",
            "author": "researcher_03",
            "text": "Global average temperature in 2024 was 1.45°C above pre-industrial levels.",
            "evidence": "WMO State of the Global Climate 2024 Report",
            "confidence": 0.88,
            "status": "pending",
            "version": 1,
        }
    ),
    "synthesizer_output": structured_response(
        {
            "summary": (
                "The evidence board shows strong consensus on three key climate indicators: "
                "Arctic sea ice decline (13%/decade), record CO2 levels (>420 ppm), "
                "and global temperature rise (1.45°C above pre-industrial). "
                "All claims show high confidence (>0.85)."
            ),
            "accepted_count": 3,
            "claim_ids": ["claim_001", "claim_002", "claim_003"],
        }
    ),
}
