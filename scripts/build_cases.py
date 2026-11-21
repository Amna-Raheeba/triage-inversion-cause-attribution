"""Generate the stored case data.

Writes:
- data/days.json: 20 seeded ED days (event logs + planted truth),
  using the same seed scheme as triage_inversion.evaluate, so the
  stored days are the first 20 days of the headline evaluation.
- examples/demo_day.json: one seeded day for the example script.

Run: python scripts/build_cases.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from triage_inversion.cli import demo_days
from triage_inversion.evaluate import DEFAULT_CONFIG
from triage_inversion.generate import days_to_dict, generate_days


def main():
    root = os.path.join(os.path.dirname(__file__), "..")
    cfg = DEFAULT_CONFIG
    days = generate_days(20, cfg["base_seed"])
    data_path = os.path.join(root, "data", "days.json")
    with open(data_path, "w") as handle:
        json.dump(days_to_dict(days), handle, separators=(",", ":"))
    inversions = sum(len(day.inversions) for day in days)
    print("Wrote %s (%d days, %d planted inversions)" % (data_path, len(days), inversions))

    demo_path = os.path.join(root, "examples", "demo_day.json")
    demo = demo_days()[:1]
    with open(demo_path, "w") as handle:
        json.dump(days_to_dict(demo), handle, indent=2)
    print("Wrote %s (%d day)" % (demo_path, len(demo)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
