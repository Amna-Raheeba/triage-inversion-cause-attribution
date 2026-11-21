# Triage Inversion Cause Attribution

A **cause-attributed audit** of an emergency-department priority
queue: it detects *priority inversions* — a less acute patient
treated before a more acute one who arrived earlier and waited
longer — and attributes each inversion to the operational mechanism
that produced it, instead of scoring triage accuracy in aggregate.

## 1. What it is

Triage audits usually ask "how accurate was the triage score?" This
tool asks a different question: when the queue served the wrong
patient first, *why*? The answer matters because the fixes differ —
and because many inversions are not errors at all, but deliberate
policy (a fast-track room doing exactly what it was built to do).

A seeded discrete-event simulation generates synthetic ED days
(arrivals, acuity levels, deterioration while waiting, vitals
checks, reassessment rounds, typed rooms). Inversions are planted by
three distinct mechanisms, recorded as ground truth. A detector that
reads **only the queue log** — never the truth — must find each
inversion and classify its cause from its log signature. Everything
is offline, deterministic and seeded. Pure Python standard library;
no API keys, no model downloads, no network. All patients are
synthetic; there is no real patient data anywhere in this repo.

## 2. The novel mechanism

**Planted causes + a log-only attributor.** The simulator's queue
orders patients by *recorded* acuity, while *true* acuity can
deteriorate during the wait. That gap, plus room fit, plants
inversions through three mechanisms:

1. **retriage_lag** — the victim deteriorates; a vitals check logs
   an abnormal severity, but the protocol reassessment that should
   follow it never happens before a less acute patient is taken.
   The queue ordered by a stale score nobody was alerted to fix.
2. **resource_fit_preemption** — a fast-track room frees and takes
   a low-acuity, short-service case that fits the room, while a
   sicker patient who cannot use that room keeps waiting.
   Deliberate policy, not an error — but it is still an inversion,
   and it carries most of the burden (below).
3. **batch_reassessment_timing** — the victim deteriorates after
   the last batch reassessment round; no vitals check observes the
   change, so the score is stale purely because of where the batch
   boundary fell.

A fourth label, **post_hoc_deterioration**, covers *apparent* pairs:
the victim's recorded score was accurate when the beneficiary was
taken, and they only became more acute afterwards. Such pairs look
like inversions in any log that records acuity at each patient's own
service start, and an honest audit must decline them rather than
count them.

**Counting convention.** A victim is counted once per cause — the
first pass by that mechanism. A patient passed first by a fast-track
pull and later by a stale score has suffered two distinct
inversions; repeated passes by the same mechanism add to their
excess wait, not to the pair count.

**Counterfactual repair.** Each attributed cause maps to a repair,
and the audit re-simulates the same seeded days with one mechanism
repaired (prompt reassessment always fires; batch rounds every 10
minutes; a fast-track guard). A repair should remove mainly *its
own* cause — which cross-validates the attribution — and its
operational cost is measured, not asserted.

## 3. Prior art and the differentiator

- **ESI / MTS validity studies** score triage assignments against
  expert panels: was the *score* right?
- **The 2026 Triage Effectiveness framework** quantifies
  prioritisation effectiveness with waiting-time and rank-based
  measures, and notes post-triage reprioritisation gaps.

Neither attributes *individual inversions* to operational causes,
and neither benchmarks a detector against planted causes with known
ground truth. That measurement — which mechanism produced how much
inversion burden, and whether a log-only detector can tell the
mechanisms apart — is the differentiator. Paper angle: *"Not all
inversions are errors: cause-attributed auditing of
emergency-department priority queues."*

## 4. Measured headline results

Seeded evaluation: 200 ED days, 23,024 patients, base seed
20261121, under the declared parameters of §6. The simulator
planted **10,076 decision-time inversions** (resource-fit 9,488;
re-triage lag 322; batch timing 266) plus **390 apparent pairs**.
Full detail in `results/`.

| Cause | Truth pairs | Detector P | Detector R | Detector F1 | Single-rule R |
|---|---|---|---|---|---|
| retriage_lag | 322 | 0.828 | 0.925 | 0.874 | 0.193 |
| resource_fit_preemption | 9,488 | 1.000 | 1.000 | 1.000 | 1.000 |
| batch_reassessment_timing | 266 | 0.233 | 0.628 | 0.340 | 0.000 |

- Overall cause-label accuracy **0.977** for the detector vs
  **0.912** for a single-rule baseline (fast-track → resource-fit,
  everything else → re-triage lag). The cause-blind counter reports
  9,589 passed-over patients and attributes nothing.
- The detector declines **70.5%** of apparent (post-hoc) pairs
  correctly; the rest are mostly labelled batch timing — the known
  blind spot of §8.
- **Burden is dominated by deliberate policy.** Urgency-weighted
  excess wait (truth): resource-fit 3,534,373 weighted minutes over
  9,488 pairs; re-triage lag 31,314 over 322; batch timing 28,681
  over 266. The stale-score causes are ~5% of pairs but are the
  *unintended* inversions — the ones an audit exists to find.
