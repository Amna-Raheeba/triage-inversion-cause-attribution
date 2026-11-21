from triage_inversion.evaluate import (
    check_drift,
    merge_scores,
    run_evaluation,
    score_predictions,
)
from triage_inversion.models import Inversion

SMALL = {"n_days": 6, "base_seed": 777, "repair_days": 3, "fifo_days": 3}


def _inv(victim, beneficiary, time, cause):
    return Inversion(
        victim=victim, beneficiary=beneficiary, time=time, cause=cause,
        victim_service_acuity=2, beneficiary_service_acuity=4,
        excess_wait_minutes=10,
    )


def test_score_predictions_perfect():
    truth = [_inv("V", "B", 50, "retriage_lag")]
    scores = score_predictions(truth, [], list(truth))
    assert scores["per_cause"]["retriage_lag"]["precision"] == 1.0
    assert scores["per_cause"]["retriage_lag"]["recall"] == 1.0
    assert scores["overall_label_accuracy"] == 1.0


def test_score_predictions_wrong_cause():
    truth = [_inv("V", "B", 50, "retriage_lag")]
    predicted = [_inv("V", "B", 50, "batch_reassessment_timing")]
    scores = score_predictions(truth, [], predicted)
    assert scores["per_cause"]["retriage_lag"]["recall"] == 0.0
    assert scores["per_cause"]["batch_reassessment_timing"]["precision"] == 0.0
    assert scores["overall_label_accuracy"] == 0.0


def test_score_predictions_post_hoc_fp():
    apparent = [_inv("V", "B", 50, "post_hoc_deterioration")]
    predicted = [_inv("V", "B", 50, "batch_reassessment_timing")]
    scores = score_predictions([], apparent, predicted)
    assert scores["apparent_declined_rate"] == 0.0
    assert scores["per_cause"]["batch_reassessment_timing"]["fp"] == 1


def test_merge_scores_sums_counts():
    truth = [_inv("V", "B", 50, "retriage_lag")]
    one = score_predictions(truth, [], list(truth))
    merged = merge_scores([one, one])
    assert merged["per_cause"]["retriage_lag"]["tp"] == 2
    assert merged["overall_label_accuracy"] == 1.0


def test_run_evaluation_small_config():
    evaluation = run_evaluation(SMALL)
    agg = evaluation["aggregates"]
    assert agg["n_days"] == 6
    assert agg["n_patients"] > 0
    assert agg["n_truth_inversions"] > 0
    assert 0.0 <= agg["detector_overall_accuracy"] <= 1.0
    assert evaluation["fifo"]["days"] == 3
    assert set(evaluation["repairs"]["repairs"]) == {
        "prompt_retriage", "frequent_batch", "fasttrack_guard"
    }


def test_check_drift_identical():
    evaluation = run_evaluation(SMALL)
    ok, problems = check_drift(evaluation, evaluation)
    assert ok
    assert problems == []


def test_check_drift_detects_change():
    evaluation = run_evaluation(SMALL)
    tampered = {"aggregates": dict(evaluation["aggregates"])}
    tampered["aggregates"]["n_truth_inversions"] += 1
    ok, problems = check_drift(evaluation, tampered)
    assert not ok
    assert problems
