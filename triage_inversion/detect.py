"""Log-only inversion detector and cause attributor.

The detector reads only the observable event log of an ED day -- the
same fields a real queue log would carry -- and never sees true
acuity or deterioration times. It reconstructs each patient's
timeline (arrival, recorded-score history, vitals severities,
assessments, service start, room type, service acuity) and:

1. **Detects inversion pairs.** A pair (victim, beneficiary) is
   detected when the beneficiary starts service while the victim --
   who arrived earlier and whose *service* acuity (recorded when the
   victim's own treatment finally starts) is more urgent than the
   beneficiary's -- is still waiting.
2. **Attributes a cause** to each pair from its log signature, in a
   fixed decision order:

   - the beneficiary was taken by a fast-track room ->
     ``resource_fit_preemption``
   - the victim has an abnormal vitals check (severity at least
     ``abnormal_threshold`` above what the recorded score implies)
     after the victim's last assessment and at or before the
     beneficiary's start, with no reassessment in between ->
     ``retriage_lag``
   - a vitals check after the victim's last assessment reads
     borderline (severity excess between the noise band and the
     abnormal threshold) -> ``batch_reassessment_timing`` (the check
     half-observed a deterioration that predates the start)
   - the victim's first vitals check after the start is clean but a
     later one is abnormal -> ``post_hoc_deterioration`` (the
     deterioration is bracketed after the start, so the recorded
     score was accurate at decision time; the detector declines to
     call it a decision-time inversion)
   - otherwise -> ``batch_reassessment_timing``

The detector's known blind spot is structural: a victim who
deteriorated shortly before the beneficiary's start, with no vitals
check in between, leaves the same log signature as one who
deteriorated shortly after. The evaluation measures how much that
costs; the detector does not pretend otherwise.

Author: Amna Raheeba
"""

from .models import (
    CAUSE_BATCH_TIMING,
    CAUSE_POST_HOC,
    CAUSE_RESOURCE_FIT,
    CAUSE_RETRIAGE_LAG,
    DEFAULT_SIM_CONFIG,
    Inversion,
)


class PatientTimeline(object):
    """One patient's detector-visible timeline, rebuilt from the log."""

    def __init__(self, patient_id):
        self.patient_id = patient_id
        self.arrival = None
        self.expected_service = None
        self.score_history = []   # (time, recorded_acuity), chronological
        self.vitals = []          # (time, severity), chronological
        self.service_start = None
        self.service_room = None
        self.service_room_type = None
        self.service_acuity = None

    def recorded_at(self, time):
        """Recorded acuity in force at ``time`` (None before triage)."""
        score = None
        for change_time, acuity in self.score_history:
            if change_time <= time:
                score = acuity
            else:
                break
        return score

    def last_assessment_before(self, time):
        """Time of the last score change at or before ``time``."""
        last = None
        for change_time, _acuity in self.score_history:
            if change_time <= time:
                last = change_time
            else:
                break
        return last

    def abnormal_vitals(self, start, end, threshold):
        """Abnormal vitals times in (start, end] given the score in force.

        A check is abnormal when its severity exceeds what the
        recorded score at that moment implies by >= threshold.
        """
        found = []
        for vtime, severity in self.vitals:
            if vtime <= start or vtime > end:
                continue
            recorded = self.recorded_at(vtime)
            if recorded is None:
                continue
            if severity - (6 - recorded) >= threshold:
                found.append(vtime)
        return found


def build_timelines(events):
    """Rebuild per-patient timelines from a day's event log."""
    timelines = {}
    arrivals = {}

    def get(patient_id):
        if patient_id not in timelines:
            timelines[patient_id] = PatientTimeline(patient_id)
        return timelines[patient_id]

    for event in events:
        etype = event["type"]
        if etype == "arrival":
            arrivals[event["patient"]] = event["time"]
        elif etype == "triage":
            timeline = get(event["patient"])
            timeline.score_history.append((event["time"], event["recorded_acuity"]))
            timeline.expected_service = event.get("expected_service")
        elif etype == "reassessment":
            timeline = get(event["patient"])
            timeline.score_history.append((event["time"], event["recorded_acuity"]))
        elif etype == "vitals":
            timeline = get(event["patient"])
            timeline.vitals.append((event["time"], event["severity"]))
        elif etype == "service_start":
            timeline = get(event["patient"])
            timeline.service_start = event["time"]
            timeline.service_room = event["room"]
            timeline.service_room_type = event["room_type"]
            timeline.service_acuity = event["service_acuity"]
    # Arrivals are derivable from the log only via triage order; the
    # simulator logs an explicit arrival event for each patient. If a
    # log lacks one, fall back to the first score change.
    for patient_id, timeline in timelines.items():
        if patient_id in arrivals:
            timeline.arrival = arrivals[patient_id]
        elif timeline.score_history:
            timeline.arrival = timeline.score_history[0][0]
    return timelines


