from __future__ import annotations

import hashlib
from pathlib import Path


def test_htmx_2_0_10_asset_checksum_is_exact() -> None:
    asset = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "web"
        / "static"
        / "vendor"
        / "htmx"
        / "htmx.min.js"
    )

    assert asset.is_file()
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == (
        "71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de"
    )
