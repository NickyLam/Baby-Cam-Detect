"""Offline detection evaluation helpers."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.schemas import AnalysisResult


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    misses: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def accuracy(self) -> float:
        return (
            (self.true_positives + self.true_negatives) / self.total
            if self.total
            else 0.0
        )


class DetectionEvaluator:
    """Score expected safety labels against actual analysis results."""

    def evaluate_jsonl(
        self,
        dataset_path: Path,
        actual_result_factory: Callable[[dict], AnalysisResult],
    ) -> EvaluationReport:
        true_positives = 0
        true_negatives = 0
        false_positives = 0
        false_negatives = 0
        misses: list[str] = []
        total = 0

        with Path(dataset_path).open() as handle:
            for line in handle:
                if not line.strip():
                    continue

                row = json.loads(line)
                total += 1
                sample_id = row["sample_id"]
                expected_status = row["expected_status"]
                expected_event_type = row.get("expected_event_type")
                actual = actual_result_factory(row)

                expected_alert = expected_status == "alert"
                actual_alert = actual.status == "alert"
                event_matches = actual.event_type == expected_event_type

                if expected_alert and actual_alert and event_matches:
                    true_positives += 1
                elif not expected_alert and not actual_alert:
                    true_negatives += 1
                elif not expected_alert and actual_alert:
                    false_positives += 1
                    misses.append(sample_id)
                else:
                    false_negatives += 1
                    misses.append(sample_id)

        return EvaluationReport(
            total=total,
            true_positives=true_positives,
            true_negatives=true_negatives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            misses=misses,
        )