def detect_inversions(events, config=None):
    """Detect inversion pairs in one day's log and attribute causes.

    Returns a list of Inversion with predicted causes (including
    ``post_hoc_deterioration`` for pairs the detector judges were not
    decision-time inversions).
    """
    cfg = dict(DEFAULT_SIM_CONFIG)
    if config:
        cfg.update(config)
    threshold = cfg["abnormal_threshold"]
    timelines = build_timelines(events)
    served = [
        timeline for timeline in timelines.values()
        if timeline.service_start is not None
    ]
    detected = []
    for beneficiary in served:
        start_b = beneficiary.service_start
        for victim in served:
            if victim.patient_id == beneficiary.patient_id:
                continue
            if victim.service_start is None or victim.service_start <= start_b:
                continue
            if victim.arrival is None or beneficiary.arrival is None:
                continue
            if victim.arrival >= beneficiary.arrival:
                continue
            if victim.service_acuity >= beneficiary.service_acuity:
                continue
            cause = _attribute_cause(victim, beneficiary, threshold)
            detected.append(Inversion(
                victim=victim.patient_id,
                beneficiary=beneficiary.patient_id,
                time=start_b,
                cause=cause,
                victim_service_acuity=victim.service_acuity,
                beneficiary_service_acuity=beneficiary.service_acuity,
                excess_wait_minutes=victim.service_start - start_b,
            ))
    detected.sort(key=lambda inv: (inv.time, inv.victim, inv.beneficiary))
    # One pair per (victim, attributed cause): the first pass by
    # that mechanism. Repeated passes by the same mechanism add to
    # excess wait, not to the pair count (same convention as the
    # ground-truth enumeration).
    seen = set()
    first_passes = []
    for inversion in detected:
        key = (inversion.victim, inversion.cause)
        if key in seen:
            continue
        seen.add(key)
        first_passes.append(inversion)
    return first_passes


def _attribute_cause(victim, beneficiary, threshold):
    start = beneficiary.service_start
    if beneficiary.service_room_type == "fast_track":
        return CAUSE_RESOURCE_FIT
    last_assessment = victim.last_assessment_before(start)
    window_start = last_assessment if last_assessment is not None else -1
    abnormal_before = victim.abnormal_vitals(window_start, start, threshold)
    if abnormal_before:
        return CAUSE_RETRIAGE_LAG
    # Sub-threshold elevation: a vitals check after the last
    # assessment whose severity excess sits between the noise band
    # (0.4) and the abnormal threshold is evidence the victim had
    # already deteriorated before the start -- the check observed
    # the deterioration but read it as borderline. Batch timing,
    # not post-hoc.
    for vtime, severity in victim.vitals:
        if window_start < vtime <= start:
            recorded = victim.recorded_at(vtime)
            if recorded is not None and 0.4 <= severity - (6 - recorded) < threshold:
                return CAUSE_BATCH_TIMING
    # Post-start vitals pattern: if the victim's first vitals check
    # after the start is clean but a later one is abnormal, the
    # deterioration happened between those checks -- after the
    # start -- so the recorded score was accurate at decision time.
    # (If the first post-start check is already abnormal, the
    # deterioration most likely predates it: batch timing.)
    post_checks = [
        (vtime, severity) for (vtime, severity) in victim.vitals
        if start < vtime <= victim.service_start
    ]
    if post_checks:
        first_time, first_severity = post_checks[0]
        first_recorded = victim.recorded_at(first_time)
        first_clean = (
            first_recorded is not None
            and first_severity - (6 - first_recorded) < 0.4
        )
        later_abnormal = victim.abnormal_vitals(
            first_time, victim.service_start, threshold
        )
        if first_clean and later_abnormal:
            return CAUSE_POST_HOC
    return CAUSE_BATCH_TIMING


def burden_by_cause(inversions):
    """Total and urgency-weighted excess wait minutes per cause."""
    burden = {}
    for inversion in inversions:
        entry = burden.setdefault(
            inversion.cause, {"pairs": 0, "excess_minutes": 0, "weighted_minutes": 0}
        )
        entry["pairs"] += 1
        entry["excess_minutes"] += inversion.excess_wait_minutes
        entry["weighted_minutes"] += inversion.weighted_burden
    return burden
