from __future__ import annotations

from eng.smoke_fakes import run_smoke


def test_fake_smoke_is_repeatable_and_contains_no_provider_call() -> None:
    first = run_smoke()
    second = run_smoke()

    assert first == second
    assert first["github"] == {
        "changed_files": 1,
        "head_sha": "b" * 40,
        "repository": "releaseproof/fixture",
    }
    assert first["llm"] == {
        "cited_evidence_ids": ("evidence:m1:fixture",),
        "summary": "Deterministic fake suggestion; no model was called.",
    }
