"""Inert service layer for static graph fixtures."""

from decimal import Decimal

from fixture_app.pricing import total_with_tax


def quoted_total(subtotal: Decimal) -> Decimal:
    return total_with_tax(subtotal, Decimal("0.13"))
