"""Detector tests on hand-built logs: one scenario per cause branch.

The hand-built logs use the same event schema as the simulator's.
Victim V: arrives 0, triaged at 2 with recorded acuity 4, finally
served at 100 with service acuity 2. Beneficiary B: arrives 10,
triaged at 12 with recorded acuity 3, served at 50 with service
acuity 3. Only the room type and V's vitals pattern change between
scenarios.
"""

from triage_inversion.detect import (
    build_timelines,
    burden_by_cause,
    detect_inversions,
)
from triage_inversion.models import (
    CAUSE_BATCH_TIMING,
    CAUSE_POST_HOC,
    CAUSE_RESOURCE_FIT,
    CAUSE_RETRIAGE_LAG,
)


def _base_events(room_type="general", victim_vitals=()):
    events = [
        {"time": 0, "type": "arrival", "patient": "V"},
        {"time": 2, "type": "triage", "patient": "V", "recorded_acuity": 4,
         "expected_service": 15},
        {"time": 10, "type": "arrival", "patient": "B"},
        {"time": 12, "type": "triage", "patient": "B", "recorded_acuity": 3,
         "expected_service": 25},
    ]
    for vtime, severity in victim_vitals:
        events.append({"time": vtime, "type": "vitals", "patient": "V",
                       "severity": severity})
    events.append({"time": 50, "type": "service_start", "patient": "B",
                   "room": "G1" if room_type == "general" else "F1",
                   "room_type": room_type, "service_acuity": 3})
    events.append({"time": 100, "type": "service_start", "patient": "V",
                   "room": "G1", "room_type": "general", "service_acuity": 2})
    events.sort(key=lambda e: e["time"])
    return events


def test_fast_track_start_is_resource_fit():
    detected = detect_inversions(_base_events(room_type="fast_track"))
    assert len(detected) == 1
    assert detected[0].cause == CAUSE_RESOURCE_FIT
    assert detected[0].victim == "V"
    assert detected[0].beneficiary == "B"
    assert detected[0].excess_wait_minutes == 50


def test_abnormal_vitals_unacted_is_retriage_lag():
    # Recorded 4 implies severity ~2.0; 3.4 is an abnormal excess of 1.4.
    events = _base_events(victim_vitals=[(30, 3.4)])
    detected = detect_inversions(events)
    assert len(detected) == 1
    assert detected[0].cause == CAUSE_RETRIAGE_LAG


def test_abnormal_vitals_acted_on_is_not_retriage_lag():
    events = _base_events(victim_vitals=[(30, 3.4)])
    events.append({"time": 35, "type": "reassessment", "patient": "V",
                   "recorded_acuity": 2, "source": "prompt"})
    events.sort(key=lambda e: e["time"])
    detected = detect_inversions(events)
    # The reassessment at 35 becomes the last assessment; the abnormal
    # check at 30 precedes it, so the retriage signature is gone and
    # the fall-through label applies.
    assert len(detected) == 1
    assert detected[0].cause == CAUSE_BATCH_TIMING


def test_no_vitals_evidence_is_batch_timing():
    events = _base_events(victim_vitals=[(30, 2.1)])
    detected = detect_inversions(events)
    assert len(detected) == 1
    assert detected[0].cause == CAUSE_BATCH_TIMING


def test_borderline_vitals_is_batch_timing_not_post_hoc():
    # Excess 0.6: above the noise band, below the abnormal threshold,
    # and an abnormal check after the start must not override it.
    events = _base_events(victim_vitals=[(30, 2.6), (80, 3.4)])
    detected = detect_inversions(events)
    assert len(detected) == 1
    assert detected[0].cause == CAUSE_BATCH_TIMING


def test_clean_then_abnormal_after_start_is_post_hoc():
    events = _base_events(victim_vitals=[(30, 2.0), (60, 2.1), (80, 3.4)])
    detected = detect_inversions(events)
    assert len(detected) == 1
    assert detected[0].cause == CAUSE_POST_HOC


def test_no_pair_when_victim_arrives_later():
    events = _base_events()
    for event in events:
        if event.get("patient") == "V" and event["type"] == "arrival":
            event["time"] = 20
    assert detect_inversions(events) == []


def test_no_pair_when_victim_served_first():
    events = _base_events()
    for event in events:
        if event.get("patient") == "V" and event["type"] == "service_start":
            event["time"] = 40
    assert detect_inversions(events) == []


def test_no_pair_when_victim_less_acute_at_service():
    events = _base_events()
    for event in events:
        if event.get("patient") == "V" and event["type"] == "service_start":
            event["service_acuity"] = 3
    assert detect_inversions(events) == []


def test_timelines_reconstruct_scores():
    events = _base_events(victim_vitals=[(30, 3.4)])
    timelines = build_timelines(events)
    victim = timelines["V"]
    assert victim.arrival == 0
    assert victim.recorded_at(10) == 4
    assert victim.recorded_at(1) is None
    assert victim.last_assessment_before(50) == 2
    assert victim.abnormal_vitals(2, 50, 0.8) == [30]
    assert victim.service_room_type == "general"


def test_burden_by_cause_aggregates():
    detected = detect_inversions(_base_events(room_type="fast_track"))
    burden = burden_by_cause(detected)
    entry = burden[CAUSE_RESOURCE_FIT]
    assert entry["pairs"] == 1
    assert entry["excess_minutes"] == 50
    assert entry["weighted_minutes"] == 50 * (6 - 2)
