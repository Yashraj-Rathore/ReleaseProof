"""Privacy-bounded MLflow adapter for public/synthetic governance metadata."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from packages.ml_core import (
    DataScope,
    EvaluationRegistryEntry,
    FormalExperimentRecord,
    GovernanceError,
)

MLFLOW_PINNED_VERSION = "3.15.2"


class _RunInfo(Protocol):
    run_id: str


class _Run(Protocol):
    info: _RunInfo


class _Experiment(Protocol):
    experiment_id: str


class _MlflowClient(Protocol):
    def get_experiment_by_name(self, name: str) -> _Experiment | None: ...

    def create_experiment(self, name: str) -> str: ...

    def search_runs(
        self, experiment_ids: list[str], *, filter_string: str, max_results: int
    ) -> list[_Run]: ...

    def create_run(self, experiment_id: str, *, tags: dict[str, str]) -> _Run: ...

    def log_param(self, run_id: str, key: str, value: str) -> None: ...

    def log_metric(self, run_id: str, key: str, value: float) -> None: ...

    def log_dict(self, run_id: str, dictionary: dict[str, object], artifact_file: str) -> None: ...

    def set_terminated(self, run_id: str, *, status: str) -> None: ...


@dataclass(frozen=True, slots=True)
class MLflowTrackingSettings:
    tracking_uri: str
    formal_experiment_name: str = "releaseproof-formal-experiments"
    evaluation_experiment_name: str = "releaseproof-evaluation-registry"

    def __post_init__(self) -> None:
        parsed = urlparse(self.tracking_uri)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MLflow tracking URI must name an HTTP(S) server")
        if parsed.username or parsed.password:
            raise ValueError("MLflow tracking credentials must not be embedded in the URI")
        for name in (self.formal_experiment_name, self.evaluation_experiment_name):
            if not 1 <= len(name) <= 128 or not name.isascii():
                raise ValueError("MLflow experiment names must be bounded ASCII")

    @classmethod
    def from_environment(cls) -> MLflowTrackingSettings:
        return cls(
            tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
            formal_experiment_name=os.getenv(
                "MLFLOW_FORMAL_EXPERIMENT_NAME", "releaseproof-formal-experiments"
            ),
            evaluation_experiment_name=os.getenv(
                "MLFLOW_EVALUATION_EXPERIMENT_NAME", "releaseproof-evaluation-registry"
            ),
        )


@dataclass(frozen=True, slots=True)
class TrackedRun:
    run_id: str
    record_sha256: str
    created: bool


def _parameter_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


class MLflowTracker:
    """Log only validated metadata to an exact-version MLflow client."""

    def __init__(
        self,
        settings: MLflowTrackingSettings,
        *,
        client: _MlflowClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or self._load_client(settings.tracking_uri)

    @staticmethod
    def _load_client(tracking_uri: str) -> _MlflowClient:
        try:
            mlflow = importlib.import_module("mlflow")
            client_module = importlib.import_module("mlflow.tracking")
        except ImportError as error:
            raise RuntimeError("the pinned governance dependency group is not installed") from error
        version = getattr(mlflow, "__version__", None)
        if version != MLFLOW_PINNED_VERSION:
            raise RuntimeError("MLflow runtime does not match the pinned adapter version")
        client_type: Any = client_module.MlflowClient
        return cast(_MlflowClient, client_type(tracking_uri=tracking_uri))

    def _experiment_id(self, name: str) -> str:
        experiment = self._client.get_experiment_by_name(name)
        return (
            self._client.create_experiment(name) if experiment is None else experiment.experiment_id
        )

    def _existing_run(self, experiment_id: str, record_sha256: str) -> TrackedRun | None:
        runs = self._client.search_runs(
            [experiment_id],
            filter_string=f"tags.releaseproof_record_sha256 = '{record_sha256}'",
            max_results=1,
        )
        if not runs:
            return None
        return TrackedRun(
            run_id=runs[0].info.run_id,
            record_sha256=record_sha256,
            created=False,
        )

    def _log(
        self,
        *,
        experiment_name: str,
        run_name: str,
        record_sha256: str,
        payload: dict[str, object],
        params: dict[str, object],
        metrics: dict[str, float],
        tags: dict[str, str],
        artifact_file: str,
    ) -> TrackedRun:
        experiment_id = self._experiment_id(experiment_name)
        existing = self._existing_run(experiment_id, record_sha256)
        if existing is not None:
            return existing
        run = self._client.create_run(
            experiment_id,
            tags={
                **tags,
                "mlflow.runName": run_name,
                "releaseproof_record_sha256": record_sha256,
            },
        )
        run_id = run.info.run_id
        try:
            for key, value in sorted(params.items()):
                self._client.log_param(run_id, key, _parameter_value(value))
            for key, value in sorted(metrics.items()):
                self._client.log_metric(run_id, key, value)
            self._client.log_dict(run_id, payload, artifact_file)
            self._client.set_terminated(run_id, status="FINISHED")
        except Exception:
            self._client.set_terminated(run_id, status="FAILED")
            raise
        return TrackedRun(run_id=run_id, record_sha256=record_sha256, created=True)

    def log_formal_experiment(self, record: FormalExperimentRecord) -> TrackedRun:
        if record.data_scope is DataScope.ORGANIZATION_LOCAL or record.contains_customer_code:
            raise GovernanceError(
                "the unauthenticated local MLflow profile accepts only approved "
                "public/synthetic metadata"
            )
        params: dict[str, object] = {
            "code_sha": record.code_sha,
            "data_scope": record.data_scope.value,
            "dataset_manifest_sha256": record.dataset_manifest_sha256,
            "dataset_version": record.dataset_version,
            "feature_schema_version": record.feature_schema_version,
            "kind": record.kind.value,
            "schema_version": record.schema_version,
            "synthetic": record.synthetic,
        }
        params.update({f"config.{key}": value for key, value in record.parameters.items()})
        params.update({f"environment.{key}": value for key, value in record.environment.items()})
        return self._log(
            experiment_name=self._settings.formal_experiment_name,
            run_name=record.run_name,
            record_sha256=record.record_sha256,
            payload=record.as_dict(),
            params=params,
            metrics=dict(record.metrics),
            tags={
                "releaseproof_contract": record.schema_version,
                "releaseproof_data_scope": record.data_scope.value,
            },
            artifact_file="governance/formal-experiment.json",
        )

    def log_evaluation(self, entry: EvaluationRegistryEntry) -> TrackedRun:
        params: dict[str, object] = {
            "component": entry.component.value,
            "contains_customer_code": entry.contains_customer_code,
            "dataset_sha256": entry.evaluation_dataset_sha256,
            "dataset_version": entry.evaluation_dataset_version,
            "license_spdx": entry.license_spdx,
            "schema_version": entry.schema_version,
            "synthetic": entry.synthetic,
        }
        params.update(
            {f"version.{key}": value for key, value in entry.configuration_versions.items()}
        )
        return self._log(
            experiment_name=self._settings.evaluation_experiment_name,
            run_name=f"{entry.component.value}-{entry.evaluation_dataset_version}",
            record_sha256=entry.record_sha256,
            payload=entry.as_dict(),
            params=params,
            metrics=dict(entry.aggregate_metrics),
            tags={"releaseproof_contract": entry.schema_version},
            artifact_file="governance/evaluation-registry-entry.json",
        )


def safe_tracking_summary(run: TrackedRun) -> str:
    return json.dumps(
        {
            "created": run.created,
            "record_sha256": run.record_sha256,
            "run_id": run.run_id,
        },
        sort_keys=True,
    )
