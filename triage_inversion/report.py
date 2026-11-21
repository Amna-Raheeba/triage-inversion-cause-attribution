"""Markdown reports for a detector audit of one or more ED days.

Author: Amna Raheeba
"""

from .detect import burden_by_cause
from .models import ALL_LABELS, CAUSE_DESCRIPTIONS


def audit_report_markdown(detected, title="Triage-inversion audit"):
    """Report detected pairs grouped by attributed cause."""
    lines = ["# %s" % title, ""]
    lines.append(
        "%d pairs detected in the log. Causes are attributed from log "
        "signatures only; post_hoc_deterioration means the detector "
        "judges the pair was not an inversion at decision time."
        % len(detected)
    )
    lines.append("")
    burden = burden_by_cause(detected)
    lines.append("| Cause | Pairs | Excess wait (min) | Weighted burden |")
    lines.append("|---|---|---|---|")
    for cause in ALL_LABELS:
        entry = burden.get(cause, {"pairs": 0, "excess_minutes": 0, "weighted_minutes": 0})
        lines.append(
            "| %s | %d | %d | %d |"
            % (cause, entry["pairs"], entry["excess_minutes"], entry["weighted_minutes"])
        )
    lines.append("")
    lines.append("## What each cause means")
    lines.append("")
    for cause in ALL_LABELS:
        lines.append("- **%s** -- %s" % (cause, CAUSE_DESCRIPTIONS[cause]))
    return "\n".join(lines) + "\n"


def inversion_examples_markdown(detected, limit=5):
    """A few detected pairs, earliest first, for eyeballing."""
    lines = ["## Example pairs", ""]
    shown = detected[:limit]
    if not shown:
        lines.append("No pairs detected.")
        return "\n".join(lines) + "\n"
    lines.append("| Time | Victim | Beneficiary | Cause | Victim acuity | Beneficiary acuity | Excess wait |")
    lines.append("|---|---|---|---|---|---|---|")
    for inversion in shown:
        lines.append(
            "| %d | %s | %s | %s | %d | %d | %d |"
            % (
                inversion.time, inversion.victim, inversion.beneficiary,
                inversion.cause, inversion.victim_service_acuity,
                inversion.beneficiary_service_acuity,
                inversion.excess_wait_minutes,
            )
        )
    return "\n".join(lines) + "\n"
