"""Tests for detection evaluation harness."""
import json


def test_evaluator_scores_expected_vs_actual_results(tmp_path):
    from app.schemas import AnalysisResult
    from app.services.detection_evaluation import DetectionEvaluator

    dataset = tmp_path / "samples.jsonl"
    rows = [
        {
            "sample_id": "safe-1",
            "expected_status": "safe",
            "expected_event_type": None,
            "actual": {"status": "safe", "confidence": 0.9},
        },
        {
            "sample_id": "face-down-1",
            "expected_status": "alert",
            "expected_event_type": "face_down",
            "actual": {
                "status": "alert",
                "event_type": "face_down",
                "confidence": 0.92,
            },
        },
        {
            "sample_id": "blanket-1",
            "expected_status": "alert",
            "expected_event_type": "blanket_over_face",
            "actual": {"status": "safe", "confidence": 0.6},
        },
    ]
    dataset.write_text("\n".join(json.dumps(row) for row in rows))

    evaluator = DetectionEvaluator()
    report = evaluator.evaluate_jsonl(
        dataset,
        actual_result_factory=lambda row: AnalysisResult(**row["actual"]),
    )

    assert report.total == 3
    assert report.true_positives == 1
    assert report.true_negatives == 1
    assert report.false_negatives == 1
    assert report.false_positives == 0
    assert report.recall == 0.5
    assert report.precision == 1.0
    assert report.accuracy == 2 / 3
    assert report.misses == ["blanket-1"]
