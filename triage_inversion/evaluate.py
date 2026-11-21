"""Headline evaluation: detector cause attribution vs planted truth.

Runs seeded ED days, scores the log-only detector against the
simulator's planted ground truth, scores the baselines the same way,
runs the FIFO burden counterfactual, and runs the counterfactual
repairs. Everything is deterministic: the same seeds regenerate the
same days, which is what the drift guard in scripts/ relies on.

Scoring definitions (also in the README):

- A *pair key* is (victim, beneficiary, beneficiary start time).
- A truth decision-time pair is *detected* if the detector emits its
  key with a cause other than post_hoc (predicting post_hoc means
  the detector declined to call it an inversion).
- Per-cause precision/recall are computed over the three planted
  causes: a detected pair predicted as cause c whose truth label is
  not c (a different cause, or an apparent/post-hoc pair) is a false
  positive for c; a truth pair of cause c not predicted as c is a
  false negative for c.

Author: Amna Raheeba
"""

import csv
import json
import os

from .baselines import blind_counter, fifo_counterfactual, single_rule_classifier, weighted_wait_by_acuity
from .detect import burden_by_cause, detect_inversions
from .generate import day_apparent, day_events, day_inversions, generate_days
from .models import CAUSES, CAUSE_POST_HOC
from .repair import run_repairs

DEFAULT_CONFIG = {
    "n_days": 200,
    "base_seed": 20261121,
    "repair_days": 50,
    "fifo_days": 50,
}


def _key(inversion):
    return (inversion.victim, inversion.beneficiary, inversion.time)


def score_predictions(truth_pairs, apparent_pairs, predicted):
    """Per-cause precision/recall/F1 of one predictor against truth."""
    truth_label = {}
    for inversion in truth_pairs:
        truth_label[_key(inversion)] = inversion.cause
    for inversion in apparent_pairs:
        truth_label[_key(inversion)] = CAUSE_POST_HOC
    predicted_label = {}
    for inversion in predicted:
        predicted_label[_key(inversion)] = inversion.cause

    per_cause = {}
    for cause in CAUSES:
        tp = sum(
            1 for key, label in truth_label.items()
            if label == cause and predicted_label.get(key) == cause
        )
        fp = sum(
            1 for key, label in predicted_label.items()
            if label == cause and truth_label.get(key) != cause
        )
        fn = sum(
            1 for key, label in truth_label.items()
            if label == cause and predicted_label.get(key) != cause
        )
        precision = tp / float(tp + fp) if (tp + fp) else 0.0
        recall = tp / float(tp + fn) if (tp + fn) else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) else 0.0
        )
        per_cause[cause] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    n_decision = sum(1 for label in truth_label.values() if label in CAUSES)
    n_apparent = sum(
        1 for label in truth_label.values() if label == CAUSE_POST_HOC
    )
    detected = sum(
        1 for key, label in truth_label.items()
        if label in CAUSES and predicted_label.get(key) not in (None, CAUSE_POST_HOC)
    )
    declined_correctly = sum(
        1 for key, label in truth_label.items()
        if label == CAUSE_POST_HOC and predicted_label.get(key) == CAUSE_POST_HOC
    )
    correct = sum(
        1 for key, label in truth_label.items()
        if predicted_label.get(key) == label
    )
    return {
        "per_cause": per_cause,
        "n_truth_decision": n_decision,
        "n_truth_apparent": n_apparent,
        "n_predicted": len(predicted_label),
        "n_detected_decision": detected,
        "n_declined_correctly": declined_correctly,
        "n_correct": correct,
        "decision_detection_rate": round(
            detected / float(n_decision), 4
        ) if n_decision else 0.0,
        "apparent_declined_rate": round(
            declined_correctly / float(n_apparent), 4
        ) if n_apparent else 0.0,
        "overall_label_accuracy": round(
            correct / float(len(truth_label)), 4
        ) if truth_label else 0.0,
    }


def merge_scores(score_list):
    """Merge per-day score dicts into corpus-level scores.

    Patient ids repeat across days, so pair keys are only unique
    within a day; scoring is therefore done per day and merged by
    summing counts and recomputing rates.
    """
    per_cause = {}
    for cause in CAUSES:
        tp = sum(s["per_cause"][cause]["tp"] for s in score_list)
        fp = sum(s["per_cause"][cause]["fp"] for s in score_list)
        fn = sum(s["per_cause"][cause]["fn"] for s in score_list)
        precision = tp / float(tp + fp) if (tp + fp) else 0.0
        recall = tp / float(tp + fn) if (tp + fn) else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) else 0.0
        )
        per_cause[cause] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    n_decision = sum(s["n_truth_decision"] for s in score_list)
    n_apparent = sum(s["n_truth_apparent"] for s in score_list)
    detected = sum(s["n_detected_decision"] for s in score_list)
    declined = sum(s["n_declined_correctly"] for s in score_list)
    correct = sum(s["n_correct"] for s in score_list)
    total = n_decision + n_apparent
    return {
        "per_cause": per_cause,
        "n_truth_decision": n_decision,
        "n_truth_apparent": n_apparent,
        "n_predicted": sum(s["n_predicted"] for s in score_list),
        "n_detected_decision": detected,
        "n_declined_correctly": declined,
        "n_correct": correct,
        "decision_detection_rate": round(detected / float(n_decision), 4) if n_decision else 0.0,
        "apparent_declined_rate": round(declined / float(n_apparent), 4) if n_apparent else 0.0,
        "overall_label_accuracy": round(correct / float(total), 4) if total else 0.0,
    }


