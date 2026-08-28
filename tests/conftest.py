"""Shared pytest fixtures and factory helpers for ReconEngine tests."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from recon_engine import (
    NormalizedBankTransaction,
    NormalizedOrder,
    NormalizedRefund,
    NormalizedSettlement,
    build_bank_index,
    build_duplicate_bank_index,
    build_report,
    load_data,
    normalize_bank_transactions,
    normalize_orders,
    normalize_refunds,
    normalize_settlements,
    reconcile_all,
    validate_inputs,
    _deterministic_report_timestamp,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DATA_DIR = PROJECT_ROOT / "data"

FEE_RATE_BPS = 200
TAX_RATE_BPS = 180

DT_BASE = datetime(2026, 1, 1, 0, 0, 0)


def compute_settlement_amounts(gross_amount: int) -> tuple[int, int, int]:
    """Mirror data_gen fee/tax/net arithmetic for test fixtures."""
    fee = gross_amount * FEE_RATE_BPS // 10000
    tax = gross_amount * TAX_RATE_BPS // 10000
    net_amount = gross_amount - fee - tax
    return fee, tax, net_amount


def make_order(
    order_id: str = "ORD_0001",
    amount_paise: int = 100_000,
    created_at: datetime | None = None,
) -> NormalizedOrder:
    return NormalizedOrder(
        order_id=order_id,
        amount_paise=amount_paise,
        created_at=created_at or DT_BASE,
    )


def make_settlement(
    settlement_id: str = "SET_0001",
    order_id: str = "ORD_0001",
    gross_amount_paise: int = 100_000,
    *,
    settled_at: datetime | None = None,
    fee_paise: int | None = None,
    tax_paise: int | None = None,
    net_amount_paise: int | None = None,
) -> NormalizedSettlement:
    fee, tax, net = compute_settlement_amounts(gross_amount_paise)
    return NormalizedSettlement(
        settlement_id=settlement_id,
        order_id=order_id,
        gross_amount_paise=gross_amount_paise,
        fee_paise=fee_paise if fee_paise is not None else fee,
        tax_paise=tax_paise if tax_paise is not None else tax,
        net_amount_paise=net_amount_paise if net_amount_paise is not None else net,
        settled_at=settled_at or DT_BASE + timedelta(hours=1),
    )


def make_refund(
    refund_id: str = "REF_0001",
    order_id: str = "ORD_0001",
    refund_amount_paise: int = 10_000,
    created_at: datetime | None = None,
) -> NormalizedRefund:
    return NormalizedRefund(
        refund_id=refund_id,
        order_id=order_id,
        refund_amount_paise=refund_amount_paise,
        created_at=created_at or DT_BASE + timedelta(hours=2),
    )


def make_bank_tx(
    bank_transaction_id: str = "BNK_0001",
    settlement_ref: str = "SET_0001",
    amount_paise: int | None = None,
    *,
    transaction_date: datetime | None = None,
    description: str = "Payout ORD_0001",
    ref_category: str | None = None,
    resolved_settlement_id: str | None = None,
) -> NormalizedBankTransaction:
    if ref_category is None:
        if settlement_ref.startswith("ORPHAN-"):
            ref_category = "orphan"
        elif settlement_ref.startswith("DUP-"):
            ref_category = "duplicate"
        elif settlement_ref.startswith("STL-"):
            ref_category = "reference_variation"
        elif settlement_ref.startswith("SET_"):
            ref_category = "canonical"
        else:
            ref_category = "unknown"
    if resolved_settlement_id is None and ref_category in ("canonical", "reference_variation"):
        if settlement_ref.startswith("STL-"):
            resolved_settlement_id = settlement_ref.replace("STL-", "SET_", 1)
        elif settlement_ref.startswith("SET_"):
            resolved_settlement_id = settlement_ref
    return NormalizedBankTransaction(
        bank_transaction_id=bank_transaction_id,
        settlement_ref=settlement_ref,
        amount_paise=amount_paise if amount_paise is not None else 96_200,
        transaction_date=transaction_date or DT_BASE + timedelta(hours=2),
        description=description,
        ref_category=ref_category,
        resolved_settlement_id=resolved_settlement_id,
    )


def make_bank_indexes(
    bank_transactions: list[NormalizedBankTransaction],
) -> tuple[dict[str, list[NormalizedBankTransaction]], dict[str, list[NormalizedBankTransaction]]]:
    return build_bank_index(bank_transactions), build_duplicate_bank_index(bank_transactions)


def reconcile_single(
    order: NormalizedOrder,
    settlements: list[NormalizedSettlement],
    refunds: list[NormalizedRefund] | None = None,
    bank_transactions: list[NormalizedBankTransaction] | None = None,
    tolerance_hours: int = 24,
):
    """Run reconcile_order with indexes built from bank transactions."""
    from recon_engine import reconcile_order

    refunds = refunds or []
    bank_transactions = bank_transactions or []
    bank_index, dup_index = make_bank_indexes(bank_transactions)
    return reconcile_order(
        order,
        settlements,
        refunds,
        bank_index,
        dup_index,
        tolerance_hours=tolerance_hours,
    )


def minimal_valid_csv_dict() -> dict[str, pd.DataFrame]:
    """Minimal valid four-file dataset as DataFrames."""
    gross = 100_000
    fee, tax, net = compute_settlement_amounts(gross)
    orders = pd.DataFrame(
        [{"order_id": "ORD_0001", "amount": gross, "created_at": DT_BASE.isoformat()}]
    )
    settlements = pd.DataFrame(
        [
            {
                "settlement_id": "SET_0001",
                "order_id": "ORD_0001",
                "gross_amount": gross,
                "fee": fee,
                "tax": tax,
                "net_amount": net,
                "settled_at": (DT_BASE + timedelta(hours=1)).isoformat(),
            }
        ]
    )
    refunds = pd.DataFrame(
        columns=["refund_id", "order_id", "refund_amount", "created_at"]
    )
    bank = pd.DataFrame(
        [
            {
                "bank_transaction_id": "BNK_0001",
                "settlement_ref": "SET_0001",
                "amount": net,
                "transaction_date": (DT_BASE + timedelta(hours=1)).isoformat(),
                "description": "Payout ORD_0001",
            }
        ]
    )
    return {"orders": orders, "settlements": settlements, "refunds": refunds, "bank": bank}


def write_csv_dataset(data_dir: Path, frames: dict[str, pd.DataFrame]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    frames["orders"].to_csv(data_dir / "orders.csv", index=False)
    frames["settlements"].to_csv(data_dir / "settlements.csv", index=False)
    frames["refunds"].to_csv(data_dir / "refunds.csv", index=False)
    frames["bank"].to_csv(data_dir / "bank.csv", index=False)


def run_engine_pipeline(data_dir: Path) -> dict[str, Any]:
    """Execute reconciliation pipeline without writing to production paths."""
    raw_data = load_data(data_dir)
    validate_inputs(raw_data)
    settlements = normalize_settlements(raw_data["settlements"])
    valid_settlement_ids = {s.settlement_id for s in settlements}
    orders = normalize_orders(raw_data["orders"])
    refunds = normalize_refunds(raw_data["refunds"])
    bank_transactions = normalize_bank_transactions(raw_data["bank"], valid_settlement_ids)
    order_results, global_exceptions = reconcile_all(
        orders, settlements, refunds, bank_transactions
    )
    report_timestamp = _deterministic_report_timestamp(
        orders, settlements, bank_transactions
    )
    return build_report(
        order_results,
        global_exceptions,
        report_timestamp=report_timestamp,
    )


@pytest.fixture
def fixture_data_copy(tmp_path: Path) -> Path:
    """Copy committed CSV fixtures into an isolated temp directory."""
    dest = tmp_path / "data"
    dest.mkdir()
    for name in ("orders.csv", "settlements.csv", "refunds.csv", "bank.csv"):
        shutil.copy2(FIXTURE_DATA_DIR / name, dest / name)
    return dest


@pytest.fixture
def golden_ground_truth() -> dict[str, Any]:
    with (FIXTURE_DATA_DIR / "ground_truth.json").open(encoding="utf-8") as handle:
        return json.load(handle)
