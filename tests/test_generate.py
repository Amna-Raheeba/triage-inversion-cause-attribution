import json
import os

from triage_inversion.generate import (
    day_apparent,
    day_events,
    day_inversions,
    days_from_dict,
    days_to_dict,
    generate_days,
)


def test_generate_days_count_and_seeds():
    days = generate_days(3, 1000)
    assert len(days) == 3
    assert [day.seed for day in days] == [1000, 1001, 1002]
    assert [day.day_index for day in days] == [0, 1, 2]


def test_days_dict_roundtrip():
    days = generate_days(2, 1000)
    restored = days_from_dict(days_to_dict(days))
    assert len(restored) == 2
    for original, copy in zip(days, restored):
        assert day_events(copy) == original.events
        assert len(day_inversions(copy)) == len(original.inversions)
        assert len(day_apparent(copy)) == len(original.apparent_pairs)


def test_stored_data_file_is_valid():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "days.json")
    with open(path) as handle:
        corpus = json.load(handle)
    days = days_from_dict(corpus)
    assert len(days) == 20
    total_inversions = sum(len(day_inversions(day)) for day in days)
    assert total_inversions > 0
