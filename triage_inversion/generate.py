"""Seeded generation of ED days and JSON serialization.

A *corpus* is a list of DayResult dicts (see models.DayResult): each
carries the detector-visible event log and, under separate keys, the
ground-truth inversions and apparent pairs. The detector consumes
only ``events``; the truth keys exist so the audit can be scored.

Author: Amna Raheeba
"""

from .models import inversion_from_dict
from .simulate import simulate_day


def generate_days(n_days, base_seed, config=None):
    """Simulate ``n_days`` days with per-day seeds base_seed + index."""
    return [
        simulate_day(day_index=index, seed=base_seed + index, config=config)
        for index in range(n_days)
    ]


def days_to_dict(days):
    return {"days": [day.to_dict() for day in days]}


def days_from_dict(data):
    """Rebuild lightweight day records from stored JSON.

    Only the fields the audit pipeline needs are restored: events,
    truth inversions, apparent pairs and stats. Patient truth
    trajectories are not stored (they are large and the detector
    never reads them).
    """
    days = []
    for entry in data["days"]:
        days.append({
            "day_index": entry["day_index"],
            "seed": entry["seed"],
            "events": entry["events"],
            "inversions": [inversion_from_dict(d) for d in entry.get("inversions", [])],
            "apparent_pairs": [
                inversion_from_dict(d) for d in entry.get("apparent_pairs", [])
            ],
            "stats": entry.get("stats", {}),
        })
    return days


def day_events(day):
    """Events of a day, whether a DayResult or a restored dict."""
    return day.events if hasattr(day, "events") else day["events"]


def day_inversions(day):
    return day.inversions if hasattr(day, "inversions") else day["inversions"]


def day_apparent(day):
    if hasattr(day, "apparent_pairs"):
        return day.apparent_pairs
    return day["apparent_pairs"]


def day_stats(day):
    return day.stats if hasattr(day, "stats") else day["stats"]
