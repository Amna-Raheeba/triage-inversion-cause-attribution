"""Streamlit dashboard for triage-inversion-cause-attribution.

Three tabs:
1. Day explorer -- one seeded ED day: the inversions the log-only
   detector finds, with attributed causes, next to the planted
   ground truth for the same day.
2. Cause attribution -- per-cause precision/recall and burden from
   the stored headline evaluation (results/evaluation.json).
3. Evaluation & repairs -- headline aggregates, the FIFO burden
   counterfactual, the counterfactual repairs, and caveats.

Run: streamlit run app.py
"""

import json
import os

import streamlit as st

from triage_inversion.detect import burden_by_cause, detect_inversions
from triage_inversion.generate import generate_days
from triage_inversion.models import ALL_LABELS, CAUSES

st.set_page_config(page_title="Triage Inversion Cause Attribution", layout="wide")

RESULTS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "results", "evaluation.json"
)


def _load_evaluation():
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as handle:
            return json.load(handle)
    return None


def tab_day_explorer():
    st.header("Explore one seeded ED day")
    st.write(
        "The detector reads only the day's event log. The planted "
        "truth for the same day is shown alongside so the attribution "
        "can be eyeballed pair by pair."
    )
    seed = st.number_input("Day seed", min_value=1, max_value=99999999,
                           value=20261121, step=1)
    day = generate_days(1, int(seed))[0]
    detected = detect_inversions(day.events)
    truth = list(day.inversions) + list(day.apparent_pairs)
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Detector (log only)")
        st.write("%d pairs reported." % len(detected))
        rows = [
            {
                "time": inv.time,
                "victim": inv.victim,
                "beneficiary": inv.beneficiary,
                "cause": inv.cause,
                "excess_wait": inv.excess_wait_minutes,
            }
            for inv in detected[:40]
        ]
        if rows:
            st.dataframe(rows)
    with col_b:
        st.subheader("Planted ground truth")
        st.write(
            "%d decision-time inversions, %d apparent pairs."
            % (len(day.inversions), len(day.apparent_pairs))
        )
        rows = [
            {
                "time": inv.time,
                "victim": inv.victim,
                "beneficiary": inv.beneficiary,
                "cause": inv.cause,
                "excess_wait": inv.excess_wait_minutes,
            }
            for inv in truth[:40]
        ]
        if rows:
            st.dataframe(rows)
    burden = burden_by_cause(detected)
    chart = dict(
        (cause, burden.get(cause, {}).get("weighted_minutes", 0))
        for cause in ALL_LABELS
    )
    st.subheader("Detector-attributed weighted burden by cause")
    st.bar_chart(chart)


def tab_attribution():
    st.header("Cause attribution (headline evaluation)")
    evaluation = _load_evaluation()
    if evaluation is None:
        st.write("No stored evaluation found. Run: python -m triage_inversion evaluate")
        return
    rows = []
    for cause in CAUSES:
        det = evaluation["detector"]["per_cause"][cause]
        base = evaluation["baseline_single_rule"]["per_cause"][cause]
        rows.append({
            "cause": cause,
            "truth_pairs": det["tp"] + det["fn"],
            "detector_precision": det["precision"],
            "detector_recall": det["recall"],
            "detector_f1": det["f1"],
            "single_rule_recall": base["recall"],
        })
    st.dataframe(rows)
    st.write(
        "Overall label accuracy: detector %.3f, single-rule baseline "
        "%.3f. Apparent (post-hoc) pairs correctly declined: %.3f."
        % (
            evaluation["aggregates"]["detector_overall_accuracy"],
            evaluation["aggregates"]["baseline_overall_accuracy"],
            evaluation["aggregates"]["detector_apparent_declined_rate"],
        )
    )
    burden_rows = []
    for cause in CAUSES:
        burden_rows.append({
            "cause": cause,
            "truth_weighted_minutes": evaluation["truth_burden"].get(cause, {}).get("weighted_minutes", 0),
            "detector_weighted_minutes": evaluation["detector_burden"].get(cause, {}).get("weighted_minutes", 0),
        })
    st.subheader("Inversion burden by cause (urgency-weighted excess wait)")
    st.dataframe(burden_rows)


def tab_evaluation():
    st.header("Evaluation, FIFO counterfactual, and repairs")
    evaluation = _load_evaluation()
    if evaluation is None:
        st.write("No stored evaluation found. Run: python -m triage_inversion evaluate")
        return
    agg = evaluation["aggregates"]
    st.write(
        "%d seeded days, %d patients, %d planted decision-time "
        "inversions, %d apparent pairs."
        % (agg["n_days"], agg["n_patients"], agg["n_truth_inversions"],
           agg["n_apparent_pairs"])
    )
    fifo = evaluation["fifo"]
    st.subheader("FIFO counterfactual (%d paired days)" % fifo["days"])
    st.write(
        "Urgency-weighted total wait: priority %d, FIFO %d. Mean wait "
        "of triage-acuity 1-2 patients: priority %.1f min, FIFO %.1f "
        "min. Inversions: priority %d, FIFO %d (all of FIFO's are "
        "fast-track resource-fit passes)."
        % (
            fifo["base_weighted_wait"], fifo["fifo_weighted_wait"],
            fifo["base_high_acuity_mean_wait"], fifo["fifo_high_acuity_mean_wait"],
            fifo["base_inversions"], fifo["fifo_inversions"],
        )
    )
    st.subheader("Counterfactual repairs (%d paired days)" % evaluation["config"]["repair_days"])
    rows = []
    base = evaluation["repairs"]["base"]
    for name, tally in sorted(evaluation["repairs"]["repairs"].items()):
        row = {"repair": name, "targets": tally["targets"]}
        for cause in CAUSES:
            row["removed_" + cause] = tally["removed_by_cause"][cause]
        row["reassessments"] = tally["total_reassessments"]
        row["mean_wait"] = tally["mean_wait_minutes"]
        rows.append(row)
    st.dataframe(rows)
    st.write(
        "Base days: %d inversions, %d reassessments, mean wait %.1f min."
        % (base["total_inversions"], base["total_reassessments"],
           base["mean_wait_minutes"])
    )
    st.subheader("Caveats")
    st.write(
        "All days are synthetic and seeded under declared simulation "
        "parameters (arrival rate, deterioration hazards, reassessment "
        "policy). The audit measures detector behaviour and mechanism "
        "costs under those parameters, not a real ED's inversion rate. "
        "Batch reassessment timing is the residual cause: deterioration "
        "shortly before a beneficiary's start with no vitals check in "
        "between is log-identical to deterioration shortly after it, "
        "and the batch precision score prices that ambiguity."
    )


def main():
    st.title("Triage Inversion Cause Attribution")
    tab1, tab2, tab3 = st.tabs(
        ["Day explorer", "Cause attribution", "Evaluation & repairs"]
    )
    with tab1:
        tab_day_explorer()
    with tab2:
        tab_attribution()
    with tab3:
        tab_evaluation()


main()
