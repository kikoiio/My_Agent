"""Pytest-based evaluation harness.

Per plan.md §8.2-8.4:
- Load YAML test cases from eval/cases/
- Run each case through agent
- Invoke 5-LLM jury for evaluation
- Generate HTML report
"""

from __future__ import annotations

import asyncio
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
    agent_func: Any = None,
    jury: Any = None,
) -> dict[str, Any]:
    """Standalone eval runner.

    Args:
        cases_dir: Path to cases directory
        category: Optional category filter
        agent_func: Optional async agent function (persona, input_text) -> (response, _, trace_id)
        jury: Optional JudgeEnsemble instance

    Returns:
        Summary dict with results
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

    # If agent and jury are available, run real evaluation
    if agent_func and jury:
        return _run_with_async(harness, cases, agent_func, jury)

    # Fallback: load cases only, mark as pending (not failed)
    return {
        "total": len(cases),
        "passed": 0,
        "failed": 0,
        "pending": len(cases),
        "cases_loaded": [c.get("id") for c in cases],
        "message": "Provide agent_func and jury to run real evaluation",
    }


def _run_with_async(
    harness: EvaluationHarness,
    cases: list[dict[str, Any]],
    agent_func: Any,
    jury: Any,
) -> dict[str, Any]:
    """Bridge sync->async for running evaluation."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        import concurrent.futures
        import threading

        result_container = {}
        error_container = {}

        def run_in_thread():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result_container["result"] = new_loop.run_until_complete(
                    _run_cases_async(harness, cases, agent_func, jury)
                )
            except Exception as e:
                error_container["error"] = e
            finally:
                new_loop.close()

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        thread.join()

        if "error" in error_container:
            raise error_container["error"]
        return result_container.get("result", {})

    return asyncio.run(_run_cases_async(harness, cases, agent_func, jury))


async def _run_cases_async(
    harness: EvaluationHarness,
    cases: list[dict[str, Any]],
    agent_func: Any,
    jury: Any,
) -> dict[str, Any]:
    """Execute all cases through agent + jury."""
    passed = 0
    failed = 0
    results = []

    for case in cases:
        try:
            input_text = ""
            expected = ""
            persona = "default"

            # Extract from turns format
            turns = case.get("turns", [])
            for turn in turns:
                if turn.get("role") == "user":
                    input_text = turn.get("content", "")
                    break
            # Fallback to direct fields
            if not input_text:
                input_text = case.get("input", "")
            expected = case.get("expected", "")

            try:
                response, _, trace_id = await agent_func(persona, input_text)
            except Exception:
                response = f"[Agent error for case {case.get('id', 'unknown')}]"
                trace_id = "error"

            # Evaluate with jury
            try:
                verdict = await jury.evaluate(
                    trace_id=trace_id,
                    input_text=input_text,
                    output_text=response,
                    expected=expected,
                )
                is_pass = verdict.final_verdict == "pass"
            except Exception:
                is_pass = False
                verdict = None

            result = {
                "case_id": case.get("id", "unknown"),
                "category": case.get("category", "unknown"),
                "input": input_text,
                "output": response,
                "expected": expected,
                "trace_id": trace_id,
                "jury_score": verdict.final_score if verdict else 0.0,
                "jury_verdict": verdict.final_verdict if verdict else "error",
                "confidence": verdict.confidence if verdict else 0.0,
                "passed": is_pass,
            }

            if is_pass:
                passed += 1
            else:
                failed += 1

            results.append(result)
            harness.results.append(result)

        except Exception as e:
            logger.error(f"Case {case.get('id', 'unknown')} failed: {e}")
            failed += 1
            harness.results.append(
                {
                    "case_id": case.get("id", "unknown"),
                    "category": case.get("category", "unknown"),
                    "error": str(e),
                    "passed": False,
                }
            )

    return {
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "results": results,
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


def test_eval_case(eval_case: dict[str, Any]) -> None:
    """Run a single YAML test case against the evaluation framework.

    Loads the case, extracts input, and verifies case structure is valid.
    When agent and jury are wired in, this will execute full evaluation.
    """
    case_id = eval_case.get("id", "unknown")
    category = eval_case.get("category", "unknown")
    assertions = eval_case.get("assertions", [])

    # Validate case structure
    assert case_id, "Case must have an id"
    assert category, "Case must have a category"

    # Check for any valid input format (turns, input, mock_external_input, setup)
    has_input = bool(
        eval_case.get("turns")
        or eval_case.get("input")
        or eval_case.get("mock_external_input")
        or eval_case.get("setup")
    )
    assert has_input, f"Case {case_id} must have turns, input, mock_external_input, or setup"

    # Validate assertions have required fields
    for a in assertions:
        assert a.get("type"), f"Case {case_id}: assertion must have a type"
        if a["type"] == "llm_judge":
            assert a.get("criteria"), f"Case {case_id}: llm_judge requires criteria"
            assert a.get("threshold"), f"Case {case_id}: llm_judge requires threshold"


def test_harness_initialization():
    """Test that harness initializes correctly."""
    harness_obj = EvaluationHarness()
    assert harness_obj.cases_dir.name == "cases"
    assert harness_obj.judges_dir.name == "judges"
