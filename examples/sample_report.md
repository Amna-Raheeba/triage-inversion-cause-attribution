<!-- Real output of: python examples/run_audit.py -->

# Demo-day audit

56 pairs detected in the log. Causes are attributed from log signatures only; post_hoc_deterioration means the detector judges the pair was not an inversion at decision time.

| Cause | Pairs | Excess wait (min) | Weighted burden |
|---|---|---|---|
| retriage_lag | 3 | 58 | 234 |
| resource_fit_preemption | 47 | 5316 | 15407 |
| batch_reassessment_timing | 4 | 394 | 1839 |
| post_hoc_deterioration | 2 | 209 | 975 |

## What each cause means

- **retriage_lag** -- The victim deteriorated while waiting; an abnormal vitals check was logged, but the protocol reassessment that should have followed it never happened before the beneficiary was taken, so the queue ordered by a stale score.
- **resource_fit_preemption** -- A fast-track room freed and took the beneficiary -- a low-acuity, short-service case that fit the room -- while the victim, who was not fast-track eligible, waited for a general room.
- **batch_reassessment_timing** -- The victim deteriorated after the last batch reassessment round and before the next one; no vitals check observed the change, so the recorded score was stale purely because of where the batch boundary fell.
- **post_hoc_deterioration** -- Not a decision-time inversion: the victim's recorded score was accurate when the beneficiary was taken; the victim only became more acute afterwards. The pair looks like an inversion in the log because service acuity is recorded when each patient's own treatment starts.

## Example pairs

| Time | Victim | Beneficiary | Cause | Victim acuity | Beneficiary acuity | Excess wait |
|---|---|---|---|---|---|---|
| 19 | P004 | P008 | resource_fit_preemption | 2 | 5 | 7 |
| 19 | P005 | P008 | resource_fit_preemption | 2 | 5 | 114 |
| 19 | P006 | P008 | resource_fit_preemption | 3 | 5 | 464 |
| 57 | P005 | P007 | batch_reassessment_timing | 2 | 3 | 76 |
| 104 | P005 | P016 | retriage_lag | 2 | 3 | 29 |

