"""Helpers for enforcing one absolute in-process request deadline."""

from __future__ import annotations

import time


class DeadlineExceeded(TimeoutError):
    """Raised when no request budget remains."""

    code = "deadline_exceeded"


def create_deadline(timeout_seconds: float) -> float:
    """Return an absolute deadline based on the monotonic process clock."""
    return time.monotonic() + max(0.0, timeout_seconds)


def child_deadline(
    parent_deadline: float | None,
    timeout_seconds: float,
) -> float:
    """Create a stage deadline that can never outlive its parent."""
    local_deadline = create_deadline(timeout_seconds)
    if parent_deadline is None:
        return local_deadline
    return min(parent_deadline, local_deadline)


def deadline_before_reserve(
    parent_deadline: float | None,
    reserve_seconds: float,
) -> float | None:
    """Return a deadline that preserves time for a required later stage."""
    if parent_deadline is None:
        return None
    return max(time.monotonic(), parent_deadline - max(0.0, reserve_seconds))


def remaining_seconds(deadline: float | None) -> float | None:
    """Return remaining request time, clamped at zero."""
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def stage_timeout(
    deadline: float | None,
    stage_budget_seconds: float,
) -> float:
    """Limit a stage by both its own budget and the request remainder."""
    stage_budget = max(0.0, stage_budget_seconds)
    remaining = remaining_seconds(deadline)
    if remaining is None:
        return stage_budget
    return min(stage_budget, remaining)


def require_remaining(
    deadline: float | None,
    stage_budget_seconds: float,
) -> float:
    """Return a usable stage timeout or fail before starting work."""
    timeout = stage_timeout(deadline, stage_budget_seconds)
    if timeout <= 0:
        raise DeadlineExceeded("Request deadline has been exhausted")
    return timeout
