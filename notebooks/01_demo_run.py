"""Demo: simulate three seeded ED days and audit their logs.

The detector reads only the event logs; the planted truth counts for
the same days are printed first so the attributed causes can be
compared against what the simulator actually planted.

Run: python notebooks/01_demo_run.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from triage_inversion.cli import demo_days
from triage_inversion.detect import detect_inversions
from triage_inversion.report import audit_report_markdown, inversion_examples_markdown


def main():
    days = demo_days()
    detected = []
    for day in days:
        print(
            "Day seed %d: %d patients, %d planted inversions, %d apparent pairs"
            % (
                day.seed,
                day.stats["n_patients"],
                len(day.inversions),
                len(day.apparent_pairs),
            )
        )
        detected.extend(detect_inversions(day.events))
    print("")
    print(audit_report_markdown(detected, title="Demo audit (3 seeded days)"))
    print(inversion_examples_markdown(detected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
