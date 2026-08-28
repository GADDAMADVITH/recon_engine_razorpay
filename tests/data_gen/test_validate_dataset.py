"""validate_dataset tests for data_gen."""

from __future__ import annotations

import json
from pathlib import Path

from data_gen import (
    generate_bank_transactions,
    generate_orders,
    generate_refunds,
    generate_settlements,
    reset_random_state,
    validate_dataset,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data"


def test_validate_dataset_passes_on_committed_data():
    reset_random_state()
    orders = generate_orders()
    settlements = generate_settlements(orders)
    refunds = generate_refunds(orders)
    bank = generate_bank_transactions(settlements, orders)
    with (FIXTURE_DIR / "ground_truth.json").open(encoding="utf-8") as handle:
        ground_truth = json.load(handle)
    messages = validate_dataset(orders, settlements, refunds, bank, ground_truth)
    assert isinstance(messages, list)


def test_validate_dataset_fails_on_tampered_net():
    reset_random_state()
    orders = generate_orders()
    settlements = generate_settlements(orders)
    refunds = generate_refunds(orders)
    bank = generate_bank_transactions(settlements, orders)
    with (FIXTURE_DIR / "ground_truth.json").open(encoding="utf-8") as handle:
        ground_truth = json.load(handle)
    settlements = settlements.copy()
    settlements.loc[0, "net_amount"] = 1
    try:
        validate_dataset(orders, settlements, refunds, bank, ground_truth)
        raised = False
    except ValueError:
        raised = True
    assert raised
