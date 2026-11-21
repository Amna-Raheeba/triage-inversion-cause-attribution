# Evaluation summary

Seeded discrete-event ED simulation: 200 days, 23024 patients, base seed 20261121. Ground truth is planted by the simulator; the detector reads only the event log. All clinical content is synthetic.

## Cause attribution

| Cause | Truth pairs | Detector P | Detector R | Detector F1 | Single-rule R |
|---|---|---|---|---|---|
| retriage_lag | 322 | 0.828 | 0.925 | 0.874 | 0.193 |
| resource_fit_preemption | 9488 | 1.000 | 1.000 | 1.000 | 1.000 |
| batch_reassessment_timing | 266 | 0.233 | 0.628 | 0.340 | 0.000 |

- Truth: 10076 decision-time inversions, 390 apparent (post-hoc) pairs.
- Detector: overall label accuracy 0.977; decision-time detection rate 0.988; apparent pairs correctly declined 0.705.
- Single-rule baseline: overall label accuracy 0.912.
- Cause-blind counter: 9589 pairs counted, no cause attributed.

## Burden (urgency-weighted excess wait minutes, truth)

- retriage_lag: truth 31314 weighted minutes over 322 pairs; detector attributes 41704.
- resource_fit_preemption: truth 3534373 weighted minutes over 9488 pairs; detector attributes 3534460.
- batch_reassessment_timing: truth 28681 weighted minutes over 266 pairs; detector attributes 201575.

## FIFO counterfactual (50 paired days)

- Same rooms and arrivals, pure arrival-order selection. Urgency-weighted total wait (triage-acuity basis), priority queue: 944812; FIFO: 899676 (ratio 0.952). Mean wait of triage-acuity 1-2 patients: priority 20.4 min, FIFO 118.0 min. Inversions: priority 2365, FIFO 2703 -- every FIFO inversion is a fast-track resource-fit pass (arrival ordering removes the stale-score causes entirely), and FIFO's are more numerous because uniformly longer waits leave more sick patients exposed in the pool each fast-track pull draws past.

## Counterfactual repairs (50 paired days)

- fasttrack_guard (targets resource_fit_preemption): inversions removed by cause -- retriage_lag -6, resource_fit_preemption +966, batch_reassessment_timing -2 (negative = that cause increased under the repair); total inversions 2365 -> 1407; reassessments 803; fast-track busy minutes 7205; mean wait 82.3.
- frequent_batch (targets batch_reassessment_timing): inversions removed by cause -- retriage_lag +74, resource_fit_preemption +14, batch_reassessment_timing +41 (negative = that cause increased under the repair); total inversions 2365 -> 2236; reassessments 937; fast-track busy minutes 7652; mean wait 69.4.
- prompt_retriage (targets retriage_lag): inversions removed by cause -- retriage_lag +54, resource_fit_preemption -10, batch_reassessment_timing -10 (negative = that cause increased under the repair); total inversions 2365 -> 2331; reassessments 797; fast-track busy minutes 7714; mean wait 69.8.

## Caveats

- Synthetic seeded days under declared simulation parameters (arrival rate, deterioration hazards, reassessment policy); the audit measures detector behaviour and mechanism costs under those parameters, not a real ED's inversion rate.
- The detector's structural blind spot: deterioration shortly before a beneficiary's start with no vitals check in between is log-identical to deterioration shortly after it; the post-hoc and batch-timing scores price that ambiguity.
