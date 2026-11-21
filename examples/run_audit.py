"""Audit the demo day (stored log) and print the report.

Run: python examples/run_audit.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from triage_inversion.detect import detect_inversions
from triage_inversion.generate import days_from_dict
from triage_inversion.report import audit_report_markdown, inversion_examples_markdown


def main():
    path = os.path.join(os.path.dirname(__file__), "demo_day.json")
    with open(path) as handle:
        days = days_from_dict(json.load(handle))
    detected = []
    for day in days:
        detected.extend(detect_inversions(day["events"]))
    print(audit_report_markdown(detected, title="Demo-day audit"))
    print(inversion_examples_markdown(detected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
