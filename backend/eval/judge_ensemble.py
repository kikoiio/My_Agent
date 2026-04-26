"""5-LLM jury protocol: independent scoring, debate, weighted aggregation.

Per plan.md §8.4: 5 independent judges score trace → debate round → aggregation.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

__all__ = ["JudgeEnsemble", "EnsembleVerdict"]


@dataclass
class IndividualVote:
    """Vote from a single judge."""

    judge_id: str
    score: float  # 0.0-1.0
    verdict: str  # "pass", "fail", "uncertain"
    reasoning: str
    weight: float = 1.0  # Learned weight from calibration


@dataclass
class EnsembleVerdict:
    """Final verdict from jury."""

    trace_id: str
    individual_votes: list[IndividualVote] = field(default_factory=list)
    debate_summary: str = ""
    final_score: float = 0.0
    final_verdict: str = "uncertain"
    confidence: float = 0.0  # How much judges agree


class JudgeEnsemble:
    """5-judge jury for evaluations."""

    def __init__(
        self,
        judges: list[Any],  # List of Judge instances
        debate_model: str = "gpt-4-turbo",
        debate_llm_call: Any = None,
    ):
        """Initialize ensemble.

        Args:
            judges: List of 5 Judge instances (different models)
            debate_model: Model for debate round
            debate_llm_call: Callable for debate phase
        """
        self.judges = judges
        self.debate_model = debate_model
        self.debate_llm_call = debate_llm_call

    async def evaluate(
        self,
        trace_id: str,
        input_text: str,
        output_text: str,
        expected: str = "",
        weights: dict[str, float] | None = None,
    ) -> EnsembleVerdict:
        """Run full ensemble evaluation (independent → debate → aggregate).

        Args:
            trace_id: Trace ID
            input_text: Original input
            output_text: Agent response
            expected: Expected output
            weights: Optional judge weights from calibration

        Returns:
            Final ensemble verdict
        """
        weights = weights or {}

        # Phase 1: Independent evaluation by all judges
        votes = await asyncio.gather(
            *[
                judge.evaluate(
                    trace_id=trace_id,
                    input_text=input_text,
                    output_text=output_text,
                    expected=expected,
                )
                for judge in self.judges
            ]
        )

        individual_votes = [
            IndividualVote(
                judge_id=vote.judge_id,
                score=vote.score,
                verdict=vote.verdict,
                reasoning=vote.reasoning,
                weight=weights.get(vote.judge_id, 1.0),
            )
            for vote in votes
        ]

        # Phase 2: Debate (optional, if debate callable provided)
        debate_summary = ""
        if self.debate_llm_call:
            debate_summary = await self._run_debate(individual_votes, input_text, output_text)

        # Phase 3: Weighted aggregation
        final_score, final_verdict, confidence = self._aggregate(individual_votes)

        return EnsembleVerdict(
            trace_id=trace_id,
            individual_votes=individual_votes,
            debate_summary=debate_summary,
            final_score=final_score,
            final_verdict=final_verdict,
            confidence=confidence,
        )

    async def _run_debate(
        self,
        votes: list[IndividualVote],
        input_text: str,
        output_text: str,
    ) -> str:
        """Run debate phase among judges.

        All judges see each other's scores and justifications,
        and update their verdicts in a second round if needed.
        """
        if not self.debate_llm_call:
            return ""

        # Prepare debate prompt
        votes_summary = "\n".join(
            f"{v.judge_id} (score={v.score:.2f}): {v.reasoning}" for v in votes
        )

        debate_prompt = f"""Given these initial evaluations:

{votes_summary}

INPUT: {input_text}
OUTPUT: {output_text}

Synthesize the verdicts into a consensus summary. Do judges agree?
Where do they disagree? What is the most likely truth?"""

        try:
            debate_response = await asyncio.to_thread(
                self.debate_llm_call,
                "You are synthesizing judge verdicts.",
                debate_prompt,
            )
            return debate_response
        except Exception as e:
            return f"Debate error: {str(e)}"

    @staticmethod
    def _aggregate(
        votes: list[IndividualVote],
    ) -> tuple[float, str, float]:
        """Aggregate weighted votes into final verdict.

        Args:
            votes: List of weighted individual votes

        Returns:
            (final_score, final_verdict, confidence)
        """
        if not votes:
            return 0.5, "uncertain", 0.0

        # Weighted average score
        total_weight = sum(v.weight for v in votes)
        weighted_score = sum(v.score * v.weight for v in votes) / total_weight if total_weight else 0.5

        # Weighted verdict (pass if avg score > 0.6)
        if weighted_score >= 0.6:
            final_verdict = "pass"
        elif weighted_score <= 0.4:
            final_verdict = "fail"
        else:
            final_verdict = "uncertain"

        # Confidence = how much judges agree (low variance = high confidence)
        score_variance = (
            sum((v.score - weighted_score) ** 2 for v in votes) / len(votes)
            if votes
            else 0
        )
        confidence = 1.0 - min(1.0, score_variance)  # 0.0 = low, 1.0 = high

        return weighted_score, final_verdict, confidence

    def get_verdict_dict(self, verdict: EnsembleVerdict) -> dict[str, Any]:
        """Serialize ensemble verdict."""
        return {
            "trace_id": verdict.trace_id,
            "final_score": verdict.final_score,
            "final_verdict": verdict.final_verdict,
            "confidence": verdict.confidence,
            "individual_votes": [
                {
                    "judge_id": v.judge_id,
                    "score": v.score,
                    "verdict": v.verdict,
                    "weight": v.weight,
                }
                for v in verdict.individual_votes
            ],
            "debate_summary": verdict.debate_summary,
        }
