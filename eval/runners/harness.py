"""Pytest-based evaluation harness.

Per plan.md §8.2-8.4:
- Load YAML test cases from eval/cases/
- Run each case through agent
- Invoke 5-LLM jury for evaluation
- Generate HTML report
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

__all__ = ["EvaluationHarness", "run_eval", "pytest_generate_tests"]

logger = logging.getLogger(__name__)


class EvaluationHarness:
    """Main evaluation harness."""

    def __init__(
        self,
        cases_dir: Path | str = "eval/cases",
        judges_dir: Path | str = "eval/runners/judges",
        fixtures_dir: Path | str = "eval/fixtures",
    ):
        """Initialize harness.

        Args:
            cases_dir: Directory containing YAML test cases
            judges_dir: Directory containing judge definitions
            fixtures_dir: Directory containing test fixtures
        """
        self.cases_dir = Path(cases_dir)
        self.judges_dir = Path(judges_dir)
        self.fixtures_dir = Path(fixtures_dir)
        self.results = []

    def load_cases(self, category: str | None = None) -> list[dict[str, Any]]:
        """Load all YAML test cases.

        Args:
            category: Optional category filter (e.g., 'core', 'security', 'persona')

        Returns:
            List of loaded test case dicts
        """
        cases = []
        if not self.cases_dir.exists():
            logger.warning(f"Cases directory not found: {self.cases_dir}")
            return cases

        for yaml_file in self.cases_dir.glob("**/*.yaml"):
            if category and not str(yaml_file).count(category):
                continue

            try:
                import yaml

                content = yaml_file.read_text(encoding="utf-8")
                case = yaml.safe_load(content)
                if case:
                    case["_file"] = str(yaml_file)
                    cases.append(case)
            except Exception as e:
                logger.error(f"Failed to load {yaml_file}: {e}")

        return cases

    async def run_case(
        self,
        case: dict[str, Any],
        agent_func: Any,
    ) -> dict[str, Any]:
        """Run single test case through agent.

        Args:
            case: Test case dict with 'input', 'expected', etc.
            agent_func: Async agent function (state, user_msg) -> (response, new_state, trace_id)

        Returns:
            Result dict with 'case', 'output', 'judge_verdicts', 'passed'
        """
        try:
            # Extract case fields
            input_text = case.get("input", "")
            expected_output = case.get("expected", "")
            persona = case.get("persona", "default")

            # Run agent
            response, _, trace_id = await agent_func(persona, input_text)

            # Store result
            result = {
                "case_id": case.get("id", "unknown"),
                "category": case.get("category", "unknown"),
                "input": input_text,
                "output": response,
                "expected": expected_output,
                "trace_id": trace_id,
                "judge_verdicts": [],
                "passed": False,
            }

            return result
        except Exception as e:
            logger.error(f"Case execution failed: {e}")
            return {
                "case_id": case.get("id", "unknown"),
                "category": case.get("category", "unknown"),
                "error": str(e),
                "passed": False,
            }

    def generate_report(self, output_file: Path | str = "eval_report.html") -> Path:
        """Generate HTML report from results.

        Returns:
            Path to generated report
        """
        output_path = Path(output_file)

        # Build HTML
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Evaluation Report</title>
    <style>
        body {{ font-family: sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #2c3e50; }}
        table {{ border-collapse: collapse; width: 100%; background: white; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background: #ecf0f1; font-weight: bold; }}
        tr:hover {{ background: #f9f9f9; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
        code {{ background: #f0f0f0; padding: 2px 4px; border-radius: 3px; }}
    </style>
</head>
<body>
    <h1>Evaluation Report</h1>
    <p>Total cases: {len(self.results)}</p>
    <p>Passed: {sum(1 for r in self.results if r.get('passed'))}</p>
    <table>
        <thead>
            <tr>
                <th>Case ID</th>
                <th>Category</th>
                <th>Result</th>
                <th>Trace ID</th>
            </tr>
        </thead>
        <tbody>
"""

        for result in self.results:
            status_class = "passed" if result.get("passed") else "failed"
            status_text = "PASS" if result.get("passed") else "FAIL"
            html_content += f"""            <tr>
                <td>{result.get('case_id', 'N/A')}</td>
                <td>{result.get('category', 'N/A')}</td>
                <td class="{status_class}">{status_text}</td>
                <td><code>{result.get('trace_id', 'N/A')[:12]}...</code></td>
            </tr>
"""

        html_content += """        </tbody>
    </table>
</body>
</html>
"""

        output_path.write_text(html_content, encoding="utf-8")
        logger.info(f"Report generated: {output_path}")
        return output_path


def run_eval(
    cases_dir: str = "eval/cases",
    category: str | None = None,
) -> dict[str, Any]:
    """Standalone eval runner (pytest entry point).

    Args:
        cases_dir: Path to cases directory
        category: Optional category filter

    Returns:
        Summary dict
    """
    harness = EvaluationHarness(cases_dir=cases_dir)
    cases = harness.load_cases(category=category)

    if not cases:
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "error": "No test cases found",
        }

    return {
        "total": len(cases),
        "passed": 0,
        "failed": len(cases),
        "cases_loaded": [c.get("id") for c in cases],
    }


# Pytest integration
def pytest_generate_tests(metafunc):
    """Pytest hook to generate parameterized tests from YAML cases."""
    if "eval_case" in metafunc.fixturenames:
        harness = EvaluationHarness()
        cases = harness.load_cases()

        if cases:
            case_ids = [c.get("id", f"case_{i}") for i, c in enumerate(cases)]
            metafunc.parametrize("eval_case", cases, ids=case_ids)


@pytest.fixture
def harness():
    """Fixture for evaluation harness."""
    return EvaluationHarness()


# Dummy test to satisfy pytest (can be run with `pytest eval/runners/harness.py`)
def test_harness_initialization():
    """Test that harness initializes correctly."""
    harness = EvaluationHarness()
    assert harness.cases_dir.name == "cases"
    assert harness.judges_dir.name == "judges"
