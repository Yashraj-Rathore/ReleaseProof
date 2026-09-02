"""Planted candidate regression: applies 15 percent instead of the supplied rate."""

from decimal import Decimal


def total_with_tax(subtotal: Decimal, tax_rate: Decimal) -> Decimal:
    if subtotal < 0 or tax_rate < 0:
        raise ValueError("subtotal and tax rate must be non-negative")
    return (subtotal * Decimal("1.15")).quantize(Decimal("0.01"))
