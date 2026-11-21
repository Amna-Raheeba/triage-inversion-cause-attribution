from triage_inversion.models import CAUSES, CAUSE_RESOURCE_FIT
from triage_inversion.simulate import simulate_day


def test_simulation_is_deterministic():
    day_a = simulate_day(day_index=0, seed=123)
    day_b = simulate_day(day_index=0, seed=123)
    assert day_a.events == day_b.events
    assert [i.to_dict() for i in day_a.inversions] == [i.to_dict() for i in day_b.inversions]


def test_different_seed_different_day():
    day_a = simulate_day(day_index=0, seed=123)
    day_b = simulate_day(day_index=0, seed=124)
    assert day_a.events != day_b.events


def test_all_patients_served():
    day = simulate_day(day_index=0, seed=99)
    assert day.stats["n_patients"] > 0
    assert day.stats["n_served"] == day.stats["n_patients"]


def test_events_are_chronological():
    day = simulate_day(day_index=0, seed=99)
    times = [event["time"] for event in day.events]
    assert times == sorted(times)


def test_log_has_no_ground_truth_fields():
    day = simulate_day(day_index=0, seed=99)
    for event in day.events:
        assert "true_acuity" not in event
        assert event["type"] != "deterioration"


def test_inversions_respect_pair_definition():
    day = simulate_day(day_index=0, seed=99)
    arrivals = dict(
        (pid, truth.arrival) for pid, truth in day.patients.items()
    )
    for inv in day.inversions:
        assert inv.cause in CAUSES
        assert arrivals[inv.victim] < arrivals[inv.beneficiary]
        assert inv.victim_service_acuity < inv.beneficiary_service_acuity
        assert inv.excess_wait_minutes >= 0


def test_apparent_pairs_are_post_hoc_labelled():
    day = simulate_day(day_index=0, seed=99)
    for inv in day.apparent_pairs:
        assert inv.cause == "post_hoc_deterioration"


def test_inversion_keys_unique_per_victim_cause():
    day = simulate_day(day_index=0, seed=99)
    seen = set()
    for inv in day.inversions:
        key = (inv.victim, inv.cause)
        assert key not in seen
        seen.add(key)


def test_fifo_day_has_only_resource_fit_inversions():
    day = simulate_day(day_index=0, seed=99, config={"policy": "fifo"})
    for inv in day.inversions:
        assert inv.cause == CAUSE_RESOURCE_FIT


def test_service_acuities_within_scale():
    day = simulate_day(day_index=0, seed=99)
    for event in day.events:
        if event["type"] == "service_start":
            assert 1 <= event["service_acuity"] <= 5
        if event["type"] == "triage":
            assert 1 <= event["recorded_acuity"] <= 5
