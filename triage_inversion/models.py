"""Data model for the triage-inversion cause-attribution audit.

An *ED day* is a list of observable log events produced by a seeded
discrete-event simulation of an emergency-department queue. The
detector reads only the log. Ground truth -- which pairs were real
decision-time inversions, and which planted mechanism produced each
one -- is recorded separately by the simulator and never appears in
the log events the detector consumes.

An *inversion* is a pair (victim, beneficiary): the beneficiary starts
treatment at time t while the victim -- who arrived earlier, waited
longer, and was truly more acute at t -- is still waiting. Acuity uses
an ESI-like 1..5 scale where 1 is most urgent.

All patients and events are synthetic. No real patient data.

Author: Amna Raheeba
"""

from dataclasses import dataclass, field

# Causes planted by the simulator (decision-time inversions).
CAUSE_RETRIAGE_LAG = "retriage_lag"
CAUSE_RESOURCE_FIT = "resource_fit_preemption"
CAUSE_BATCH_TIMING = "batch_reassessment_timing"
# Apparent pairs: the victim only became more acute *after* the
# beneficiary started, so no inversion existed at decision time.
CAUSE_POST_HOC = "post_hoc_deterioration"

CAUSES = (CAUSE_RETRIAGE_LAG, CAUSE_RESOURCE_FIT, CAUSE_BATCH_TIMING)
ALL_LABELS = CAUSES + (CAUSE_POST_HOC,)

CAUSE_DESCRIPTIONS = {
    CAUSE_RETRIAGE_LAG: (
        "The victim deteriorated while waiting; an abnormal vitals "
        "check was logged, but the protocol reassessment that should "
        "have followed it never happened before the beneficiary was "
        "taken, so the queue ordered by a stale score."
    ),
    CAUSE_RESOURCE_FIT: (
        "A fast-track room freed and took the beneficiary -- a low-"
        "acuity, short-service case that fit the room -- while the "
        "victim, who was not fast-track eligible, waited for a "
        "general room."
    ),
    CAUSE_BATCH_TIMING: (
        "The victim deteriorated after the last batch reassessment "
        "round and before the next one; no vitals check observed the "
        "change, so the recorded score was stale purely because of "
        "where the batch boundary fell."
    ),
    CAUSE_POST_HOC: (
        "Not a decision-time inversion: the victim's recorded score "
        "was accurate when the beneficiary was taken; the victim "
        "only became more acute afterwards. The pair looks like an "
        "inversion in the log because service acuity is recorded "
        "when each patient's own treatment starts."
    ),
}

# Default simulation configuration. Every parameter is declared here;
# the experiment measures the mechanisms under these settings, and the
# README states them as assumptions, not measurements of a real ED.
DEFAULT_SIM_CONFIG = {
    "day_minutes": 720,            # 12-hour ED day
    "arrival_rate_per_hour": 9.5,  # ~115 arrivals per day (busy department)
    "n_general_rooms": 3,
    "n_fasttrack_rooms": 1,
    "triage_delay_minutes": 2,
    "batch_interval_minutes": 60,  # batch reassessment rounds
    "vitals_interval_minutes": 20,  # scheduled vitals checks
    "protocol_window_minutes": 15,  # reassessment due after abnormal vitals
    "prompt_reassessment_prob": 0.4,  # chance abnormal vitals trigger one
    "abnormal_threshold": 0.8,     # severity excess that reads as abnormal
    "vitals_noise": 0.4,           # uniform noise on the severity readout
    "fasttrack_max_service": 15,   # minutes of expected service
    "fasttrack_acuities": (5,),    # lowest-acuity stream only
    "initial_acuity_probs": (0.03, 0.17, 0.35, 0.30, 0.15),
    "service_minutes": {1: 45, 2: 35, 3: 25, 4: 15, 5: 10},
    # Per-minute deterioration hazard while waiting, by true acuity.
    # These are declared simulation parameters for a busy department
    # with a deteriorating case-mix, not measurements of a real ED.
    "deterioration_hazard": {1: 0.0, 2: 0.002, 3: 0.0035, 4: 0.002, 5: 0.0007},
    # A deterioration event drops acuity by 1 level, or by 2 levels
    # (a sharp decline, e.g. progressing sepsis) with this probability.
    # Two-level drops matter: a one-level stale score can only tie the
    # patient the queue takes instead, never strictly invert them.
    "deterioration_two_step_prob": 0.3,
}


@dataclass
class PatientTruth:
    """Ground-truth state for one patient (never in the detector log)."""

    patient_id: str
    arrival: int
    initial_acuity: int
    expected_service: int
    # List of (time, new_true_acuity) change points, starting at arrival.
    acuity_history: list = field(default_factory=list)
    deterioration_times: list = field(default_factory=list)

    def true_acuity_at(self, time):
        acuity = self.initial_acuity
        for change_time, new_acuity in self.acuity_history:
            if change_time <= time:
                acuity = new_acuity
            else:
                break
        return acuity


@dataclass
class Inversion:
    """One inversion (or apparent pair), from truth or from detection."""

    victim: str
    beneficiary: str
    time: int                 # beneficiary service-start time
    cause: str
    victim_service_acuity: int = 0
    beneficiary_service_acuity: int = 0
    excess_wait_minutes: int = 0   # victim's wait beyond the inversion time

    @property
    def weighted_burden(self):
        """Excess wait weighted by victim urgency (acuity 1 weighs 5)."""
        return self.excess_wait_minutes * (6 - self.victim_service_acuity)

    def to_dict(self):
        return {
            "victim": self.victim,
            "beneficiary": self.beneficiary,
            "time": self.time,
            "cause": self.cause,
            "victim_service_acuity": self.victim_service_acuity,
            "beneficiary_service_acuity": self.beneficiary_service_acuity,
            "excess_wait_minutes": self.excess_wait_minutes,
            "weighted_burden": self.weighted_burden,
        }


def inversion_from_dict(data):
    return Inversion(
        victim=data["victim"],
        beneficiary=data["beneficiary"],
        time=data["time"],
        cause=data["cause"],
        victim_service_acuity=data.get("victim_service_acuity", 0),
        beneficiary_service_acuity=data.get("beneficiary_service_acuity", 0),
        excess_wait_minutes=data.get("excess_wait_minutes", 0),
    )


@dataclass
class DayResult:
    """One simulated ED day: observable log plus ground truth."""

    day_index: int
    seed: int
    events: list = field(default_factory=list)        # detector-visible log
    patients: dict = field(default_factory=dict)      # patient_id -> PatientTruth
    inversions: list = field(default_factory=list)    # decision-time, truth
    apparent_pairs: list = field(default_factory=list)  # post-hoc pairs, truth
    stats: dict = field(default_factory=dict)

    def to_dict(self, include_truth=True):
        data = {
            "day_index": self.day_index,
            "seed": self.seed,
            "events": self.events,
            "stats": self.stats,
        }
        if include_truth:
            data["inversions"] = [inv.to_dict() for inv in self.inversions]
            data["apparent_pairs"] = [inv.to_dict() for inv in self.apparent_pairs]
        return data
