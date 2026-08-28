"""Inert test module used only as static source data during M3."""

from decimal import Decimal

from fixture_app.pricing import total_with_tax


def check_total_with_tax() -> None:
    assert total_with_tax(Decimal("10"), Decimal("0.10")) == Decimal("11.00")
