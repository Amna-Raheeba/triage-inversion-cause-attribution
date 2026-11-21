import os

from triage_inversion.cli import demo_days, main

EXAMPLES_DAY = os.path.join(
    os.path.dirname(__file__), "..", "examples", "demo_day.json"
)


def test_demo_days_are_seeded():
    days = demo_days()
    assert len(days) == 3
    assert [day.seed for day in days] == [7, 8, 9]


def test_cli_demo(capsys):
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "Demo audit" in out


def test_cli_audit_demo_day(capsys):
    assert main(["audit", "--days", EXAMPLES_DAY]) == 0
    out = capsys.readouterr().out
    assert "pairs detected" in out


def test_cli_no_command():
    assert main([]) == 2
