"""Single judge runner for evaluation verdict."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["JudgeVerdict", "run_judge"]


@dataclass
class JudgeVerdict:
    """Result of judge evaluation."""

    judge_id: str
    trace_id: str
    score: float  # 0.0 - 1.0
    verdict: str  # "pass", "fail", "uncertain"
    reasoning: str
    rubric_scores: dict[str, float] | None = None


class Judge:
    """Base class for evaluators."""

    def __init__(self, judge_id: str, model: str, llm_call: Any):
        """Initialize judge.

        Args:
            judge_id: Unique judge identifier
            model: LLM model name
            llm_call: Callable to invoke LLM
        """
        self.judge_id = judge_id
        self.model = model
        self.llm_call = llm_call

    async def evaluate(
        self,
        trace_id: str,
        input_text: str,
        output_text: str,
        expected: str = "",
        rubric: dict[str, str] | None = None,
    ) -> JudgeVerdict:
        """Evaluate a single case.

        Args:
            trace_id: Trace ID for tracking
            input_text: Original input
            output_text: Agent output
            expected: Expected output (optional)
            rubric: Evaluation rubric (optional)

        Returns:
            Judge verdict
        """
        # Build evaluation prompt
        eval_prompt = self._build_prompt(
            input_text=input_text,
            output_text=output_text,
            expected=expected,
            rubric=rubric,
        )

        # Call LLM for evaluation
        system_msg = """You are an expert evaluator. Assess the given agent response.
Respond with JSON: {
    "score": <0.0-1.0>,
    "verdict": "<pass|fail|uncertain>",
    "reasoning": "<brief explanation>"
}"""

        try:
            import asyncio

            response = await asyncio.to_thread(
                self.llm_call,
                system_msg,
                eval_prompt,
            )

            # Parse response
            import json

            parsed = json.loads(response)
            score = parsed.get("score", 0.5)
            verdict = parsed.get("verdict", "uncertain")
            reasoning = parsed.get("reasoning", "")
        except Exception as e:
            score = 0.5
            verdict = "uncertain"
            reasoning = f"Evaluation error: {str(e)}"

        return JudgeVerdict(
            judge_id=self.judge_id,
            trace_id=trace_id,
            score=score,
            verdict=verdict,
            reasoning=reasoning,
        )

    def _build_prompt(
        self,
        input_text: str,
        output_text: str,
        expected: str,
        rubric: dict[str, str] | None,
    ) -> str:
        """Build evaluation prompt."""
        prompt = f"""Evaluate the following agent response:

INPUT: {input_text}

AGENT OUTPUT: {output_text}"""

        if expected:
            prompt += f"\n\nEXPECTED OUTPUT: {expected}"

        if rubric:
            prompt += "\n\nRUBRIC:"
            for criterion, description in rubric.items():
                prompt += f"\n  {criterion}: {description}"

        prompt += "\n\nProvide a score (0.0-1.0), verdict, and reasoning."
        return prompt


async def run_judge(
    judge_id: str,
    model: str,
    trace_id: str,
    input_text: str,
    output_text: str,
    expected: str = "",
    llm_call: Any = None,
) -> JudgeVerdict:
    """Run single judge evaluation (convenience function).

    Args:
        judge_id: Judge identifier
        model: Model name
        trace_id: Trace ID
        input_text: Original input
        output_text: Agent response
        expected: Expected output
        llm_call: LLM callable

    Returns:
        Judge verdict
    """
    judge = Judge(judge_id=judge_id, model=model, llm_call=llm_call)
    return await judge.evaluate(
        trace_id=trace_id,
        input_text=input_text,
        output_text=output_text,
        expected=expected,
    )
