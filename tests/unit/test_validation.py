"""Tests for input validation and data loading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from recon_engine import load_data, validate_inputs
from tests.conftest import DT_BASE, minimal_valid_csv_dict, write_csv_dataset


def test_validate_inputs_accepts_minimal_valid_dataset():
    validate_inputs(minimal_valid_csv_dict())


def test_validate_inputs_rejects_missing_column():
    frames = minimal_valid_csv_dict()
    frames["orders"] = frames["orders"].drop(columns=["amount"])
    with pytest.raises(ValueError, match="orders column mismatch"):
        validate_inputs(frames)


def test_validate_inputs_rejects_extra_column():
    frames = minimal_valid_csv_dict()
    frames["orders"]["extra"] = 1
    with pytest.raises(ValueError, match="orders column mismatch"):
        validate_inputs(frames)


def test_validate_inputs_rejects_duplicate_order_ids():
    frames = minimal_valid_csv_dict()
    frames["orders"] = pd.concat([frames["orders"], frames["orders"]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate order IDs"):
        validate_inputs(frames)


def test_validate_inputs_rejects_unknown_settlement_order():
    frames = minimal_valid_csv_dict()
    frames["settlements"].loc[0, "order_id"] = "ORD_9999"
    with pytest.raises(ValueError, match="Settlement references unknown order_id"):
        validate_inputs(frames)


def test_validate_inputs_rejects_unknown_refund_order():
    frames = minimal_valid_csv_dict()
    frames["refunds"] = pd.DataFrame(
        [
            {
                "refund_id": "REF_0001",
                "order_id": "ORD_9999",
                "refund_amount": 1000,
                "created_at": DT_BASE.isoformat(),
            }
        ]
    )
    with pytest.raises(ValueError, match="Refund references unknown order_id"):
        validate_inputs(frames)


def test_load_data_raises_when_file_missing(tmp_path: Path):
    write_csv_dataset(tmp_path, minimal_valid_csv_dict())
    (tmp_path / "bank.csv").unlink()
    with pytest.raises(FileNotFoundError, match="Missing required CSV files"):
        load_data(tmp_path)


def test_load_data_loads_all_four_csvs(tmp_path: Path):
    write_csv_dataset(tmp_path, minimal_valid_csv_dict())
    data = load_data(tmp_path)
    assert set(data.keys()) == {"orders", "settlements", "refunds", "bank"}
    assert len(data["orders"]) == 1
