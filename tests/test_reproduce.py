import json
import os

from triage_inversion.evaluate import DEFAULT_CONFIG, check_drift, run_evaluation

RESULTS = os.path.join(
    os.path.dirname(__file__), "..", "results", "evaluation.json"
)
DATA = os.path.join(os.path.dirname(__file__), "..", "data", "days.json")


def test_stored_results_reproduce():
    with open(RESULTS) as handle:
        stored = json.load(handle)
    fresh = run_evaluation()
    ok, problems = check_drift(stored, fresh)
    assert ok, problems


def test_stored_days_match_evaluation_seed_scheme():
    with open(DATA) as handle:
        corpus = json.load(handle)
    assert len(corpus["days"]) == 20
    base_seed = DEFAULT_CONFIG["base_seed"]
    for index, day in enumerate(corpus["days"]):
        assert day["seed"] == base_seed + index
        assert day["events"]
        assert day["inversions"]
