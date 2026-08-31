"""Minimal data-source boundary for ReconEngine inputs.

CSV loading remains the production default via api.run_reconciliation_report.
Razorpay sync produces the same normalized record types through a separate path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from recon_engine import (
    NormalizedBankTransaction,
    NormalizedOrder,
    NormalizedRefund,
    NormalizedSettlement,
    load_data,
    normalize_bank_transactions,
    normalize_orders,
    normalize_refunds,
    normalize_settlements,
    validate_inputs,
)

DataSourceName = Literal["csv", "razorpay"]


@dataclass(frozen=True)
class ReconEngineDataset:
    """Normalized records from a single data source."""

    source: DataSourceName
    orders: tuple[NormalizedOrder, ...]
    settlements: tuple[NormalizedSettlement, ...]
    refunds: tuple[NormalizedRefund, ...]
    bank_transactions: tuple[NormalizedBankTransaction, ...]

    @property
    def has_orders(self) -> bool:
        return len(self.orders) > 0


def load_csv_dataset(data_dir: Path) -> ReconEngineDataset:
    """Load and normalize the CSV dataset (existing production path)."""
    raw_data = load_data(data_dir)
    validate_inputs(raw_data)

    settlements = normalize_settlements(raw_data["settlements"])
    valid_settlement_ids = {s.settlement_id for s in settlements}
    orders = normalize_orders(raw_data["orders"])
    refunds = normalize_refunds(raw_data["refunds"])
    bank_transactions = normalize_bank_transactions(raw_data["bank"], valid_settlement_ids)

    return ReconEngineDataset(
        source="csv",
        orders=tuple(orders),
        settlements=tuple(settlements),
        refunds=tuple(refunds),
        bank_transactions=tuple(bank_transactions),
    )
