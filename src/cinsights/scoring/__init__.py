"""Interestingness scoring for selective LLM analysis.

Scores sessions relative to per-(user, project) baselines. Only top N%
get LLM-analyzed based on budget mode. Cold start: always analyze first
N sessions per (user, project).
"""

from __future__ import annotations

import logging

from cinsights.db.models import CodingSession, SessionBaseline
from cinsights.scoring.signals import DEFAULT_SIGNALS, Signal

logger = logging.getLogger(__name__)

# Budget mode → fraction of sessions to analyze
BUDGET_THRESHOLDS = {
    "frugal": 0.10,
    "balanced": 0.30,
    "thorough": 0.50,
    "all": 1.00,
}


def score_session(
    session: CodingSession,
    baseline: SessionBaseline,
    signals: list[Signal] | None = None,
) -> tuple[float, dict[str, float]]:
    """Score a session's interestingness relative to its baseline.

    Returns (total_score, breakdown) where breakdown maps signal name to
    its weighted contribution.
    """
    if signals is None:
        signals = DEFAULT_SIGNALS

    breakdown: dict[str, float] = {}
    total = 0.0

    for signal in signals:
        try:
            raw = signal.score(session, baseline)
            weighted = raw * signal.weight
            breakdown[signal.name] = round(weighted, 3)
            total += weighted
        except Exception:
            logger.debug("Signal %s failed for session %s", signal.name, session.id, exc_info=True)
            breakdown[signal.name] = 0.0

    return round(min(total, 1.0), 3), breakdown


def select_for_analysis(
    scored: list[tuple[CodingSession, float, dict[str, float]]],
    min_score: float = 0.4,
    min_per_user_project: int | None = None,
    min_per_project: int | None = None,
    small_project_threshold: int | None = None,
) -> tuple[list[CodingSession], list[CodingSession]]:
    """Split scored sessions into (to_analyze, to_skip).

    Selection logic:
    1. Small projects (≤ small_project_threshold sessions) → analyze all
    2. All sessions scoring >= min_score are selected
    3. Per (user, project) pair: at least min_per_user_project sessions
    4. Per project: at least min_per_project sessions globally
    Coverage picks are chosen by highest score within each group.
    """
    from collections import defaultdict

    from cinsights.settings import get_config

    limits = get_config().limits
    if min_per_user_project is None:
        min_per_user_project = limits.min_coverage_per_user_project
    if min_per_project is None:
        min_per_project = limits.min_coverage_per_project
    if small_project_threshold is None:
        small_project_threshold = limits.small_project_threshold

    selected_ids: set[str] = set()

    # Group by project and by (user, project)
    by_project: dict[str | None, list[tuple[CodingSession, float]]] = defaultdict(list)
    by_user_project: dict[tuple[str, str | None], list[tuple[CodingSession, float]]] = defaultdict(
        list
    )
    for session, score, _ in scored:
        by_project[session.project_name].append((session, score))
        key = (session.user_id or "unknown", session.project_name)
        by_user_project[key].append((session, score))

    # Pass 1: small projects → analyze all (cost is negligible)
    for _proj, group in by_project.items():
        if len(group) <= small_project_threshold:
            for s, _ in group:
                selected_ids.add(s.id)

    # Pass 2: select everything above threshold
    for session, score, _breakdown in scored:
        if score >= min_score:
            selected_ids.add(session.id)

    # Pass 3: ensure minimum coverage per (user, project) — unconditional
    for _key, group in by_user_project.items():
        already = sum(1 for s, _ in group if s.id in selected_ids)
        if already >= min_per_user_project:
            continue
        unselected = [(s, sc) for s, sc in group if s.id not in selected_ids]
        unselected.sort(key=lambda x: x[1], reverse=True)
        need = min_per_user_project - already
        for s, _ in unselected[:need]:
            selected_ids.add(s.id)

    # Pass 4: ensure minimum coverage per project globally
    for _proj, group in by_project.items():
        already = sum(1 for s, _ in group if s.id in selected_ids)
        if already >= min_per_project:
            continue
        unselected = [(s, sc) for s, sc in group if s.id not in selected_ids]
        unselected.sort(key=lambda x: x[1], reverse=True)
        need = min_per_project - already
        for s, _ in unselected[:need]:
            selected_ids.add(s.id)

    to_analyze = [s for s, _, _ in scored if s.id in selected_ids]
    to_skip = [s for s, _, _ in scored if s.id not in selected_ids]

    return to_analyze, to_skip


def format_score_reason(score: float, breakdown: dict[str, float]) -> str:
    """Human-readable explanation of why a session scored the way it did."""
    top = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
    parts = [f"{name}={val:.2f}" for name, val in top if val > 0.01]
    if not parts:
        return f"Score {score:.2f}: routine session"
    return f"Score {score:.2f}: {', '.join(parts[:3])}"
