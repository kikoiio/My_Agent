"""HTML report generator for evaluation results."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = ["EvalReport", "generate_html_report"]


@dataclass
class EvalResult:
    """Single evaluation result."""

    case_id: str
    category: str
    persona: str
    input_text: str
    output_text: str
    expected_text: str
    judge_verdicts: list[dict[str, Any]]
    passed: bool
    trace_id: str | None = None


class EvalReport:
    """Structured evaluation report."""

    def __init__(self, title: str = "Evaluation Report"):
        """Initialize report.

        Args:
            title: Report title
        """
        self.title = title
        self.results: list[EvalResult] = []
        self.created_at = datetime.now().isoformat()

    def add_result(self, result: EvalResult) -> None:
        """Add evaluation result."""
        self.results.append(result)

    def summary(self) -> dict[str, Any]:
        """Get report summary statistics."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        by_category = {}
        for result in self.results:
            cat = result.category
            if cat not in by_category:
                by_category[cat] = {"total": 0, "passed": 0}
            by_category[cat]["total"] += 1
            if result.passed:
                by_category[cat]["passed"] += 1

        return {
            "total_cases": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
            "by_category": by_category,
            "created_at": self.created_at,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "created_at": self.created_at,
            "summary": self.summary(),
            "results": [asdict(r) for r in self.results],
        }

    def save_json(self, output_file: Path | str) -> None:
        """Save report as JSON."""
        Path(output_file).write_text(
            json.dumps(self.to_dict(), indent=2),
            encoding="utf-8",
        )


def generate_html_report(
    report: EvalReport,
    output_file: Path | str = "eval_report.html",
) -> Path:
    """Generate HTML report from evaluation results.

    Args:
        report: EvalReport instance
        output_file: Output file path

    Returns:
        Path to generated report
    """
    summary = report.summary()
    pass_rate = summary["pass_rate"]
    pass_rate_class = (
        "status-ok" if pass_rate >= 80 else "status-warn" if pass_rate >= 50 else "status-error"
    )

    # Build results table
    results_table = ""
    for result in report.results:
        verdict_class = "passed" if result.passed else "failed"
        verdict_text = "PASS" if result.passed else "FAIL"
        avg_score = (
            sum(v.get("score", 0) for v in result.judge_verdicts) / len(result.judge_verdicts)
            if result.judge_verdicts
            else 0
        )

        results_table += f"""    <tr>
        <td>{result.case_id}</td>
        <td>{result.category}</td>
        <td>{result.persona}</td>
        <td class="{verdict_class}">{verdict_text}</td>
        <td>{avg_score:.2f}</td>
        <td><code>{result.trace_id[:12] if result.trace_id else 'N/A'}...</code></td>
    </tr>
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report.title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; }}
        header {{ background: #2c3e50; color: white; padding: 30px 20px; }}
        header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        header p {{ opacity: 0.8; }}
        .container {{ max-width: 1200px; margin: 20px auto; padding: 0 20px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
        .summary-card {{ background: white; padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-card h3 {{ font-size: 14px; color: #666; margin-bottom: 10px; }}
        .summary-card .value {{ font-size: 32px; font-weight: bold; }}
        .summary-card.ok .value {{ color: #27ae60; }}
        .summary-card.warn .value {{ color: #f39c12; }}
        .summary-card.error .value {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; background: white; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #ecf0f1; font-weight: 600; }}
        tr:hover {{ background: #f9f9f9; }}
        .passed {{ color: #27ae60; font-weight: bold; }}
        .failed {{ color: #e74c3c; font-weight: bold; }}
        code {{ background: #f0f0f0; padding: 2px 4px; border-radius: 3px; font-family: monospace; }}
        footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; margin-top: 40px; }}
    </style>
</head>
<body>
    <header>
        <h1>{report.title}</h1>
        <p>Generated: {report.created_at}</p>
    </header>

    <div class="container">
        <!-- Summary Cards -->
        <div class="summary-grid">
            <div class="summary-card">
                <h3>Total Cases</h3>
                <div class="value">{summary['total_cases']}</div>
            </div>
            <div class="summary-card ok">
                <h3>Passed</h3>
                <div class="value">{summary['passed']}</div>
            </div>
            <div class="summary-card error">
                <h3>Failed</h3>
                <div class="value">{summary['failed']}</div>
            </div>
            <div class="summary-card {pass_rate_class}">
                <h3>Pass Rate</h3>
                <div class="value">{pass_rate:.1f}%</div>
            </div>
        </div>

        <!-- Results Table -->
        <h2>Results by Case</h2>
        <table>
            <thead>
                <tr>
                    <th>Case ID</th>
                    <th>Category</th>
                    <th>Persona</th>
                    <th>Result</th>
                    <th>Judge Score</th>
                    <th>Trace ID</th>
                </tr>
            </thead>
            <tbody>
{results_table}            </tbody>
        </table>

        <!-- Category Breakdown -->
        <h2>Results by Category</h2>
        <table>
            <thead>
                <tr>
                    <th>Category</th>
                    <th>Total</th>
                    <th>Passed</th>
                    <th>Pass Rate</th>
                </tr>
            </thead>
            <tbody>
"""

    for category, stats in summary["by_category"].items():
        cat_pass_rate = (
            stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
        )
        html_content += f"""            <tr>
                <td>{category}</td>
                <td>{stats['total']}</td>
                <td><span class="passed">{stats['passed']}</span></td>
                <td>{cat_pass_rate:.1f}%</td>
            </tr>
"""

    html_content += """            </tbody>
        </table>
    </div>

    <footer>
        <p>Multi-Persona Voice Agent | Evaluation Report</p>
    </footer>
</body>
</html>
"""

    output_path = Path(output_file)
    output_path.write_text(html_content, encoding="utf-8")
    return output_path
