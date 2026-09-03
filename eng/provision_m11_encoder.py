"""Explicitly provision the exact public M11 encoder into an ignored local directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

from packages.retrieval_core import EMBEDDING_ARTIFACT

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = ROOT / "models" / "private" / "all-MiniLM-L6-v2-1110a243"
ALLOWED_FILES = (
    "1_Pooling/config.json",
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "model.safetensors",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_directory(destination: Path) -> dict[str, object]:
    resolved = destination.resolve()
    hashes: dict[str, str] = {}
    for name in ALLOWED_FILES:
        path = resolved / name
        if not path.is_file():
            raise ValueError(f"provisioned model is missing required file: {name}")
        hashes[name] = _sha256(path)
    if hashes["model.safetensors"] != EMBEDDING_ARTIFACT.safetensors_sha256:
        raise ValueError("provisioned model weights do not match the approved checksum")
    return {
        "files_sha256": hashes,
        "license": EMBEDDING_ARTIFACT.license,
        "model_id": EMBEDDING_ARTIFACT.model_id,
        "revision": EMBEDDING_ARTIFACT.revision,
        "safetensors_sha256": EMBEDDING_ARTIFACT.safetensors_sha256,
        "schema_version": "m11-local-model-manifest-v1",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    destination = args.destination.resolve()
    if not args.verify_only:
        destination.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=EMBEDDING_ARTIFACT.model_id,
            revision=EMBEDDING_ARTIFACT.revision,
            local_dir=destination,
            allow_patterns=list(ALLOWED_FILES),
            max_workers=4,
            etag_timeout=30,
        )
    manifest = verify_model_directory(destination)
    manifest_path = destination / "releaseproof-model-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "destination": str(destination),
                "model_id": EMBEDDING_ARTIFACT.model_id,
                "revision": EMBEDDING_ARTIFACT.revision,
                "status": "verified",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
