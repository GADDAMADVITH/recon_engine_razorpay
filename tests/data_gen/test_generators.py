"""Data generator output structure tests."""

from __future__ import annotations

from data_gen import (
    NUM_BANK_TRANSACTIONS,
    NUM_ORDERS,
    NUM_REFUNDS,
    NUM_SETTLEMENTS,
    SCENARIO_TO_EXPECTED_STATUS,
    compute_settlement_amounts,
    generate_bank_transactions,
    generate_orders,
    generate_refunds,
    generate_settlements,
    reset_random_state,
)


def test_record_counts():
    reset_random_state()
    orders = generate_orders()
    settlements = generate_settlements(orders)
    refunds = generate_refunds(orders)
    bank = generate_bank_transactions(settlements, orders)
    assert len(orders) == NUM_ORDERS
    assert len(settlements) == NUM_SETTLEMENTS
    assert len(refunds) == NUM_REFUNDS
    assert len(bank) == NUM_BANK_TRANSACTIONS


def test_unique_order_ids():
    reset_random_state()
    orders = generate_orders()
    assert orders["order_id"].is_unique


def test_foreign_keys_valid():
    reset_random_state()
    orders = generate_orders()
    settlements = generate_settlements(orders)
    refunds = generate_refunds(orders)
    order_ids = set(orders["order_id"])
    assert set(settlements["order_id"]).issubset(order_ids)
    assert set(refunds["order_id"]).issubset(order_ids)


def test_compute_settlement_amounts_arithmetic():
    fee, tax, net = compute_settlement_amounts(100_000)
    assert fee + tax + net == 100_000


def test_all_scenario_types_present_in_mapping():
    assert len(SCENARIO_TO_EXPECTED_STATUS) == 10