- Detector-attributed burden tracks truth closely for resource-fit
  (3,534,460) and re-triage lag (41,704), but overstates batch
  timing ~7× (201,575 vs 28,681) — the burden shadow of batch's low
  precision, reported rather than hidden.
- **FIFO counterfactual** (50 paired days, same rooms and
  arrivals, arrival-order selection): urgency-weighted total wait
  899,676 vs the priority queue's 944,812 — but the mean wait of
  triage-acuity 1–2 patients is **118.0 min under FIFO vs 20.4 min**
  under priority ordering. FIFO's inversion count is *higher*
  (2,703 vs 2,365) and every one is a resource-fit pass: arrival
  ordering removes the stale-score causes entirely, yet longer
  uniform waits leave more sick patients exposed to each fast-track
  pull.

## 5. Quick start

```bash
pip install -r requirements.txt

python -m triage_inversion demo                    # 3 seeded days, audited
python -m triage_inversion audit --days examples/demo_day.json
python -m triage_inversion evaluate                # regenerate results/
python examples/run_audit.py                       # audit via the example script
streamlit run app.py                               # dashboard (3 tabs)
```

Days format: JSON with a `days` list; each day has `day_index`,
`seed`, `events` (the detector-visible log), `stats`, and — stored
separately from the log — `inversions` and `apparent_pairs` ground
truth. See `data/days.json` (20 seeded days).

## 6. How it works

1. **Simulate** — a minute-stepped queue: seeded arrivals (~9.5/hr
   over a 12-hour day), triage after 2 min, 3 general rooms + 1
   fast-track room (lowest-acuity, ≤15 min expected service),
   vitals checks every 20 min (severity = true-acuity signal +
   noise), batch reassessment rounds every 60 min, prompt
   reassessment after an abnormal vitals check with probability
   0.4. Waiting patients deteriorate at declared per-minute hazards
   by acuity (0.002–0.0035), dropping 1 acuity level, or 2 with
   probability 0.3. Every parameter is declared in
   `triage_inversion/models.py`.
2. **Detect** — the detector rebuilds each patient's timeline from
   the log and applies a fixed decision order per pair: fast-track
   start → resource-fit; abnormal vitals after the victim's last
   assessment, unacted → re-triage lag; borderline vitals excess
   (between the noise band and the abnormal threshold) → batch
   timing; first post-start vitals clean but a later one abnormal
   → post-hoc; otherwise → batch timing.
3. **Score** — per-cause precision/recall against the planted
   truth, scored per day and merged (patient ids repeat across
   days, so pair keys are only unique within a day).
4. **Repair** — re-simulate paired days with one mechanism fixed
   and compare inversions removed against operational cost.

## 7. Counterfactual repairs (50 paired days)

Base: 2,365 inversions (resource-fit 2,225; re-triage lag 77; batch
timing 63), 740 reassessments, mean wait 70.7 min.

| Repair | Target | Removed (target) | Side effects | Cost |
|---|---|---|---|---|
| prompt_retriage | re-triage lag | 54 of 77 (70%) | batch +10, resource +10 | reassessments 740 → 797 |
| frequent_batch | batch timing | 41 of 63 (65%) | also removes 74 of 77 re-triage lag | reassessments 740 → 937 (+27%) |
| fasttrack_guard | resource-fit | 966 of 2,225 (43%) | re-triage +6, batch +2 | mean wait 70.7 → 82.3 min; fast-track busy 7,680 → 7,205 min |

Each repair removes mainly its own cause, which cross-validates the
attribution. The side effects are real queue dynamics, reported as
measured: fixing scores earlier reorders the queue and creates a
few inversions elsewhere; the fast-track guard is the most
effective repair in absolute terms and the most expensive — holding
the fast-track room for the sicker queue costs ~12 minutes of mean
wait across *all* patients.

## 8. Honest limits

- **Synthetic days, declared parameters.** Arrival rates,
  deterioration hazards, vitals noise and the reassessment policy
  are simulation assumptions chosen to exercise the mechanisms, not
  measurements of any real ED. The audit measures detector
  behaviour and mechanism costs *under those parameters*.
- **Batch timing is the residual cause, and it shows.** Its
  precision (0.233) is low because its signature is an absence: a
  deterioration shortly before a beneficiary's start with no vitals
  check in between is log-identical to one shortly after the start.
  The detector's borderline-vitals and post-start-bracketing rules
  recover part of the distinction (recall 0.628, 70.5% of apparent
  pairs declined); the rest is structural ambiguity, priced in the
  scores rather than designed away.
- **Pair detection is exact by construction in this log design:**
  service acuity is recorded for every patient, so the detector
  sees every candidate pair. The scientific content is the *cause
  attribution*, the burden split, and the repair costs — not pair
  recall. Real logs with missing service acuities would degrade
  detection as well.
- **The simulator's truth labels for stale-score passes** are
  determined by whether an abnormal vitals check was logged and
  left unacted — the same evidence the detector uses — so re-triage
  lag scores partly measure implementation agreement. The
  non-circular results are the baselines' structural failures (the
  single-rule baseline can never name batch timing; the blind
  counter can never name anything) and the repair cross-checks,
  where removing a mechanism removes mainly its own cause.
