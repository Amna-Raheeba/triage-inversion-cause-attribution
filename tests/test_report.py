from triage_inversion.models import ALL_LABELS, Inversion
from triage_inversion.report import audit_report_markdown, inversion_examples_markdown


def _inv(cause="retriage_lag"):
    return Inversion(
        victim="P001", beneficiary="P002", time=50, cause=cause,
        victim_service_acuity=2, beneficiary_service_acuity=4,
        excess_wait_minutes=30,
    )


def test_audit_report_lists_all_causes():
    report = audit_report_markdown([_inv()])
    for cause in ALL_LABELS:
        assert cause in report
    assert "1 pairs detected" in report


def test_audit_report_empty():
    report = audit_report_markdown([])
    assert "0 pairs detected" in report


def test_examples_markdown_rows():
    text = inversion_examples_markdown([_inv(), _inv("resource_fit_preemption")])
    assert "P001" in text
    assert "retriage_lag" in text
    assert "resource_fit_preemption" in text


def test_examples_markdown_empty():
    text = inversion_examples_markdown([])
    assert "No pairs detected." in text


def test_examples_markdown_respects_limit():
    text = inversion_examples_markdown([_inv() for _ in range(10)], limit=3)
    rows = [line for line in text.splitlines() if line.startswith("| 50")]
    assert len(rows) == 3
