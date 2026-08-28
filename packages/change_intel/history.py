"""Strictly pre-change, bounded repository history statistics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from packages.change_intel.contracts import (
    HISTORY_SCHEMA_VERSION,
    HistoricalChange,
    HistoricalStatistics,
    NormalizedDiff,
)

MAX_HISTORY_CHANGES = 10_000
DEFAULT_HISTORY_WINDOW_DAYS = 90


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("history timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _module_area(path: str) -> str:
    pure = PurePosixPath(path)
    parts = list(pure.parts)
    if parts and parts[0] in {"src", "lib"}:
        parts = parts[1:]
    if len(parts) <= 1:
        return parts[0] if parts else path
    return "/".join(parts[:-1])


def compute_historical_statistics(
    normalized_diff: NormalizedDiff,
    history: tuple[HistoricalChange, ...],
    *,
    prediction_time: datetime,
    current_author_key: str | None,
    window_days: int = DEFAULT_HISTORY_WINDOW_DAYS,
    history_truncated: bool = False,
) -> HistoricalStatistics:
    prediction = _aware(prediction_time)
    if window_days < 1 or window_days > 3_650:
        raise ValueError("history window must be between 1 and 3650 days")
    if len(history) > MAX_HISTORY_CHANGES:
        raise ValueError("history exceeds the deterministic record limit")
    start = prediction - timedelta(days=window_days)
    included: list[HistoricalChange] = []
    excluded_future = 0
    for change in history:
        observed = _aware(change.observed_at)
        if observed >= prediction:
            excluded_future += 1
        elif observed >= start:
            included.append(change)
    included.sort(key=lambda change: change.observed_at)

    target_paths = {file.path for file in normalized_diff.files}
    target_areas = {_module_area(path) for path in target_paths}
    file_touches = 0
    module_touches = 0
    churn = 0
    failure_count = 0
    failure_observations = 0
    familiar_touches = 0
    ownership_observations = 0
    for change in included:
        touched_paths = {file.path.replace("\\", "/") for file in change.files}
        touched_areas = {_module_area(path) for path in touched_paths}
        overlaps_files = bool(touched_paths & target_paths)
        overlaps_modules = bool(touched_areas & target_areas)
        if overlaps_files:
            file_touches += 1
            churn += sum(
                file.additions + file.deletions
                for file in change.files
                if file.path.replace("\\", "/") in target_paths
            )
        if overlaps_modules:
            module_touches += 1
            if change.failed_check_proxy is not None:
                failure_observations += 1
                failure_count += int(change.failed_check_proxy)
            if current_author_key is not None and change.author_key is not None:
                ownership_observations += 1
                familiar_touches += int(change.author_key == current_author_key)

    missing: list[str] = []
    if not included:
        missing.append("repository_history")
    if failure_observations == 0:
        missing.append("prior_failure_proxy")
    if current_author_key is None:
        missing.append("current_author_key")
    elif ownership_observations == 0:
        missing.append("ownership_history")
    if history_truncated:
        missing.append("history_truncated")
    return HistoricalStatistics(
        schema_version=HISTORY_SCHEMA_VERSION,
        prediction_time=prediction,
        window_days=window_days,
        included_changes=len(included),
        excluded_future_changes=excluded_future,
        target_file_touches=file_touches,
        target_module_touches=module_touches,
        line_churn=churn,
        prior_failure_proxy_count=failure_count if failure_observations else None,
        failure_proxy_observations=failure_observations,
        ownership_familiarity=(
            familiar_touches / ownership_observations if ownership_observations else None
        ),
        missing=tuple(missing),
        truncated=history_truncated,
    )
