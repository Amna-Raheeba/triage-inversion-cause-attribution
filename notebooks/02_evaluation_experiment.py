"""Evaluation experiment: cause attribution against planted truth.

Runs the full headline evaluation (200 seeded days + baselines +
FIFO counterfactual + repairs) and prints the headline summary.
This is the same computation that produces results/; CI runs it as
a smoke check.

Run: python notebooks/02_evaluation_experiment.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from triage_inversion.evaluate import headline_markdown, run_evaluation


def main():
    evaluation = run_evaluation()
    print(headline_markdown(evaluation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
