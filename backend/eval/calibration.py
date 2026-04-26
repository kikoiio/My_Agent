"""Calibration: gold-standard blind probe + weight update.

Per plan.md §8.4.2: Run probes where ground truth is known,
track each judge's hit rate, update weights via multiplicative update.
weight *= 1.01 on hit, weight *= 0.97 on miss, clamped [0.5, 1.5].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["CalibrationProbe", "Calibrator"]


@dataclass
class CalibrationProbe:
    """Single gold-standard evaluation probe."""

    probe_id: str
    input_text: str
    output_text: str
    ground_truth_verdict: str  # "pass" or "fail"
    category: str  # "security", "persona", "smoke", etc.
    explanation: str = ""


@dataclass
class CalibrationResult:
    """Result of running a probe."""

    probe_id: str
    judge_id: str
    predicted_verdict: str
    correct: bool
    confidence: float
    weight_delta: float = 0.0

    @property
    def is_hit(self) -> bool:
        return self.correct


class Calibrator:
    """Judge calibration using blind probes."""

    # Constants for multiplicative weight update
    HIT_MULTIPLIER = 1.01  # Weight increases on correct prediction
    MISS_MULTIPLIER = 0.97  # Weight decreases on wrong prediction
    WEIGHT_MIN = 0.5
    WEIGHT_MAX = 1.5

    def __init__(self, judges: list[Any] | None = None):
        """Initialize calibrator.

        Args:
            judges: List of Judge instances to calibrate
        """
        self.judges = judges or []
        self.judge_weights: dict[str, float] = {j.judge_id: 1.0 for j in self.judges}
        self.probe_history: list[CalibrationResult] = []

    async def run_probe(
        self,
        probe: CalibrationProbe,
    ) -> dict[str, Any]:
        """Run single probe against all judges.

        Args:
            probe: Calibration probe with known ground truth

        Returns:
            Dict of {judge_id: CalibrationResult}
        """
        results = {}

        for judge in self.judges:
            # Run evaluation
            verdict = await judge.evaluate(
                trace_id=probe.probe_id,
                input_text=probe.input_text,
                output_text=probe.output_text,
            )

            # Check correctness
            is_correct = verdict.verdict == probe.ground_truth_verdict

            # Calculate new weight
            old_weight = self.judge_weights[judge.judge_id]
            multiplier = self.HIT_MULTIPLIER if is_correct else self.MISS_MULTIPLIER
            new_weight = old_weight * multiplier
            new_weight = max(self.WEIGHT_MIN, min(self.WEIGHT_MAX, new_weight))
            weight_delta = new_weight - old_weight

            self.judge_weights[judge.judge_id] = new_weight

            # Record result
            result = CalibrationResult(
                probe_id=probe.probe_id,
                judge_id=judge.judge_id,
                predicted_verdict=verdict.verdict,
                correct=is_correct,
                confidence=verdict.score,
                weight_delta=weight_delta,
            )
            results[judge.judge_id] = result
            self.probe_history.append(result)

        return results

    async def run_probes(
        self,
        probes: list[CalibrationProbe],
    ) -> dict[str, Any]:
        """Run all probes and update weights.

        Args:
            probes: List of calibration probes

        Returns:
            Summary of calibration results
        """
        for probe in probes:
            await self.run_probe(probe)

        # Compute summary stats
        return self.get_summary()

    def get_summary(self) -> dict[str, Any]:
        """Get calibration summary."""
        if not self.probe_history:
            return {
                "total_probes": 0,
                "judge_accuracies": {},
                "judge_weights": self.judge_weights.copy(),
            }

        # Compute per-judge accuracy
        by_judge: dict[str, list[bool]] = {}
        for result in self.probe_history:
            if result.judge_id not in by_judge:
                by_judge[result.judge_id] = []
            by_judge[result.judge_id].append(result.is_hit)

        judge_accuracies = {
            judge_id: sum(hits) / len(hits) if hits else 0.0
            for judge_id, hits in by_judge.items()
        }

        return {
            "total_probes": len(set(r.probe_id for r in self.probe_history)),
            "total_evaluations": len(self.probe_history),
            "judge_accuracies": judge_accuracies,
            "judge_weights": self.judge_weights.copy(),
        }

    def get_judge_weights(self) -> dict[str, float]:
        """Get current judge weights for ensemble voting."""
        return self.judge_weights.copy()

    def reset_weights(self) -> None:
        """Reset all weights to 1.0 (for testing or retraining)."""
        self.judge_weights = {j: 1.0 for j in self.judge_weights.keys()}
        self.probe_history = []
