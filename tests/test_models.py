from triage_inversion.models import (
    ALL_LABELS,
    CAUSES,
    CAUSE_POST_HOC,
    DayResult,
    Inversion,
    PatientTruth,
    inversion_from_dict,
)


def test_causes_and_labels():
    assert len(CAUSES) == 3
    assert CAUSE_POST_HOC in ALL_LABELS
    assert len(ALL_LABELS) == 4


def test_patient_truth_acuity_at():
    truth = PatientTruth(
        patient_id="P001", arrival=10, initial_acuity=4, expected_service=15,
        acuity_history=[(10, 4), (40, 3), (70, 1)],
    )
    assert truth.true_acuity_at(0) == 4
    assert truth.true_acuity_at(10) == 4
    assert truth.true_acuity_at(39) == 4
    assert truth.true_acuity_at(40) == 3
    assert truth.true_acuity_at(69) == 3
    assert truth.true_acuity_at(70) == 1
    assert truth.true_acuity_at(500) == 1


def test_inversion_weighted_burden():
    inv = Inversion(
        victim="P001", beneficiary="P002", time=50, cause="retriage_lag",
        victim_service_acuity=2, beneficiary_service_acuity=4,
        excess_wait_minutes=30,
    )
    assert inv.weighted_burden == 30 * 4


def test_inversion_dict_roundtrip():
    inv = Inversion(
        victim="P001", beneficiary="P002", time=50, cause="batch_reassessment_timing",
        victim_service_acuity=1, beneficiary_service_acuity=3,
        excess_wait_minutes=12,
    )
    restored = inversion_from_dict(inv.to_dict())
    assert restored.victim == inv.victim
    assert restored.beneficiary == inv.beneficiary
    assert restored.time == inv.time
    assert restored.cause == inv.cause
    assert restored.weighted_burden == inv.weighted_burden


def test_day_result_to_dict_hides_truth_on_request():
    day = DayResult(day_index=0, seed=42, events=[{"time": 0, "type": "arrival", "patient": "P001"}])
    public = day.to_dict(include_truth=False)
    assert "inversions" not in public
    assert "apparent_pairs" not in public
    full = day.to_dict()
    assert full["inversions"] == []
    assert full["seed"] == 42
