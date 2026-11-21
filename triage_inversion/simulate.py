"""Discrete-event simulation of one emergency-department day.

The simulator runs a minute-stepped queue: seeded arrivals, triage,
scheduled vitals checks, batch reassessment rounds, prompt
reassessments after abnormal vitals, and typed rooms (general +
fast-track). The queue orders waiting patients by *recorded* acuity;
the patient's *true* acuity can deteriorate while waiting, and the
recorded score only catches up at a reassessment. That gap -- plus
fast-track room fit -- is what plants inversions.

The simulator emits two separate artifacts:

- ``events``: the observable log (arrivals, triage scores, vitals
  severities, reassessments, batch rounds, service starts/ends).
  This is all the detector is allowed to read.
- ground truth: each patient's true acuity trajectory, and every
  decision-time inversion with the mechanism that produced it,
  determined from simulator state at the moment of the inversion.

Cause determination at the moment a beneficiary is taken:

- the taking room is fast-track -> ``resource_fit_preemption``
- else the victim's recorded score is stale, and an abnormal vitals
  check was logged after the victim's last assessment without a
  reassessment following it -> ``retriage_lag``
- else the victim's recorded score is stale with no observing vitals
  check -> ``batch_reassessment_timing``

Author: Amna Raheeba
"""

import random

from .models import (
    CAUSE_BATCH_TIMING,
    CAUSE_POST_HOC,
    CAUSE_RESOURCE_FIT,
    CAUSE_RETRIAGE_LAG,
    DEFAULT_SIM_CONFIG,
    DayResult,
    Inversion,
    PatientTruth,
)


def merged_config(config=None):
    cfg = dict(DEFAULT_SIM_CONFIG)
    if config:
        cfg.update(config)
    return cfg


class _PatientState(object):
    """Mutable per-patient simulation state."""

    def __init__(self, truth, expected_service):
        self.truth = truth
        self.expected_service = expected_service
        self.recorded = None            # recorded acuity (None pre-triage)
        self.last_assessment = None     # time recorded last changed
        self.next_vitals = None
        self.prompt_due = None          # scheduled prompt reassessment time
        self.service_start = None
        self.service_acuity = None
        self.vitals_history = []        # (time, abnormal) as observed in sim


def _draw_acuity(rng, probs):
    roll = rng.random()
    cumulative = 0.0
    for index, prob in enumerate(probs):
        cumulative += prob
        if roll < cumulative:
            return index + 1
    return len(probs)


def _generate_arrivals(rng, cfg):
    """Seeded arrival stream: (arrival_time, initial_acuity, expected_service)."""
    arrivals = []
    rate_per_minute = cfg["arrival_rate_per_hour"] / 60.0
    time = 0.0
    while True:
        time += rng.expovariate(rate_per_minute)
        minute = int(time)
        if minute >= cfg["day_minutes"]:
            break
        acuity = _draw_acuity(rng, cfg["initial_acuity_probs"])
        base = cfg["service_minutes"][acuity]
        expected = max(5, int(round(base * rng.uniform(0.8, 1.25))))
        arrivals.append((minute, acuity, expected))
    return arrivals