def run_evaluation(config=None):
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    sim_config = cfg.get("sim_config")
    days = generate_days(cfg["n_days"], cfg["base_seed"], config=sim_config)

    truth_pairs = []
    apparent_pairs = []
    detected = []
    blind = []
    detector_day_scores = []
    baseline_day_scores = []
    for day in days:
        events = day_events(day)
        truth_d = day_inversions(day)
        apparent_d = day_apparent(day)
        detected_d = detect_inversions(events, config=sim_config)
        single_d = single_rule_classifier(events)
        truth_pairs.extend(truth_d)
        apparent_pairs.extend(apparent_d)
        detected.extend(detected_d)
        blind.extend(blind_counter(events))
        detector_day_scores.append(
            score_predictions(truth_d, apparent_d, detected_d)
        )
        baseline_day_scores.append(
            score_predictions(truth_d, apparent_d, single_d)
        )

    detector_scores = merge_scores(detector_day_scores)
    baseline_scores = merge_scores(baseline_day_scores)

    truth_burden = burden_by_cause(truth_pairs)
    detector_burden = burden_by_cause(
        [inv for inv in detected if inv.cause in CAUSES]
    )

    # FIFO burden counterfactual on a paired subset of days: same
    # rooms, same arrivals, pure arrival-order selection.
    fifo_base_weighted = 0
    fifo_weighted = 0
    fifo_base_high_wait = 0.0
    fifo_high_wait = 0.0
    fifo_base_counts = 0
    fifo_inversions = 0
    fifo_base_inversions = 0
    for index in range(cfg["fifo_days"]):
        seed = cfg["base_seed"] + index
        base_day = days[index]
        fifo_day = fifo_counterfactual(index, seed, config=sim_config)
        fifo_base_inversions += len(day_inversions(base_day))
        fifo_inversions += len(fifo_day.inversions)
        for label, day in (("base", base_day), ("fifo", fifo_day)):
            totals = weighted_wait_by_acuity(day)
            weighted = sum(e["weighted_minutes"] for e in totals.values())
            high = sum(
                e["wait_minutes"] / float(e["patients"])
                for acuity, e in totals.items() if acuity <= 2 and e["patients"]
            )
            if label == "base":
                fifo_base_weighted += weighted
                fifo_base_high_wait += high
            else:
                fifo_weighted += weighted
                fifo_high_wait += high
        fifo_base_counts += 1

    repairs = run_repairs(cfg["repair_days"], cfg["base_seed"], config=sim_config)

    aggregates = {
        "n_days": cfg["n_days"],
        "n_patients": sum(
            (day.stats if hasattr(day, "stats") else day["stats"]).get("n_patients", 0)
            for day in days
        ),
        "n_truth_inversions": len(truth_pairs),
        "n_apparent_pairs": len(apparent_pairs),
        "n_detected_pairs": len(detected),
        "n_blind_pairs": len(blind),
        "detector_overall_accuracy": detector_scores["overall_label_accuracy"],
        "detector_decision_detection_rate": detector_scores["decision_detection_rate"],
        "detector_apparent_declined_rate": detector_scores["apparent_declined_rate"],
        "baseline_overall_accuracy": baseline_scores["overall_label_accuracy"],
    }
    for cause in CAUSES:
        short = cause.replace("_preemption", "").replace("_timing", "")
        aggregates["detector_%s_precision" % short] = detector_scores["per_cause"][cause]["precision"]
        aggregates["detector_%s_recall" % short] = detector_scores["per_cause"][cause]["recall"]
        aggregates["baseline_%s_recall" % short] = baseline_scores["per_cause"][cause]["recall"]
    aggregates["truth_weighted_burden"] = sum(
        entry["weighted_minutes"] for entry in truth_burden.values()
    )
    aggregates["fifo_weighted_wait_ratio"] = round(
        fifo_weighted / float(fifo_base_weighted), 4
    ) if fifo_base_weighted else 0.0

    return {
        "config": dict(
            (key, value) for key, value in cfg.items() if key != "sim_config"
        ),
        "aggregates": aggregates,
        "detector": detector_scores,
        "baseline_single_rule": baseline_scores,
        "truth_burden": truth_burden,
        "detector_burden": detector_burden,
        "fifo": {
            "days": cfg["fifo_days"],
            "base_weighted_wait": fifo_base_weighted,
            "fifo_weighted_wait": fifo_weighted,
            "base_high_acuity_mean_wait": round(
                fifo_base_high_wait / float(fifo_base_counts), 3
            ) if fifo_base_counts else 0.0,
            "fifo_high_acuity_mean_wait": round(
                fifo_high_wait / float(fifo_base_counts), 3
            ) if fifo_base_counts else 0.0,
            "base_inversions": fifo_base_inversions,
            "fifo_inversions": fifo_inversions,
        },
        "repairs": repairs,
    }


