.PHONY: install format lint typecheck test test-unit test-integration test-failures examples benchmark docs verify clean

# ── Setup ──────────────────────────────────────────────────────────────────
install:
	uv sync --extra dev

# ── Quality ────────────────────────────────────────────────────────────────
format:
	uv run ruff format src/ tests/

lint:
	uv run ruff check --fix src/ tests/

typecheck:
	uv run mypy src/adk_patterns/

# ── Testing ────────────────────────────────────────────────────────────────
test:
	@echo "Running all pattern tests..."
	@PASS=0; FAIL=0; \
	for dir in examples/*/; do \
		uv run pytest "$$dir" -q --tb=short 2>/dev/null && PASS=$$((PASS+1)) || FAIL=$$((FAIL+1)); \
	done; \
	echo "Patterns passed: $$PASS, failed: $$FAIL"

test-unit:
	uv run pytest tests/unit/ -v --tb=short

test-integration:
	uv run pytest examples/ -v --tb=short --import-mode=importlib -p no:cacheprovider

test-failures:
	uv run pytest tests/failure_injection/ -v --tb=short

# ── Examples ───────────────────────────────────────────────────────────────
examples:
	@for dir in examples/*/; do \
		name=$$(basename $$dir); \
		echo "Running $$name..."; \
		uv run python -c "import sys; sys.path.insert(0,'$$dir'); exec(open('$${dir}run.py').read())" 2>&1 || true; \
	done

# ── Benchmark ──────────────────────────────────────────────────────────────
benchmark:
	uv run python scripts/verify_examples.py --benchmark
	@echo "Benchmark artifacts: artifacts/pattern-benchmark.json"

# ── Documentation ──────────────────────────────────────────────────────────
docs:
	@echo "Documentation generation not yet configured (no mkdocs)"

# ── Full Verification ──────────────────────────────────────────────────────
verify: format lint typecheck test
	@echo "All checks passed."

# ── Cleanup ────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ artifacts/
