# Changelog

## 0.1.0 — 2026-11-21

- Initial release.
- Seeded discrete-event ED simulator (minute-stepped queue: arrivals,
  triage, deterioration while waiting, scheduled vitals checks, batch
  reassessment rounds, prompt reassessments, general + fast-track
  rooms) that plants priority inversions by three mechanisms —
  re-triage lag, resource-fit preemption, batch reassessment timing —
  and records each inversion's cause as ground truth, plus apparent
  (post-hoc) pairs whose victims only became more acute after being
  passed.
- Log-only detector that rebuilds patient timelines from the event
  log and attributes each detected pair to a cause from its
  signature: room type, unacted abnormal vitals, borderline severity
  excess, and post-start vitals bracketing.
- Baselines: a cause-blind inversion counter, a single-rule
  classifier (fast-track → resource-fit, else re-triage lag), and a
  FIFO counterfactual queue (same rooms and arrivals, arrival-order
  selection) for burden comparison.
- Counterfactual repairs: prompt re-triage, frequent batch rounds,
  and a fast-track guard, each re-simulated on paired seeds with
  inversions removed per cause and operational costs measured.
- Headline evaluation: 200 seeded days / 23,024 patients; detector
  cause-label accuracy 0.977 vs 0.912 single-rule; per-cause recall
  0.925 (re-triage lag), 1.000 (resource-fit), 0.628 (batch timing);
  70.5% of apparent pairs correctly declined; batch precision 0.233
  reported as the structural blind spot.
- Streamlit dashboard (3 tabs), CLI, notebooks, and a
  reproducibility script with a headline-drift guard.
