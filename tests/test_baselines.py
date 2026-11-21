from triage_inversion.baselines import (
    blind_counter,
    fifo_counterfactual,
    single_rule_classifier,
    weighted_wait_by_acuity,
)
from triage_inversion.generate import generate_days


def test_blind_counter_attributes_nothing():
    day = generate_days(1, 4242)[0]
    pairs = blind_counter(day.events)
    assert pairs
    assert all(pair.cause == "unknown" for pair in pairs)


def test_blind_counter_one_entry_per_victim():
    day = generate_days(1, 4242)[0]
    pairs = blind_counter(day.events)
    victims = [pair.victim for pair in pairs]
    assert len(victims) == len(set(victims))


def test_single_rule_never_predicts_batch_or_post_hoc():
    day = generate_days(1, 4242)[0]
    pairs = single_rule_classifier(day.events)
    assert pairs
    for pair in pairs:
        assert pair.cause in ("retriage_lag", "resource_fit_preemption")


def test_single_rule_uses_same_pair_count_as_detector_convention():
    day = generate_days(1, 4242)[0]
    pairs = single_rule_classifier(day.events)
    keys = [(pair.victim, pair.cause) for pair in pairs]
    assert len(keys) == len(set(keys))


def test_fifo_counterfactual_serves_everyone():
    day = fifo_counterfactual(0, 4242)
    assert day.stats["n_served"] == day.stats["n_patients"]


def test_weighted_wait_by_acuity_covers_all_served():
    day = generate_days(1, 4242)[0]
    totals = weighted_wait_by_acuity(day)
    patients = sum(entry["patients"] for entry in totals.values())
    assert patients == day.stats["n_served"]
    for acuity, entry in totals.items():
        assert 1 <= acuity <= 5
        assert entry["weighted_minutes"] == entry["wait_minutes"] * (6 - acuity)
