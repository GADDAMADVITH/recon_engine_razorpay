"""Phase 4A synthetic demo fixtures for Razorpay-shaped reconciliation.

Razorpay-side records (orders / settlements / refunds) are synthetic payloads
shaped like mapped Razorpay entities. Bank-side records are an explicitly
separate synthetic fixture source — never derived from settlement_utr or any
Razorpay API field.

Label: bank_source = "synthetic_fixture"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import pandas as pd

from recon_engine import (
    NormalizedBankTransaction,
    NormalizedOrder,
    NormalizedRefund,
    NormalizedSettlement,
    normalize_bank_transactions,
)

DEMO_DATA_SOURCE: Literal["razorpay"] = "razorpay"
DEMO_BANK_SOURCE = "synthetic_fixture"
DEMO_BANK_SOURCE_NOTE = (
    "Bank rows are synthetic fixtures for Phase 4A demonstration. "
    "They are not produced by Razorpay and are not derived from settlement_utr."
)

ScenarioId = Literal[
    "successful_reconciliation",
    "bank_amount_mismatch",
    "missing_settlement",
    "refund_adjusted",
]


@dataclass(frozen=True)
class DemoScenarioBundle:
    """One demonstrable order scenario with separate Razorpay-side and bank-side data."""

    scenario_id: ScenarioId
    description: str
    expected_status: str
    expected_reconciled: bool
    order: NormalizedOrder
    settlements: tuple[NormalizedSettlement, ...]
    refunds: tuple[NormalizedRefund, ...]
    bank_rows: tuple[dict[str, Any], ...]


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def build_demo_scenarios() -> tuple[DemoScenarioBundle, ...]:
    """Return four labelled scenarios for Phase 4A demonstration."""

    # --- 1. Successful reconciliation ---
    order_ok = NormalizedOrder(
        order_id="order_demo_success",
        amount_paise=50000,
        created_at=_dt("2026-08-01T10:00:00"),
    )
    settlement_ok = NormalizedSettlement(
        settlement_id="setl_demo_success",
        order_id="order_demo_success",
        gross_amount_paise=50000,
        fee_paise=1000,
        tax_paise=180,
        net_amount_paise=48820,
        settled_at=_dt("2026-08-02T10:00:00"),
    )
    bank_ok = {
        "bank_transaction_id": "BNK_DEMO_SUCCESS",
        "settlement_ref": "setl_demo_success",
        "amount": 48820,
        "transaction_date": "2026-08-02T10:00:00",
        "description": "SYNTHETIC_BANK_FIXTURE success (not from Razorpay)",
    }

    # --- 2. Bank amount mismatch ---
    order_mismatch = NormalizedOrder(
        order_id="order_demo_bank_mismatch",
        amount_paise=50000,
        created_at=_dt("2026-08-01T11:00:00"),
    )
    settlement_mismatch = NormalizedSettlement(
        settlement_id="setl_demo_bank_mismatch",
        order_id="order_demo_bank_mismatch",
        gross_amount_paise=50000,
        fee_paise=1000,
        tax_paise=180,
        net_amount_paise=48820,
        settled_at=_dt("2026-08-02T11:00:00"),
    )
    bank_mismatch = {
        "bank_transaction_id": "BNK_DEMO_MISMATCH",
        "settlement_ref": "setl_demo_bank_mismatch",
        "amount": 40000,  # intentionally wrong vs net 48820
        "transaction_date": "2026-08-02T13:00:00",
        "description": "SYNTHETIC_BANK_FIXTURE bank amount mismatch (not from Razorpay)",
    }

    # --- 3. Missing settlement (Razorpay-side order only; no settlement mapped) ---
    order_missing = NormalizedOrder(
        order_id="order_demo_missing_settlement",
        amount_paise=50000,
        created_at=_dt("2026-08-01T12:00:00"),
    )

    # --- 4. Refund-adjusted reconciliation ---
    order_refund = NormalizedOrder(
        order_id="order_demo_refund_adjusted",
        amount_paise=50000,
        created_at=_dt("2026-08-01T13:00:00"),
    )
    refund = NormalizedRefund(
        refund_id="rfnd_demo_adjusted",
        order_id="order_demo_refund_adjusted",
        refund_amount_paise=10000,
        created_at=_dt("2026-08-01T14:00:00"),
    )
    settlement_refund = NormalizedSettlement(
        settlement_id="setl_demo_refund_adjusted",
        order_id="order_demo_refund_adjusted",
        gross_amount_paise=40000,  # order - refund
        fee_paise=800,
        tax_paise=144,
        net_amount_paise=39056,
        settled_at=_dt("2026-08-03T10:00:00"),
    )
    bank_refund = {
        "bank_transaction_id": "BNK_DEMO_REFUND",
        "settlement_ref": "setl_demo_refund_adjusted",
        "amount": 39056,
        "transaction_date": "2026-08-03T12:00:00",
        "description": "SYNTHETIC_BANK_FIXTURE refund-adjusted (not from Razorpay)",
    }

    return (
        DemoScenarioBundle(
            scenario_id="successful_reconciliation",
            description="Order + settlement + matching synthetic bank net",
            expected_status="reconciled",
            expected_reconciled=True,
            order=order_ok,
            settlements=(settlement_ok,),
            refunds=(),
            bank_rows=(bank_ok,),
        ),
        DemoScenarioBundle(
            scenario_id="bank_amount_mismatch",
            description="Settlement present; synthetic bank amount != net",
            expected_status="unreconciled_settlement_amount",
            expected_reconciled=False,
            order=order_mismatch,
            settlements=(settlement_mismatch,),
            refunds=(),
            bank_rows=(bank_mismatch,),
        ),
        DemoScenarioBundle(
            scenario_id="missing_settlement",
            description="Razorpay-shaped order with no settlement and no bank",
            expected_status="unreconciled_missing_settlement",
            expected_reconciled=False,
            order=order_missing,
            settlements=(),
            refunds=(),
            bank_rows=(),
        ),
        DemoScenarioBundle(
            scenario_id="refund_adjusted",
            description="Refund reflected in settlement gross; bank matches adjusted net",
            expected_status="reconciled_with_refund_adjustment",
            expected_reconciled=True,
            order=order_refund,
            settlements=(settlement_refund,),
            refunds=(refund,),
            bank_rows=(bank_refund,),
        ),
    )


@dataclass(frozen=True)
class DemoReconciliationInput:
    """Merged demo inputs with explicit source labels."""

    orders: tuple[NormalizedOrder, ...]
    settlements: tuple[NormalizedSettlement, ...]
    refunds: tuple[NormalizedRefund, ...]
    bank_transactions: tuple[NormalizedBankTransaction, ...]
    scenarios: tuple[DemoScenarioBundle, ...]
    data_source: Literal["razorpay"] = DEMO_DATA_SOURCE
    bank_source: str = DEMO_BANK_SOURCE
    bank_source_note: str = DEMO_BANK_SOURCE_NOTE


def build_demo_reconciliation_input() -> DemoReconciliationInput:
    """Assemble all Phase 4A scenarios into one reconciliation input set."""
    scenarios = build_demo_scenarios()
    orders = tuple(s.order for s in scenarios)
    settlements = tuple(st for s in scenarios for st in s.settlements)
    refunds = tuple(rf for s in scenarios for rf in s.refunds)
    bank_row_dicts = [row for s in scenarios for row in s.bank_rows]

    valid_settlement_ids = {st.settlement_id for st in settlements}
    if bank_row_dicts:
        bank_transactions = tuple(
            normalize_bank_transactions(pd.DataFrame(bank_row_dicts), valid_settlement_ids)
        )
    else:
        bank_transactions = ()

    return DemoReconciliationInput(
        orders=orders,
        settlements=settlements,
        refunds=refunds,
        bank_transactions=bank_transactions,
        scenarios=scenarios,
    )


def scenario_expectations() -> list[dict[str, Any]]:
    """Compact expected outcomes for API/tests."""
    return [
        {
            "scenario_id": s.scenario_id,
            "order_id": s.order.order_id,
            "description": s.description,
            "expected_status": s.expected_status,
            "expected_reconciled": s.expected_reconciled,
        }
        for s in build_demo_scenarios()
    ]
