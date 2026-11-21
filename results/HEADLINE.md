# Headline results

A cause-attributed inversion audit of a synthetic emergency-department queue: 200 seeded ED days, 23024 patients, 10076 planted decision-time inversions across three operational causes, plus 390 apparent pairs that only look like inversions. A log-only detector attributes each pair's cause from its signature in the queue log.

- Overall cause-label accuracy **0.977** (single-rule baseline 0.912); the cause-blind counter attributes nothing.
- Per-cause recall: re-triage lag **0.925**, resource-fit preemption **1.000**, batch reassessment timing **0.628**.
- The single-rule baseline never predicts batch timing (recall 0.000 there) -- the vitals/batch signature logic is what buys that cause.
- Apparent (post-hoc) pairs correctly declined: **0.705**. Hardest label by errors: **batch_reassessment_timing**.

Caveat: all days are synthetic and seeded, with causes planted by construction under declared simulation parameters; the audit measures detector behaviour on these mechanisms, not performance in a real emergency department.
