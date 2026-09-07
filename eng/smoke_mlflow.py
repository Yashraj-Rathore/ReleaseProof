#!/usr/bin/env python3
"""Register and verify the safe M13 fixture registry against live MLflow."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import cast

from adapters.mlflow import (
    MLFLOW_PINNED_VERSION,
    MLflowTracker,
    MLflowTrackingSettings,
    safe_tracking_summary,
)
from eng.evaluate_m13_governance import evaluation_registry, formal_experiments


def _read(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - bounded local URL
        if response.status != 200:
            raise RuntimeError("MLflow health endpoint was not ready")
        return cast(str, response.read(128).decode("utf-8").strip())


def main() -> int:
    settings = MLflowTrackingSettings.from_environment()
    base_url = settings.tracking_uri.rstrip("/")
    try:
        _read(f"{base_url}/health")
        version = _read(f"{base_url}/version")
        if version != MLFLOW_PINNED_VERSION:
            raise RuntimeError("MLflow service version does not match the pinned adapter")
        tracker = MLflowTracker(settings)
        formal = [tracker.log_formal_experiment(item) for item in formal_experiments()]
        evaluations = [tracker.log_evaluation(item) for item in evaluation_registry()]
    except (RuntimeError, ValueError, urllib.error.URLError) as error:
        print(f"MLflow governance smoke failed: {error}", file=sys.stderr)
        return 1
    result = {
        "evaluations": [json.loads(safe_tracking_summary(item)) for item in evaluations],
        "formal_experiments": [json.loads(safe_tracking_summary(item)) for item in formal],
        "mlflow_version": version,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