def write_results(evaluation, outdir):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "evaluation.json"), "w") as handle:
        json.dump(evaluation, handle, indent=2, sort_keys=True)
    rows = []
    for cause in CAUSES:
        det = evaluation["detector"]["per_cause"][cause]
        base = evaluation["baseline_single_rule"]["per_cause"][cause]
        rows.append({
            "cause": cause,
            "detector_precision": det["precision"],
            "detector_recall": det["recall"],
            "detector_f1": det["f1"],
            "baseline_precision": base["precision"],
            "baseline_recall": base["recall"],
            "baseline_f1": base["f1"],
            "truth_pairs": det["tp"] + det["fn"],
            "truth_weighted_burden": evaluation["truth_burden"].get(
                cause, {}
            ).get("weighted_minutes", 0),
        })
    with open(os.path.join(outdir, "evaluation.csv"), "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with open(os.path.join(outdir, "evaluation_summary.md"), "w") as handle:
        handle.write(summary_markdown(evaluation))
    with open(os.path.join(outdir, "HEADLINE.md"), "w") as handle:
        handle.write(headline_markdown(evaluation))
    return rows


def _cause_table(evaluation):
    lines = [
        "| Cause | Truth pairs | Detector P | Detector R | Detector F1 | Single-rule R |",
        "|---|---|---|---|---|---|",
    ]
    for cause in CAUSES:
        det = evaluation["detector"]["per_cause"][cause]
        base = evaluation["baseline_single_rule"]["per_cause"][cause]
        lines.append(
            "| %s | %d | %.3f | %.3f | %.3f | %.3f |"
            % (cause, det["tp"] + det["fn"], det["precision"], det["recall"],
               det["f1"], base["recall"])
        )
    return "\n".join(lines)


def summary_markdown(evaluation):
    agg = evaluation["aggregates"]
    lines = [
        "# Evaluation summary",
        "",
        "Seeded discrete-event ED simulation: %d days, %d patients, "
        "base seed %d. Ground truth is planted by the simulator; the "
        "detector reads only the event log. All clinical content is "
        "synthetic." % (
            agg["n_days"], agg["n_patients"], evaluation["config"]["base_seed"]
        ),
        "",
        "## Cause attribution",
        "",
        _cause_table(evaluation),
        "",
        "- Truth: %d decision-time inversions, %d apparent (post-hoc) pairs."
        % (agg["n_truth_inversions"], agg["n_apparent_pairs"]),
        "- Detector: overall label accuracy %.3f; decision-time detection "
        "rate %.3f; apparent pairs correctly declined %.3f."
        % (agg["detector_overall_accuracy"],
           agg["detector_decision_detection_rate"],
           agg["detector_apparent_declined_rate"]),
        "- Single-rule baseline: overall label accuracy %.3f."
        % agg["baseline_overall_accuracy"],
        "- Cause-blind counter: %d pairs counted, no cause attributed."
        % agg["n_blind_pairs"],
        "",
        "## Burden (urgency-weighted excess wait minutes, truth)",
        "",
    ]
    for cause in CAUSES:
        entry = evaluation["truth_burden"].get(cause, {})
        det = evaluation["detector_burden"].get(cause, {})
        lines.append(
            "- %s: truth %d weighted minutes over %d pairs; detector "
            "attributes %d." % (
                cause, entry.get("weighted_minutes", 0), entry.get("pairs", 0),
                det.get("weighted_minutes", 0),
            )
        )
    lines += [
        "",
        "## FIFO counterfactual (%d paired days)" % evaluation["fifo"]["days"],
        "",
        "- Same rooms and arrivals, pure arrival-order selection. "
        "Urgency-weighted total wait (triage-acuity basis), priority "
        "queue: %d; FIFO: %d (ratio %.3f). Mean wait of triage-acuity "
        "1-2 patients: priority %.1f min, FIFO %.1f min. Inversions: "
        "priority %d, FIFO %d -- every FIFO inversion is a fast-track "
        "resource-fit pass (arrival ordering removes the stale-score "
        "causes entirely), and FIFO's are more numerous because "
        "uniformly longer waits leave more sick patients exposed in "
        "the pool each fast-track pull draws past." % (
            evaluation["fifo"]["base_weighted_wait"],
            evaluation["fifo"]["fifo_weighted_wait"],
            agg["fifo_weighted_wait_ratio"],
            evaluation["fifo"]["base_high_acuity_mean_wait"],
            evaluation["fifo"]["fifo_high_acuity_mean_wait"],
            evaluation["fifo"]["base_inversions"],
            evaluation["fifo"]["fifo_inversions"],
        ),
        "",
        "## Counterfactual repairs (%d paired days)" % evaluation["config"]["repair_days"],
        "",
    ]
    for name, tally in sorted(evaluation["repairs"]["repairs"].items()):
        lines.append(
            "- %s (targets %s): inversions removed by cause -- %s "
            "(negative = that cause increased under the repair); total "
            "inversions %d -> %d; reassessments %d; fast-track busy "
            "minutes %d; mean wait %.1f."
            % (
                name, tally["targets"],
                ", ".join(
                    "%s %+d" % (cause, tally["removed_by_cause"][cause])
                    for cause in CAUSES
                ),
                evaluation["repairs"]["base"]["total_inversions"],
                tally["total_inversions"],
                tally["total_reassessments"],
                tally["fasttrack_busy_minutes"],
                tally["mean_wait_minutes"],
            )
        )
    lines += [
        "",
        "## Caveats",
        "",
        "- Synthetic seeded days under declared simulation parameters "
        "(arrival rate, deterioration hazards, reassessment policy); "
        "the audit measures detector behaviour and mechanism costs "
        "under those parameters, not a real ED's inversion rate.",
        "- The detector's structural blind spot: deterioration shortly "
        "before a beneficiary's start with no vitals check in between "
        "is log-identical to deterioration shortly after it; the "
        "post-hoc and batch-timing scores price that ambiguity.",
    ]
    return "\n".join(lines) + "\n"


def headline_markdown(evaluation):
    agg = evaluation["aggregates"]
    det = evaluation["detector"]["per_cause"]
    worst = max(CAUSES, key=lambda c: det[c]["fp"] + det[c]["fn"])
    lines = [
        "# Headline results",
        "",
        "A cause-attributed inversion audit of a synthetic emergency-"
        "department queue: %d seeded ED days, %d patients, %d planted "
        "decision-time inversions across three operational causes, "
        "plus %d apparent pairs that only look like inversions. A "
        "log-only detector attributes each pair's cause from its "
        "signature in the queue log." % (
            agg["n_days"], agg["n_patients"], agg["n_truth_inversions"],
            agg["n_apparent_pairs"],
        ),
        "",
        "- Overall cause-label accuracy **%.3f** (single-rule baseline "
        "%.3f); the cause-blind counter attributes nothing."
        % (agg["detector_overall_accuracy"], agg["baseline_overall_accuracy"]),
        "- Per-cause recall: re-triage lag **%.3f**, resource-fit "
        "preemption **%.3f**, batch reassessment timing **%.3f**."
        % (det["retriage_lag"]["recall"], det["resource_fit_preemption"]["recall"],
           det["batch_reassessment_timing"]["recall"]),
        "- The single-rule baseline never predicts batch timing "
        "(recall %.3f there) -- the vitals/batch signature logic is "
        "what buys that cause." % evaluation["baseline_single_rule"]["per_cause"]["batch_reassessment_timing"]["recall"],
        "- Apparent (post-hoc) pairs correctly declined: **%.3f**. "
        "Hardest label by errors: **%s**."
        % (agg["detector_apparent_declined_rate"], worst),
        "",
        "Caveat: all days are synthetic and seeded, with causes planted "
        "by construction under declared simulation parameters; the "
        "audit measures detector behaviour on these mechanisms, not "
        "performance in a real emergency department.",
    ]
    return "\n".join(lines) + "\n"


DRIFT_KEYS = None  # computed from aggregates on first use


def check_drift(stored, fresh, tol=1e-6):
    """Compare stored vs fresh headline aggregates; return (ok, problems)."""
    problems = []
    stored_agg = stored.get("aggregates", {})
    fresh_agg = fresh.get("aggregates", {})
    for key in sorted(set(stored_agg) | set(fresh_agg)):
        stored_value = stored_agg.get(key)
        fresh_value = fresh_agg.get(key)
        if isinstance(stored_value, (int, float)) and isinstance(fresh_value, (int, float)):
            diff = abs(stored_value - fresh_value)
            if diff > tol:
                problems.append((key, stored_value, fresh_value, diff))
        elif stored_value != fresh_value:
            problems.append((key, stored_value, fresh_value, None))
    return (not problems), problems
