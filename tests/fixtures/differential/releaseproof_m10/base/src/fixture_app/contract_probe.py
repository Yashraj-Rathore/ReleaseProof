"""Emit one bounded HTTP/state observation without opening a network socket."""

from __future__ import annotations

import json
import sys
from decimal import Decimal

from fixture_app.pricing import total_with_tax


def main() -> None:
    subtotal = Decimal("100.00")
    total = total_with_tax(subtotal, Decimal("0.13"))
    observation = {
        "events": [{"name": "quote.calculated", "sequence": 1}],
        "http": {
            "body": {"currency": "CAD", "total": str(total)},
            "headers": {"content-type": "application/json", "x-request-id": "masked"},
            "schema": {"currency": "string", "total": "string"},
            "status": 200,
        },
        "request": {"method": "GET", "path": "/quote", "subtotal": "100.00"},
        "state": {"quote_count": 1, "updated_at": "masked"},
    }
    sys.stdout.write(json.dumps(observation, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
