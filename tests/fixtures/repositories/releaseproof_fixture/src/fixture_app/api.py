"""Inert API layer for static graph fixtures."""

from decimal import Decimal

from fixture_app.service import quoted_total


def quote(subtotal: str) -> str:
    return str(quoted_total(Decimal(subtotal)))
