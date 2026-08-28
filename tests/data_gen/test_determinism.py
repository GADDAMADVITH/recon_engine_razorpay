"""Data generator determinism tests."""

from __future__ import annotations

from data_gen import generate_orders, reset_random_state


def test_generate_orders_is_deterministic():
    reset_random_state()
    first = generate_orders()
    reset_random_state()
    second = generate_orders()
    assert first.equals(second)
