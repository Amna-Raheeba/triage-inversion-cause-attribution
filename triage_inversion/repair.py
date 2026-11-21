"""Counterfactual repairs: what removing each mechanism costs and buys.

Attribution is only useful if it points at a fix. For each planted
cause the audit re-simulates the same seeded days with one mechanism
repaired and measures (a) how many inversions of each cause remain --
a repair should remove mainly *its own* cause, which cross-validates
the attribution -- and (b) the operational cost of the repair.

Repairs:

- ``prompt_retriage`` (targets re-triage lag): every abnormal vitals
  check triggers a prompt reassessment (probability 0.5 -> 1.0).
  Cost: number of reassessments performed.
- ``frequent_batch`` (targets batch timing): batch reassessment
  rounds every 10 minutes instead of 45. Cost: reassessment count.
- ``fasttrack_guard`` (targets resource-fit preemption): the
  fast-track room holds its pull when any recorded-acuity <= 3
  patient has waited 20+ minutes. Cost: fast-track busy minutes lost
  (idle room) and any change in mean wait.

All repairs are config overrides on the same simulator, run on the
same seeds, so before/after counts are paired by construction.

Author: Amna Raheeba
"""

from .generate import generate_days
from .models import CAUSES

REPAIRS = {
    "prompt_retriage": {
        "overrides": {"prompt_reassessment_prob": 1.0},
        "targets": "retriage_lag",
        "description": "Every abnormal vitals check triggers a prompt reassessment.",
    },
    "frequent_batch": {
        "overrides": {"batch_interval_minutes": 10},
        "targets": "batch_reassessment_timing",
        "description": "Batch reassessment rounds every 10 minutes instead of 60.",
    },
    "fasttrack_guard": {
        "overrides": {"fasttrack_guard_wait": 20},
        "targets": "resource_fit_preemption",
        "description": "Fast-track room holds its pull while a recorded-acuity <= 3 patient has waited 20+ minutes.",
    },
}


def _tally(days):
    counts = dict((cause, 0) for cause in CAUSES)
    total = 0
    reassessments = 0
    fasttrack_busy = 0
    waits = []
    for day in days:
        stats = day.stats if hasattr(day, "stats") else day["stats"]
        reassessments += stats.get("n_reassessments", 0)
        fasttrack_busy += stats.get("fasttrack_busy_minutes", 0)
        waits.append(stats.get("mean_wait_minutes", 0.0))
        inversions = day.inversions if hasattr(day, "inversions") else day["inversions"]
        for inversion in inversions:
            counts[inversion.cause] += 1
            total += 1
    return {
        "inversions_by_cause": counts,
        "total_inversions": total,
        "total_reassessments": reassessments,
        "fasttrack_busy_minutes": fasttrack_busy,
        "mean_wait_minutes": round(sum(waits) / float(len(waits)), 3) if waits else 0.0,
    }


def run_repairs(n_days, base_seed, config=None):
    """Run the base days and each one-mechanism repair on the same seeds."""
    base_days = generate_days(n_days, base_seed, config=config)
    result = {"base": _tally(base_days), "repairs": {}}
    for name, spec in REPAIRS.items():
        cfg = dict(config or {})
        cfg.update(spec["overrides"])
        repaired_days = generate_days(n_days, base_seed, config=cfg)
        tally = _tally(repaired_days)
        removed = {}
        for cause in CAUSES:
            removed[cause] = (
                result["base"]["inversions_by_cause"][cause]
                - tally["inversions_by_cause"][cause]
            )
        tally["removed_by_cause"] = removed
        tally["targets"] = spec["targets"]
        tally["description"] = spec["description"]
        result["repairs"][name] = tally
    return result
