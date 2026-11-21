"""Baselines the cause-attribution detector is compared against.

1. **Cause-blind counter** -- counts inversion pairs (using service
   acuities, like the detector) but attributes no cause at all. It
   answers "how many?" and nothing else: per-cause precision/recall
   are zero by construction, and burden cannot be split by cause.
2. **Single-rule classifier** -- a plausible hand rule: fast-track
   starts are resource-fit, everything else is re-triage lag. It
   never predicts batch timing or post-hoc, so its per-cause scores
   show exactly what the vitals/batch signature logic adds.
3. **FIFO counterfactual queue** -- the same days re-simulated with
   pure first-in-first-out room assignment (no acuity ordering, no
   fast-track fit). Not a classifier: a burden baseline. It has no
   inversions by construction (an earlier arriver is always taken
   first), but high-acuity patients wait behind everyone who arrived
   before them; the evaluation compares urgency-weighted waits so the
   tradeoff is measured, not asserted.

Author: Amna Raheeba
"""

from .detect import build_timelines
from .models import CAUSE_RESOURCE_FIT, CAUSE_RETRIAGE_LAG, Inversion
from .simulate import simulate_day


def _enumerate_pairs(events):
    """All detectable passes (no dedup), with cause left as unknown."""
    timelines = build_timelines(events)
    served = [
        timeline for timeline in timelines.values()
        if timeline.service_start is not None
    ]
    pairs = []
    for beneficiary in served:
        for victim in served:
            if victim.patient_id == beneficiary.patient_id:
                continue
            if victim.service_start <= beneficiary.service_start:
                continue
            if victim.arrival >= beneficiary.arrival:
                continue
            if victim.service_acuity >= beneficiary.service_acuity:
                continue
            pairs.append(Inversion(
                victim=victim.patient_id,
                beneficiary=beneficiary.patient_id,
                time=beneficiary.service_start,
                cause="unknown",
                victim_service_acuity=victim.service_acuity,
                beneficiary_service_acuity=beneficiary.service_acuity,
                excess_wait_minutes=victim.service_start - beneficiary.service_start,
            ))
    pairs.sort(key=lambda inv: (inv.time, inv.victim, inv.beneficiary))
    return pairs


def blind_counter(events):
    """Count passed-over patients, attributing no cause.

    Reports one entry per victim (their first pass): how many
    patients were passed over, never why.
    """
    pairs = _enumerate_pairs(events)
    seen = set()
    first_passes = []
    for pair in pairs:
        if pair.victim in seen:
            continue
        seen.add(pair.victim)
        first_passes.append(pair)
    return first_passes


def single_rule_classifier(events):
    """Fast-track -> resource fit; everything else -> re-triage lag.

    Uses the same pair enumeration and the same per-(victim, cause)
    counting convention as the detector, so the comparison isolates
    the attribution rule, not the bookkeeping.
    """
    pairs = _enumerate_pairs(events)
    timelines = build_timelines(events)
    for pair in pairs:
        room_type = timelines[pair.beneficiary].service_room_type
        pair.cause = CAUSE_RESOURCE_FIT if room_type == "fast_track" else CAUSE_RETRIAGE_LAG
    seen = set()
    deduped = []
    for pair in pairs:
        key = (pair.victim, pair.cause)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(pair)
    return deduped


def fifo_counterfactual(day_index, seed, config=None):
    """Re-simulate a day under pure FIFO room assignment."""
    cfg = dict(config or {})
    cfg["policy"] = "fifo"
    return simulate_day(day_index=day_index, seed=seed, config=cfg)


def weighted_wait_by_acuity(day):
    """Urgency-weighted total wait, split by *triage* acuity.

    The acuity basis is the score recorded at triage -- before any
    waiting deterioration -- because it is a property of the arriving
    patient, not an outcome of the queue policy. (Weighting by
    service acuity would confound the comparison: a policy that lets
    patients deteriorate manufactures its own high-acuity class.)
    Used to compare the priority queue against the FIFO
    counterfactual on the harm each policy actually distributes.
    """
    starts = {}
    arrivals = {}
    acuities = {}
    for event in day.events if hasattr(day, "events") else day["events"]:
        if event["type"] == "arrival":
            arrivals[event["patient"]] = event["time"]
        elif event["type"] == "triage":
            acuities[event["patient"]] = event["recorded_acuity"]
        elif event["type"] == "service_start":
            starts[event["patient"]] = event["time"]
    totals = {}
    for patient_id, start in starts.items():
        wait = start - arrivals[patient_id]
        acuity = acuities[patient_id]
        entry = totals.setdefault(acuity, {"patients": 0, "wait_minutes": 0,
                                           "weighted_minutes": 0})
        entry["patients"] += 1
        entry["wait_minutes"] += wait
        entry["weighted_minutes"] += wait * (6 - acuity)
    return totals
