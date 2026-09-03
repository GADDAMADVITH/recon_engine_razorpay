"""Tests for normalization and reference resolution."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from recon_engine import (
    classify_settlement_ref,
    normalize_amount,
    normalize_bank_transactions,
    normalize_id,
    normalize_settlement_ref,
    normalize_timestamp,
)


def test_normalize_id_strips_whitespace():
    assert normalize_id("  ORD_0001  ") == "ORD_0001"


def test_normalize_amount_accepts_positive_integer():
    assert normalize_amount(100_000, "order.amount") == 100_000


def test_normalize_amount_rejects_zero():
    with pytest.raises(ValueError, match="must be positive"):
        normalize_amount(0, "order.amount")


def test_normalize_amount_rejects_negative():
    with pytest.raises(ValueError, match="must be positive"):
        normalize_amount(-1, "order.amount")


def test_normalize_amount_rejects_non_numeric():
    with pytest.raises(ValueError, match="Invalid monetary value"):
        normalize_amount("abc", "order.amount")


def test_normalize_amount_accepts_large_integer():
    assert normalize_amount(2_000_000_000, "order.amount") == 2_000_000_000


def test_normalize_timestamp_parses_iso():
    result = normalize_timestamp("2026-01-01T00:00:00", "order.created_at")
    assert result == datetime(2026, 1, 1, 0, 0, 0)


def test_normalize_timestamp_rejects_malformed():
    with pytest.raises(ValueError, match="Malformed timestamp"):
        normalize_timestamp("not-a-date", "order.created_at")


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("SET_0001", "canonical"),
        ("STL-0001", "reference_variation"),
        ("ORPHAN-ORD_0001", "orphan"),
        ("DUP-SET_0001", "duplicate"),
        ("FOO-BAR", "unknown"),
    ],
)
def test_classify_settlement_ref(ref: str, expected: str):
    assert classify_settlement_ref(ref) == expected


@pytest.mark.parametrize(
    ("ref", "valid_ids", "expected"),
    [
        ("SET_0001", {"SET_0001"}, "SET_0001"),
        ("STL-0001", {"SET_0001"}, "SET_0001"),
        ("ORPHAN-ORD_0001", {"SET_0001"}, None),
        ("DUP-SET_0001", {"SET_0001"}, None),
        ("SET_9999", {"SET_0001"}, None),
        ("FOO-BAR", {"SET_0001"}, None),
        # Razorpay-style IDs: exact match only when present in valid set
        ("setl_DemoExact001", {"setl_DemoExact001"}, "setl_DemoExact001"),
        ("setl_DemoExact001", {"SET_0001"}, None),
        ("setl_Other", {"setl_DemoExact001"}, None),
        # Orphan/duplicate prefixes must never exact-match even if listed
        ("ORPHAN-setl_x", {"ORPHAN-setl_x"}, None),
        ("DUP-setl_x", {"DUP-setl_x"}, None),
    ],
)
def test_normalize_settlement_ref(ref: str, valid_ids: set[str], expected: str | None):
    assert normalize_settlement_ref(ref, valid_ids) == expected


def test_classify_razorpay_settlement_id_is_unknown():
    """Prove setl_* is not SET_/STL-; resolution relies on exact-match fallback."""
    assert classify_settlement_ref("setl_DemoExact001") == "unknown"


def test_normalize_bank_resolves_exact_razorpay_settlement_id():
    df = pd.DataFrame(
        [
            {
                "bank_transaction_id": "BNK_RZ_001",
                "settlement_ref": "setl_DemoExact001",
                "amount": 370605,
                "transaction_date": "2026-01-02T02:00:00",
                "description": "Synthetic bank fixture (not from Razorpay)",
            }
        ]
    )
    records = normalize_bank_transactions(df, {"setl_DemoExact001"})
    assert records[0].ref_category == "unknown"
    assert records[0].resolved_settlement_id == "setl_DemoExact001"


def test_normalize_bank_transactions_does_not_use_description_for_resolution():
    df = pd.DataFrame(
        [
            {
                "bank_transaction_id": "BNK_0001",
                "settlement_ref": "ORPHAN-ORD_0001",
                "amount": 1000,
                "transaction_date": "2026-01-01T02:00:00",
                "description": "SET_0001 misleading description",
            }
        ]
    )
    records = normalize_bank_transactions(df, {"SET_0001"})
    assert records[0].resolved_settlement_id is None
    assert records[0].ref_category == "orphan"
