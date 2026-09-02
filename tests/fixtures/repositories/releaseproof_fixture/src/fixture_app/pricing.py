"""Inert source fixture used by later change-intelligence tests."""

from decimal import Decimal


def total_with_tax(subtotal: Decimal, tax_rate: Decimal) -> Decimal:
    """Return a currency-quantized total for a non-negative subtotal."""
    if subtotal < 0 or tax_rate < 0:
        raise ValueError("subtotal and tax rate must be non-negative")
    return (subtotal * (Decimal("1") + tax_rate)).quantize(Decimal("0.01"))


def calculate_total(subtotal: int, tax_percent: int) -> int:
    """Return a deterministic integer total for the fictional fixture."""

    return subtotal + (subtotal * tax_percent // 100)
