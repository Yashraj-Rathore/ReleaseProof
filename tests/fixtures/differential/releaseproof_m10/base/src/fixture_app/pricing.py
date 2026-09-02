"""Deterministic pricing behavior used by the M10 sandbox fixture."""

from decimal import Decimal


def total_with_tax(subtotal: Decimal, tax_rate: Decimal) -> Decimal:
    if subtotal < 0 or tax_rate < 0:
        raise ValueError("subtotal and tax rate must be non-negative")
    return (subtotal * (Decimal("1") + tax_rate)).quantize(Decimal("0.01"))
