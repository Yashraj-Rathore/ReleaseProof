"""Controlled mutant: removes the negative-value validation branch."""

from decimal import Decimal


def total_with_tax(subtotal: Decimal, tax_rate: Decimal) -> Decimal:
    return (subtotal * (Decimal("1") + tax_rate)).quantize(Decimal("0.01"))
