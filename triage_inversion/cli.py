"""Command line interface.

Usage:
    python -m triage_inversion demo
    python -m triage_inversion audit --days examples/demo_day.json
    python -m triage_inversion evaluate --outdir results
"""

import argparse
import json

from .detect import detect_inversions
from .evaluate import run_evaluation, write_results
from .generate import days_from_dict, generate_days
from .report import audit_report_markdown, inversion_examples_markdown

DEMO_SEED = 7


def demo_days():
    """Three seeded days for the built-in demo."""
    return generate_days(3, DEMO_SEED)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="triage_inversion",
        description=(
            "Audit an emergency-department queue log for priority "
            "inversions and attribute each inversion to its "
            "operational cause."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("demo", help="Simulate 3 days, detect inversions, report")

    audit_parser = sub.add_parser(
        "audit", help="Detect inversions in a stored days JSON file"
    )
    audit_parser.add_argument("--days", required=True,
                              help="Days JSON path (see data/days.json)")

    eval_parser = sub.add_parser(
        "evaluate", help="Run the headline evaluation and write results"
    )
    eval_parser.add_argument("--outdir", default="results")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "demo":
        detected = []
        for day in demo_days():
            detected.extend(detect_inversions(day.events))
        print(audit_report_markdown(detected, title="Demo audit (3 seeded days)"))
        print(inversion_examples_markdown(detected))
        return 0
    if args.command == "audit":
        with open(args.days) as handle:
            days = days_from_dict(json.load(handle))
        detected = []
        for day in days:
            detected.extend(detect_inversions(day["events"]))
        print(audit_report_markdown(detected))
        print(inversion_examples_markdown(detected))
        return 0
    if args.command == "evaluate":
        evaluation = run_evaluation()
        write_results(evaluation, args.outdir)
        agg = evaluation["aggregates"]
        print(
            "Wrote results to %s: %d truth inversions over %d days, "
            "detector cause accuracy %.3f, single-rule baseline %.3f."
            % (
                args.outdir,
                agg["n_truth_inversions"],
                agg["n_days"],
                agg["detector_overall_accuracy"],
                agg["baseline_overall_accuracy"],
            )
        )
        return 0
    parser.print_help()
    return 2
