#!/usr/bin/env python3
"""Run a deterministic, network-free smoke path across all M1 provider fakes."""

from __future__ import annotations

import hashlib
import json

from adapters.github import FakeGitHubProvider
from adapters.llm import FakeLLMProvider
from adapters.object_storage import FakeObjectStorage
from packages.ai_core import ContentClass, EvidenceContext, LLMBudget, build_analysis_request
from packages.github_contracts import ChangedFile, PullRequestSnapshot


def run_smoke() -> dict[str, object]:
    snapshot = PullRequestSnapshot(
        repository="releaseproof/fixture",
        number=1,
        title="Exercise deterministic provider boundaries",
        base_sha="a" * 40,
        head_sha="b" * 40,
        changed_files=(ChangedFile("src/fixture_app/pricing.py", 4, 1),),
    )
    github = FakeGitHubProvider([snapshot])
    resolved_snapshot = github.get_pull_request("releaseproof/fixture", 1)

    llm = FakeLLMProvider()
    response = llm.analyze_change(
        build_analysis_request(
            change_id="change:m1:fixture",
            evidence=(
                EvidenceContext(
                    evidence_id="evidence:m1:fixture",
                    content_class=ContentClass.DETERMINISTIC_EVIDENCE,
                    content="The fixture pricing boundary changed.",
                    source_reference="fixture:evidence:m1",
                ),
            ),
            budget=LLMBudget(
                max_input_bytes=16_384,
                max_input_tokens=16_384,
                max_output_tokens=1_024,
                max_cost_microusd=100_000,
                connect_timeout_seconds=5.0,
                read_timeout_seconds=30.0,
                max_attempts=2,
                retry_backoff_seconds=0.5,
            ),
        )
    )

    payload = b"releaseproof-m1-fixture"
    checksum = hashlib.sha256(payload).hexdigest()
    storage = FakeObjectStorage()
    storage.ensure_bucket()
    metadata = storage.put("m1/smoke.txt", payload, content_type="text/plain", sha256=checksum)

    return {
        "github": {
            "changed_files": len(resolved_snapshot.changed_files),
            "head_sha": resolved_snapshot.head_sha,
            "repository": resolved_snapshot.repository,
        },
        "llm": {
            "cited_evidence_ids": response.suggestion.cited_evidence_ids,
            "summary": response.suggestion.summary,
        },
        "object_storage": {
            "bytes": len(storage.get(metadata.key)),
            "sha256": metadata.sha256,
        },
    }


def main() -> int:
    print(json.dumps(run_smoke(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
