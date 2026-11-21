"""Triage Inversion Cause Attribution.

Detects priority inversions in a synthetic emergency-department
queue and attributes each inversion to the operational mechanism
that produced it -- re-triage lag, resource-fit preemption, or batch
reassessment timing -- instead of scoring triage accuracy in
aggregate.

Author: Amna Raheeba
"""

__version__ = "0.1.0"