def simulate_day(day_index=0, seed=0, config=None):
    """Simulate one ED day and return a DayResult (log + ground truth)."""
    cfg = merged_config(config)
    rng = random.Random(seed)
    policy = cfg.get("policy", "priority")
    guard_wait = cfg.get("fasttrack_guard_wait")

    arrivals = _generate_arrivals(rng, cfg)
    arrival_map = {}
    for idx, (minute, acuity, expected) in enumerate(arrivals):
        patient_id = "P%03d" % (idx + 1)
        truth = PatientTruth(
            patient_id=patient_id,
            arrival=minute,
            initial_acuity=acuity,
            expected_service=expected,
            acuity_history=[(minute, acuity)],
        )
        arrival_map.setdefault(minute, []).append((truth, expected))

    events = []
    patients = {}          # patient_id -> _PatientState
    waiting = []           # patient_ids, kept in arrival order
    rooms = []
    for room_idx in range(cfg["n_general_rooms"]):
        rooms.append({"room": "G%d" % (room_idx + 1), "type": "general",
                      "busy_until": None, "current": None})
    for room_idx in range(cfg["n_fasttrack_rooms"]):
        rooms.append({"room": "F%d" % (room_idx + 1), "type": "fast_track",
                      "busy_until": None, "current": None})

    truth_inversions = []  # patched after the run
    victims_seen = set()   # victims whose first pass is already counted
    stats = {
        "n_patients": len(arrivals),
        "n_reassessments": 0,
        "n_prompt_reassessments": 0,
        "n_batch_reassessments": 0,
        "n_vitals": 0,
        "n_abnormal_vitals": 0,
        "fasttrack_busy_minutes": 0,
        "general_busy_minutes": 0,
    }

    def log(time, etype, **fields):
        event = {"time": time, "type": etype}
        event.update(fields)
        events.append(event)

    def do_reassessment(time, state, source):
        state.recorded = state.truth.true_acuity_at(time)
        state.last_assessment = time
        stats["n_reassessments"] += 1
        if source == "prompt":
            stats["n_prompt_reassessments"] += 1
        elif source == "batch":
            stats["n_batch_reassessments"] += 1
        log(time, "reassessment", patient=state.truth.patient_id,
            recorded_acuity=state.recorded, source=source)

    def pick_general(candidates):
        if policy == "fifo":
            return min(candidates, key=lambda pid: patients[pid].truth.arrival)
        return min(
            candidates,
            key=lambda pid: (patients[pid].recorded, patients[pid].truth.arrival),
        )

    def pick_fasttrack(candidates, time):
        eligible = [
            pid for pid in candidates
            if patients[pid].recorded in cfg["fasttrack_acuities"]
            and patients[pid].expected_service <= cfg["fasttrack_max_service"]
        ]
        if not eligible:
            return None
        if guard_wait is not None:
            for pid in candidates:
                state = patients[pid]
                if state.recorded <= 3 and time - state.truth.arrival >= guard_wait:
                    return None  # guard: hold the room for the sicker queue
        if policy == "fifo":
            return min(eligible, key=lambda pid: patients[pid].truth.arrival)
        return min(
            eligible,
            key=lambda pid: (patients[pid].recorded, patients[pid].truth.arrival),
        )

    def start_service(time, room, patient_id):
        state = patients[patient_id]
        waiting.remove(patient_id)
        service_acuity = state.truth.true_acuity_at(time)
        state.service_start = time
        state.service_acuity = service_acuity
        actual = max(1, int(round(state.expected_service * rng.uniform(0.9, 1.1))))
        room["busy_until"] = time + actual
        room["current"] = patient_id
        if room["type"] == "fast_track":
            stats["fasttrack_busy_minutes"] += actual
        else:
            stats["general_busy_minutes"] += actual
        log(time, "service_start", patient=patient_id, room=room["room"],
            room_type=room["type"], service_acuity=service_acuity)
        # Enumerate decision-time inversions created by this start.
        # A victim is counted once per cause: the first start that
        # passes them by that mechanism. (A patient first passed by a
        # fast-track pull and later passed again because their score
        # went stale has suffered two distinct inversions; repeated
        # passes by the same mechanism add to excess wait, not to
        # the pair count.)
        for other_id in list(waiting):
            other = patients[other_id]
            if other.truth.arrival >= state.truth.arrival:
                continue
            other_true = other.truth.true_acuity_at(time)
            if other_true >= service_acuity:
                continue
            if room["type"] == "fast_track":
                cause = CAUSE_RESOURCE_FIT
            elif any(
                vtime > (other.last_assessment or -1) and vtime <= time and abnormal
                for (vtime, abnormal) in other.vitals_history
            ):
                cause = CAUSE_RETRIAGE_LAG
            else:
                cause = CAUSE_BATCH_TIMING
            if (other_id, cause) in victims_seen:
                continue
            victims_seen.add((other_id, cause))
            inversion = Inversion(
                victim=other_id,
                beneficiary=patient_id,
                time=time,
                cause=cause,
                victim_service_acuity=0,  # patched when the victim is served
                beneficiary_service_acuity=service_acuity,
            )
            truth_inversions.append(inversion)

    hard_stop = cfg["day_minutes"] + 900
    time = 0
    while time <= hard_stop:
        # 1. Arrivals and triage.
        for truth, expected in arrival_map.get(time, []):
            state = _PatientState(truth, expected)
            patients[truth.patient_id] = state
            state.triage_time = time + cfg["triage_delay_minutes"]
            log(time, "arrival", patient=truth.patient_id)
        for state in list(patients.values()):
            if state.recorded is None and getattr(state, "triage_time", None) == time:
                state.recorded = state.truth.true_acuity_at(time)
                state.last_assessment = time
                state.next_vitals = time + cfg["vitals_interval_minutes"]
                waiting.append(state.truth.patient_id)
                log(time, "triage", patient=state.truth.patient_id,
                    recorded_acuity=state.recorded,
                    expected_service=state.expected_service)
        # 2. Deterioration of waiting patients (arrival order = deterministic).
        for patient_id in list(waiting):
            state = patients[patient_id]
            true_acuity = state.truth.true_acuity_at(time)
            hazard = cfg["deterioration_hazard"].get(true_acuity, 0.0)
            if hazard > 0 and rng.random() < hazard and true_acuity > 1:
                step = 2 if rng.random() < cfg["deterioration_two_step_prob"] else 1
                new_acuity = max(1, true_acuity - step)
                state.truth.acuity_history.append((time, new_acuity))
                state.truth.deterioration_times.append(time)
        # 3. Scheduled vitals checks.
        for patient_id in list(waiting):
            state = patients[patient_id]
            if state.next_vitals is not None and time >= state.next_vitals:
                true_acuity = state.truth.true_acuity_at(time)
                severity = (6 - true_acuity) + rng.uniform(
                    -cfg["vitals_noise"], cfg["vitals_noise"]
                )
                severity = round(severity, 2)
                abnormal = (severity - (6 - state.recorded)) >= cfg["abnormal_threshold"]
                state.vitals_history.append((time, abnormal))
                stats["n_vitals"] += 1
                if abnormal:
                    stats["n_abnormal_vitals"] += 1
                    if rng.random() < cfg["prompt_reassessment_prob"]:
                        state.prompt_due = time + rng.randint(1, 5)
                log(time, "vitals", patient=patient_id, severity=severity)
                state.next_vitals = time + cfg["vitals_interval_minutes"]
        # 4. Prompt reassessments that fell due.
        for patient_id in list(waiting):
            state = patients[patient_id]
            if state.prompt_due is not None and time >= state.prompt_due:
                state.prompt_due = None
                do_reassessment(time, state, "prompt")
        # 5. Batch reassessment rounds.
        if time > 0 and time % cfg["batch_interval_minutes"] == 0:
            log(time, "batch_round")
            for patient_id in list(waiting):
                state = patients[patient_id]
                if state.recorded != state.truth.true_acuity_at(time):
                    do_reassessment(time, state, "batch")
        # 6. Service completions.
        for room in rooms:
            if room["busy_until"] is not None and time >= room["busy_until"]:
                log(time, "service_end", patient=room["current"], room=room["room"])
                room["busy_until"] = None
                room["current"] = None
        # 7. Room assignment. Room types are respected under every
        # policy (a fast-track room can only take eligible cases);
        # the policy changes the *ordering* within each room's
        # candidate set, so policy comparisons isolate ordering.
        for room in rooms:
            if room["busy_until"] is not None or not waiting:
                continue
            if room["type"] == "fast_track":
                chosen = pick_fasttrack(waiting, time)
            else:
                chosen = pick_general(waiting)
            if chosen is not None:
                start_service(time, room, chosen)
        if len(patients) == len(arrivals) and not waiting and all(
            room["busy_until"] is None for room in rooms
        ) and time >= cfg["day_minutes"]:
            break
        time += 1

    # Patch victim service acuities and excess waits; compute apparent pairs.
    start_times = {}
    service_acuities = {}
    for event in events:
        if event["type"] == "service_start":
            start_times[event["patient"]] = event["time"]
            service_acuities[event["patient"]] = event["service_acuity"]
    for inversion in truth_inversions:
        inversion.victim_service_acuity = service_acuities.get(inversion.victim, 0)
        inversion.excess_wait_minutes = (
            start_times.get(inversion.victim, inversion.time) - inversion.time
        )
    decision_keys = set(
        (inv.victim, inv.beneficiary, inv.time) for inv in truth_inversions
    )
    apparent = []
    apparent_seen = set()
    # An apparent pair is recorded only for a victim whose first-ever
    # pass was apparent (they were not yet more acute when first
    # passed). A victim whose first pass was a genuine inversion is
    # already counted; later apparent passes of theirs are noise
    # around a counted victim, not a separate artifact record.
    earliest_decision = {}
    for inv in truth_inversions:
        if inv.victim not in earliest_decision or inv.time < earliest_decision[inv.victim]:
            earliest_decision[inv.victim] = inv.time
    arrivals_by_patient = dict(
        (pid, patients[pid].truth.arrival) for pid in patients
    )
    for beneficiary, start_b in sorted(start_times.items(), key=lambda kv: kv[1]):
        for victim, start_v in start_times.items():
            if victim == beneficiary or start_v <= start_b:
                continue
            if victim in apparent_seen:
                continue  # earliest apparent pass per victim only
            if victim in earliest_decision and start_b >= earliest_decision[victim]:
                continue  # first pass was a genuine inversion
            if arrivals_by_patient[victim] >= arrivals_by_patient[beneficiary]:
                continue
            if service_acuities[victim] >= service_acuities[beneficiary]:
                continue
            key = (victim, beneficiary, start_b)
            if key in decision_keys:
                continue
            apparent_seen.add(victim)
            apparent.append(Inversion(
                victim=victim,
                beneficiary=beneficiary,
                time=start_b,
                cause=CAUSE_POST_HOC,
                victim_service_acuity=service_acuities[victim],
                beneficiary_service_acuity=service_acuities[beneficiary],
                excess_wait_minutes=start_v - start_b,
            ))
    apparent.sort(key=lambda inv: (inv.time, inv.victim, inv.beneficiary))

    waits = [
        start_times[pid] - patients[pid].truth.arrival
        for pid in start_times
    ]
    stats["n_served"] = len(start_times)
    stats["mean_wait_minutes"] = round(sum(waits) / float(len(waits)), 3) if waits else 0.0
    stats["n_inversions"] = len(truth_inversions)
    stats["n_apparent_pairs"] = len(apparent)

    return DayResult(
        day_index=day_index,
        seed=seed,
        events=events,
        patients=dict((pid, s.truth) for pid, s in patients.items()),
        inversions=truth_inversions,
        apparent_pairs=apparent,
        stats=stats,
    )
