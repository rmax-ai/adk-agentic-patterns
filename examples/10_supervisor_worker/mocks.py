"""Mock worker services for Pattern 10: Supervisor-Worker.

Simulates specialist workers that perform product-launch review tasks.
Each worker has isolated capabilities and cannot modify tasks belonging
to other workers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MockMarketWorker:
    """Mock market-analysis specialist worker.

    Capabilities: market_analysis, competitor_intel, pricing_review
    """

    analyses: dict[str, dict] = field(default_factory=dict)

    def analyze_market(self, product: str) -> dict:
        """Analyze market conditions for a product.

        Args:
            product: Product name to analyze.

        Returns:
            Dict with market analysis results.
        """
        key = f"market:{product}"
        result = {
            "product": product,
            "market_size": "$500M TAM",
            "growth_rate": "12% YoY",
            "competitive_position": "strong",
            "recommendation": "proceed",
        }
        self.analyses[key] = result
        return result

    def review_pricing(self, product: str, proposed_price: float) -> dict:
        """Review proposed pricing for a product.

        Args:
            product: Product name.
            proposed_price: Proposed price point.

        Returns:
            Dict with pricing review results.
        """
        return {
            "product": product,
            "proposed_price": proposed_price,
            "competitive_analysis": "within market range",
            "margin_estimate": "38%",
            "recommendation": "approved",
        }

    def competitor_intel(self, product: str) -> dict:
        """Gather competitor intelligence for a product.

        Args:
            product: Product name.

        Returns:
            Dict with competitor intel.
        """
        return {
            "product": product,
            "competitors": ["Competitor A", "Competitor B"],
            "market_share_estimate": "15%",
            "differentiation": "strong",
        }


@dataclass
class MockTechWorker:
    """Mock technical-review specialist worker.

    Capabilities: technical_review, security_audit, performance_benchmark
    """

    reviews: dict[str, dict] = field(default_factory=dict)

    def review_technical(self, product: str) -> dict:
        """Perform a technical review of a product.

        Args:
            product: Product name.

        Returns:
            Dict with technical review results.
        """
        key = f"tech:{product}"
        result = {
            "product": product,
            "architecture_score": 8.5,
            "code_quality": "good",
            "tech_debt": "low",
            "recommendation": "ready",
        }
        self.reviews[key] = result
        return result

    def security_audit(self, product: str) -> dict:
        """Perform a security audit.

        Args:
            product: Product name.

        Returns:
            Dict with security audit results.
        """
        return {
            "product": product,
            "vulnerabilities_found": 2,
            "critical": 0,
            "high": 1,
            "medium": 1,
            "overall_risk": "low",
        }

    def performance_benchmark(self, product: str) -> dict:
        """Run performance benchmarks.

        Args:
            product: Product name.

        Returns:
            Dict with benchmark results.
        """
        return {
            "product": product,
            "p99_latency_ms": 120,
            "throughput_rps": 5000,
            "memory_footprint_mb": 256,
            "status": "pass",
        }


@dataclass
class MockComplianceWorker:
    """Mock compliance-review specialist worker.

    Capabilities: compliance_check, regulatory_review, data_privacy
    """

    checks: dict[str, dict] = field(default_factory=dict)

    def check_compliance(self, product: str, region: str = "global") -> dict:
        """Check compliance requirements for a product.

        Args:
            product: Product name.
            region: Target region (default: global).

        Returns:
            Dict with compliance check results.
        """
        key = f"compliance:{product}:{region}"
        result = {
            "product": product,
            "region": region,
            "compliance_status": "pass",
            "requirements_met": ["GDPR", "CCPA", "SOC2"],
            "pending_items": [],
        }
        self.checks[key] = result
        return result

    def regulatory_review(self, product: str) -> dict:
        """Perform regulatory review.

        Args:
            product: Product name.

        Returns:
            Dict with regulatory review results.
        """
        return {
            "product": product,
            "regulatory_status": "compliant",
            "jurisdictions": ["US", "EU", "APAC"],
            "filing_required": False,
        }

    def data_privacy_review(self, product: str) -> dict:
        """Review data privacy aspects.

        Args:
            product: Product name.

        Returns:
            Dict with data privacy review results.
        """
        return {
            "product": product,
            "data_collection": "minimal",
            "user_consent": "obtained",
            "encryption": "AES-256",
            "status": "pass",
        }


@dataclass
class MockLaunchWorker:
    """Mock launch-coordination specialist worker.

    Capabilities: launch_readiness, go_to_market
    """

    plans: dict[str, dict] = field(default_factory=dict)

    def assess_readiness(self, product: str) -> dict:
        """Assess overall launch readiness.

        Args:
            product: Product name.

        Returns:
            Dict with readiness assessment.
        """
        key = f"launch:{product}"
        result = {
            "product": product,
            "readiness_score": 92,
            "marketing_ready": True,
            "sales_trained": True,
            "support_prepared": True,
            "recommendation": "launch",
        }
        self.plans[key] = result
        return result

    def go_to_market(self, product: str) -> dict:
        """Create go-to-market plan summary.

        Args:
            product: Product name.

        Returns:
            Dict with GTM plan.
        """
        return {
            "product": product,
            "launch_date": "2026-08-15",
            "channels": ["web", "enterprise_sales", "partners"],
            "budget_allocated": 250000,
            "target_audience": "mid-market",
        }
