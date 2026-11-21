from triage_inversion.repair import REPAIRS, run_repairs


def test_repairs_registry_targets_planted_causes():
    assert set(REPAIRS) == {"prompt_retriage", "frequent_batch", "fasttrack_guard"}
    targets = set(spec["targets"] for spec in REPAIRS.values())
    assert targets == {
        "retriage_lag", "batch_reassessment_timing", "resource_fit_preemption"
    }


def test_prompt_retriage_removes_retriage_lag():
    result = run_repairs(10, 20261121)
    removed = result["repairs"]["prompt_retriage"]["removed_by_cause"]
    assert removed["retriage_lag"] > 0


def test_frequent_batch_removes_batch_timing():
    result = run_repairs(10, 20261121)
    removed = result["repairs"]["frequent_batch"]["removed_by_cause"]
    assert removed["batch_reassessment_timing"] > 0


def test_fasttrack_guard_removes_resource_fit():
    result = run_repairs(10, 20261121)
    removed = result["repairs"]["fasttrack_guard"]["removed_by_cause"]
    assert removed["resource_fit_preemption"] > 0


def test_repairs_report_costs():
    result = run_repairs(4, 20261121)
    for tally in result["repairs"].values():
        assert tally["total_reassessments"] >= 0
        assert tally["fasttrack_busy_minutes"] >= 0
        assert tally["mean_wait_minutes"] > 0
    base = result["base"]
    assert base["total_inversions"] == sum(base["inversions_by_cause"].values())
