"""Synthetic data generation for ReconEngine reconciliation testing."""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from faker import Faker

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

NUM_ORDERS = 100
NUM_SETTLEMENTS = 100
NUM_REFUNDS = 20
NUM_BANK_TRANSACTIONS = 100

RANDOM_SEED = 42

BASE_DATE = datetime(2026, 8, 1, 10, 0, 0)

DATA_DIR = Path(__file__).resolve().parent / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.json"

# Reconciliation tolerance used when documenting expected outcomes.
TIMESTAMP_TOLERANCE_HOURS = 24

# Fee/tax rates applied deterministically from order gross (basis points).
FEE_RATE_BPS = 200  # 2.00%
TAX_RATE_BPS = 180  # 1.80% of gross

# Bank amount offset for settlement_amount_mismatch scenarios (paise).
SETTLEMENT_AMOUNT_MISMATCH_BANK_OFFSET_PAISE = 2500

# Primary evaluation grain for metrics.py.
EVALUATION_GRAIN = "order"

ORDERS_COLUMNS = ("order_id", "amount", "created_at")
SETTLEMENTS_COLUMNS = (
    "settlement_id",
    "order_id",
    "gross_amount",
    "fee",
    "tax",
    "net_amount",
    "settled_at",
)
REFUNDS_COLUMNS = ("refund_id", "order_id", "refund_amount", "created_at")
BANK_COLUMNS = (
    "bank_transaction_id",
    "settlement_ref",
    "amount",
    "transaction_date",
    "description",
)

# Finite vocabulary: expected reconciliation OUTCOME per order.
EXPECTED_STATUS_VOCABULARY: frozenset[str] = frozenset(
    {
        "reconciled",
        "reconciled_within_timestamp_tolerance",
        "unreconciled_timestamp_exceeded",
        "unreconciled_settlement_amount",
        "unreconciled_missing_settlement",
        "unreconciled_missing_bank",
        "reconciled_with_refund_adjustment",
        "unreconciled_refund_not_adjusted",
        "reconciled_with_reference_variation",
        "partially_reconciled_duplicate_settlement",
    }
)

# scenario_type (why) -> default expected_status (outcome).
SCENARIO_TO_EXPECTED_STATUS: dict[str, str] = {
    "exact_match": "reconciled",
    "timestamp_within_tolerance": "reconciled_within_timestamp_tolerance",
    "timestamp_outside_tolerance": "unreconciled_timestamp_exceeded",
    "settlement_amount_mismatch": "unreconciled_settlement_amount",
    "missing_settlement": "unreconciled_missing_settlement",
    "missing_bank_transaction": "unreconciled_missing_bank",
    "refund_adjusted": "reconciled_with_refund_adjustment",
    "refund_unadjusted_mismatch": "unreconciled_refund_not_adjusted",
    "reference_variation": "reconciled_with_reference_variation",
    "duplicate_settlement": "partially_reconciled_duplicate_settlement",
}

# Whether the order is expected to be fully reconciled at order-level grain.
EXPECTED_RECONCILED_BY_STATUS: dict[str, bool] = {
    "reconciled": True,
    "reconciled_within_timestamp_tolerance": True,
    "unreconciled_timestamp_exceeded": False,
    "unreconciled_settlement_amount": False,
    "unreconciled_missing_settlement": False,
    "unreconciled_missing_bank": False,
    "reconciled_with_refund_adjustment": True,
    "unreconciled_refund_not_adjusted": False,
    "reconciled_with_reference_variation": True,
    "partially_reconciled_duplicate_settlement": False,
}

REQUIRED_GROUND_TRUTH_ORDER_FIELDS: tuple[str, ...] = (
    "order_id",
    "scenario_type",
    "expected_status",
    "expected_reconciled",
    "evaluation_grain",
    "primary_settlement_id",
    "primary_bank_transaction_id",
    "order_amount_paise",
    "total_refund_paise",
    "settlement_ids",
    "refund_ids",
    "valid_bank_transaction_ids",
    "notes",
)

# Deterministic scenario assignment by order index (1-based).
# Indices 1–50 preserve the original operational batch layout.
SCENARIO_BY_ORDER_INDEX: dict[int, str] = {
    **{i: "exact_match" for i in range(1, 13)},
    **{i: "timestamp_within_tolerance" for i in range(13, 18)},
    18: "timestamp_outside_tolerance",
    **{i: "settlement_amount_mismatch" for i in range(19, 24)},
    **{i: "missing_settlement" for i in range(24, 28)},
    **{i: "missing_bank_transaction" for i in range(28, 33)},
    **{i: "refund_adjusted" for i in range(33, 38)},
    **{i: "reference_variation" for i in range(38, 43)},
    **{i: "exact_match" for i in range(43, 46)},
    **{i: "duplicate_settlement" for i in range(46, 50)},
    50: "exact_match",
    # Indices 51–100 mirror the same scenario mix for a 100-order operational batch.
    **{i: "exact_match" for i in range(51, 63)},
    **{i: "timestamp_within_tolerance" for i in range(63, 68)},
    68: "timestamp_outside_tolerance",
    **{i: "settlement_amount_mismatch" for i in range(69, 74)},
    **{i: "missing_settlement" for i in range(74, 78)},
    **{i: "missing_bank_transaction" for i in range(78, 83)},
    **{i: "refund_adjusted" for i in range(83, 88)},
    **{i: "reference_variation" for i in range(88, 93)},
    **{i: "exact_match" for i in range(93, 96)},
    **{i: "duplicate_settlement" for i in range(96, 100)},
    100: "exact_match",
}

# Override exact_match defaults for orders with unadjusted refunds.
for _idx in (5, 8, 10, 43, 44, 55, 58, 60, 93, 94):
    SCENARIO_BY_ORDER_INDEX[_idx] = "refund_unadjusted_mismatch"

# Orders receiving refunds (index -> refund fraction of order amount).
REFUND_BY_ORDER_INDEX: dict[int, float] = {
    33: 0.25,
    34: 0.50,
    35: 0.75,
    36: 0.30,
    37: 0.15,
    5: 0.10,
    8: 0.20,
    10: 0.05,
    43: 0.12,
    44: 0.08,
    83: 0.25,
    84: 0.50,
    85: 0.75,
    86: 0.30,
    87: 0.15,
    55: 0.10,
    58: 0.20,
    60: 0.05,
    93: 0.12,
    94: 0.08,
}

# Erroneous duplicate bank rows for the original 50-order block (fixed BNK ids).
DUP_BANK_ASSIGNMENTS_BLOCK_1: list[tuple[int, str]] = [
    (46, "SET_0046"),
    (47, "SET_0047"),
    (48, "SET_0048"),
    (49, "SET_0049"),
    (50, "SET_0050"),
]

fake = Faker()
random.seed(RANDOM_SEED)
Faker.seed(RANDOM_SEED)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


def order_id_for_index(index: int) -> str:
    """Return canonical order_id for a 1-based index."""
    return f"ORD_{index:04d}"


def settlement_id_for_index(index: int) -> str:
    """Return canonical settlement_id for a 1-based index."""
    return f"SET_{index:04d}"


def refund_id_for_index(index: int) -> str:
    """Return canonical refund_id for a 1-based index."""
    return f"RFN_{index:04d}"


def bank_transaction_id_for_index(index: int) -> str:
    """Return canonical bank_transaction_id for a 1-based index."""
    return f"BNK_{index:04d}"


def order_index_from_id(order_id: str) -> int:
    """Parse 1-based order index from order_id."""
    return int(order_id.split("_")[1])


def parse_iso_datetime(value: str) -> datetime:
    """Parse ISO datetime strings produced by this module."""
    return datetime.fromisoformat(value)


def compute_settlement_amounts(gross_amount: int) -> tuple[int, int, int]:
    """Return (fee, tax, net_amount) in paise for a gross amount."""
    fee = gross_amount * FEE_RATE_BPS // 10000
    tax = gross_amount * TAX_RATE_BPS // 10000
    net_amount = gross_amount - fee - tax
    return fee, tax, net_amount


def settlement_offset_hours(order_index: int) -> int:
    """Deterministic hours after order creation for settlement."""
    return 24 + (order_index * 7) % 72


def bank_offset_hours(settlement_index: int, scenario: str) -> int:
    """Deterministic hours after settlement for bank transaction."""
    if scenario == "timestamp_within_tolerance":
        return 2 + (settlement_index % 12)  # 2-13 hours (within 24h tolerance)
    if scenario == "timestamp_outside_tolerance":
        return 48 + (settlement_index % 48)  # 48-95 hours (outside tolerance)
    return 6 + (settlement_index % 12)  # 6-17 hours for standard cases


def alternate_settlement_ref(settlement_id: str) -> str:
    """Produce a reference variation for bank records."""
    return settlement_id.replace("SET_", "STL-")


def normalize_settlement_ref(
    settlement_ref: str,
    valid_settlement_ids: set[str],
) -> str | None:
    """Resolve a bank settlement_ref to a canonical settlement_id.

    ORPHAN-* and DUP-* refs intentionally do not resolve.
    STL-* refs normalize to SET_* when the settlement exists.
    """
    if settlement_ref.startswith(("ORPHAN-", "DUP-")):
        return None
    if settlement_ref.startswith("SET_") and settlement_ref in valid_settlement_ids:
        return settlement_ref
    if settlement_ref.startswith("STL-"):
        canonical = settlement_ref.replace("STL-", "SET_", 1)
        if canonical in valid_settlement_ids:
            return canonical
    return None


def valid_bank_transactions_for_settlements(
    bank_df: pd.DataFrame,
    settlement_ids: list[str],
    valid_settlement_ids: set[str],
) -> pd.DataFrame:
    """Return bank rows whose settlement_ref resolves to one of settlement_ids."""
    if not settlement_ids:
        return bank_df.iloc[0:0]

    target_ids = set(settlement_ids)
    matching_ids: list[str] = []
    for _, row in bank_df.iterrows():
        resolved = normalize_settlement_ref(str(row["settlement_ref"]), valid_settlement_ids)
        if resolved in target_ids:
            matching_ids.append(str(row["bank_transaction_id"]))

    return bank_df[bank_df["bank_transaction_id"].isin(matching_ids)]


def reset_random_state() -> None:
    """Reset RNG state for deterministic generation."""
    random.seed(RANDOM_SEED)
    Faker.seed(RANDOM_SEED)


# ---------------------------------------------------------
# Order Generation
# ---------------------------------------------------------


def generate_orders() -> pd.DataFrame:
    """Generate the synthetic order dataset."""

    orders = []

    for index in range(1, NUM_ORDERS + 1):
        order_id = order_id_for_index(index)

        amount = random.randint(50000, 500000)

        created_at = BASE_DATE + timedelta(
            minutes=random.randint(0, 60 * 24 * 30)
        )

        orders.append(
            {
                "order_id": order_id,
                "amount": amount,
                "created_at": created_at.isoformat(),
            }
        )

    return pd.DataFrame(orders)


# ---------------------------------------------------------
# Settlement Generation
# ---------------------------------------------------------


def generate_settlements(orders_df: pd.DataFrame) -> pd.DataFrame:
    """Generate settlement records linked to orders (integer paise)."""
    orders_by_id = orders_df.set_index("order_id")
    settlements: list[dict[str, Any]] = []
    settlement_index = 1

    for order_index in range(1, NUM_ORDERS + 1):
        scenario = SCENARIO_BY_ORDER_INDEX[order_index]
        if scenario == "missing_settlement":
            continue

        order_id = order_id_for_index(order_index)
        order_row = orders_by_id.loc[order_id]
        order_created = parse_iso_datetime(order_row["created_at"])
        gross_amount = int(order_row["amount"])

        if scenario == "settlement_amount_mismatch":
            gross_amount += 5000 + (order_index * 100)

        fee, tax, net_amount = compute_settlement_amounts(gross_amount)

        if scenario == "refund_adjusted":
            refund_fraction = REFUND_BY_ORDER_INDEX.get(order_index, 0.0)
            refund_amount = int(order_row["amount"] * refund_fraction)
            gross_amount = max(gross_amount - refund_amount, 0)
            fee, tax, net_amount = compute_settlement_amounts(gross_amount)

        settled_at = order_created + timedelta(
            hours=settlement_offset_hours(order_index)
        )

        settlements.append(
            {
                "settlement_id": settlement_id_for_index(settlement_index),
                "order_id": order_id,
                "gross_amount": gross_amount,
                "fee": fee,
                "tax": tax,
                "net_amount": net_amount,
                "settled_at": settled_at.isoformat(),
            }
        )
        settlement_index += 1

        if scenario == "duplicate_settlement":
            duplicate_gross = gross_amount // 2
            dup_fee, dup_tax, dup_net = compute_settlement_amounts(duplicate_gross)
            settlements.append(
                {
                    "settlement_id": settlement_id_for_index(settlement_index),
                    "order_id": order_id,
                    "gross_amount": duplicate_gross,
                    "fee": dup_fee,
                    "tax": dup_tax,
                    "net_amount": dup_net,
                    "settled_at": (settled_at + timedelta(hours=6)).isoformat(),
                }
            )
            settlement_index += 1

    return pd.DataFrame(settlements)


# ---------------------------------------------------------
# Refund Generation
# ---------------------------------------------------------


def generate_refunds(orders_df: pd.DataFrame) -> pd.DataFrame:
    """Generate refund records linked to orders."""
    orders_by_id = orders_df.set_index("order_id")
    refunds: list[dict[str, Any]] = []

    for refund_index, (order_index, fraction) in enumerate(
        sorted(REFUND_BY_ORDER_INDEX.items()), start=1
    ):
        order_id = order_id_for_index(order_index)
        order_row = orders_by_id.loc[order_id]
        order_amount = int(order_row["amount"])
        refund_amount = max(1, int(order_amount * fraction))
        refund_amount = min(refund_amount, order_amount)

        order_created = parse_iso_datetime(order_row["created_at"])
        created_at = order_created + timedelta(
            hours=48 + (order_index * 3) % 120
        )

        refunds.append(
            {
                "refund_id": refund_id_for_index(refund_index),
                "order_id": order_id,
                "refund_amount": refund_amount,
                "created_at": created_at.isoformat(),
            }
        )

    return pd.DataFrame(refunds)


# ---------------------------------------------------------
# Bank Transaction Generation
# ---------------------------------------------------------


def generate_bank_transactions(
    settlements_df: pd.DataFrame,
    orders_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate bank transactions referencing settlements.

    Phase 1 preserves BNK_0001–BNK_0050 layout for orders 1–50.
    Phase 2 appends BNK_0051+ for orders 51–NUM_ORDERS.
    """
    orders_by_id = orders_df.set_index("order_id")
    settlements_by_id = settlements_df.set_index("settlement_id")
    bank_rows: list[dict[str, Any]] = []

    order_index_by_id = {
        order_id_for_index(i): i for i in range(1, NUM_ORDERS + 1)
    }

    def _append_settlement_banks(order_indices: set[int], bank_index_start: int) -> int:
        bank_index = bank_index_start
        for _, settlement in settlements_df.iterrows():
            order_index = order_index_by_id[settlement["order_id"]]
            if order_index not in order_indices:
                continue
            scenario = SCENARIO_BY_ORDER_INDEX[order_index]

            if scenario == "missing_bank_transaction":
                continue

            if scenario == "duplicate_settlement":
                duplicate_ids = settlements_df[
                    settlements_df["order_id"] == settlement["order_id"]
                ]["settlement_id"].tolist()
                if settlement["settlement_id"] != duplicate_ids[0]:
                    continue

            settlement_id = settlement["settlement_id"]
            settled_at = parse_iso_datetime(settlement["settled_at"])
            amount = int(settlement["net_amount"])

            if scenario == "settlement_amount_mismatch":
                amount += SETTLEMENT_AMOUNT_MISMATCH_BANK_OFFSET_PAISE

            if scenario == "reference_variation":
                settlement_ref = alternate_settlement_ref(settlement_id)
            else:
                settlement_ref = settlement_id

            transaction_date = settled_at + timedelta(
                hours=bank_offset_hours(bank_index, scenario)
            )

            bank_rows.append(
                {
                    "bank_transaction_id": bank_transaction_id_for_index(bank_index),
                    "settlement_ref": settlement_ref,
                    "amount": amount,
                    "transaction_date": transaction_date.isoformat(),
                    "description": f"Payout {settlement['order_id']}",
                }
            )
            bank_index += 1
        return bank_index

    def _append_orphan_banks(order_indices: range | list[int], bank_index_start: int) -> int:
        bank_index = bank_index_start
        for order_index in order_indices:
            if SCENARIO_BY_ORDER_INDEX.get(order_index) != "missing_settlement":
                continue
            order_id = order_id_for_index(order_index)
            order_row = orders_by_id.loc[order_id]
            order_created = parse_iso_datetime(order_row["created_at"])
            _, _, net_amount = compute_settlement_amounts(int(order_row["amount"]))

            bank_rows.append(
                {
                    "bank_transaction_id": bank_transaction_id_for_index(bank_index),
                    "settlement_ref": f"ORPHAN-{order_id}",
                    "amount": net_amount,
                    "transaction_date": (order_created + timedelta(days=5)).isoformat(),
                    "description": f"Unmatched payout {order_id}",
                }
            )
            bank_index += 1
        return bank_index

    def _append_dup_banks(assignments: list[tuple[int, str]]) -> None:
        for dup_bank_index, source_settlement_id in assignments:
            source_settlement = settlements_by_id.loc[source_settlement_id]
            settled_at = parse_iso_datetime(source_settlement["settled_at"])
            bank_rows.append(
                {
                    "bank_transaction_id": bank_transaction_id_for_index(dup_bank_index),
                    "settlement_ref": f"DUP-{source_settlement_id}",
                    "amount": int(source_settlement["net_amount"]) + 100,
                    "transaction_date": (settled_at + timedelta(days=2)).isoformat(),
                    "description": f"Duplicate payout {source_settlement['order_id']}",
                }
            )

    # Phase 1 — original 50-order bank layout (BNK_0001–BNK_0050).
    bank_index = _append_settlement_banks(set(range(1, 51)), 1)
    bank_index = _append_orphan_banks(range(24, 28), bank_index)
    _append_dup_banks(DUP_BANK_ASSIGNMENTS_BLOCK_1)

    # Phase 2 — orders 51–100 continue from BNK_0051.
    if NUM_ORDERS > 50:
        bank_index = _append_settlement_banks(set(range(51, NUM_ORDERS + 1)), 51)
        bank_index = _append_orphan_banks(
            [i for i in range(51, NUM_ORDERS + 1) if SCENARIO_BY_ORDER_INDEX[i] == "missing_settlement"],
            bank_index,
        )
        # Duplicate bank rows for second-block duplicate_settlement orders (+ ORD_0100 mirror).
        dup_assignments_block_2: list[tuple[int, str]] = []
        for order_index in list(range(96, 100)) + ([100] if NUM_ORDERS >= 100 else []):
            order_settlements = settlements_df[
                settlements_df["order_id"] == order_id_for_index(order_index)
            ]
            if order_settlements.empty:
                continue
            primary_sid = str(order_settlements.iloc[0]["settlement_id"])
            dup_assignments_block_2.append((bank_index, primary_sid))
            bank_index += 1
        _append_dup_banks(dup_assignments_block_2)

    bank_rows.sort(key=lambda row: row["bank_transaction_id"])
    return pd.DataFrame(bank_rows[:NUM_BANK_TRANSACTIONS])


# ---------------------------------------------------------
# Ground Truth
# ---------------------------------------------------------


def _scenario_notes(
    scenario_type: str,
    *,
    total_refund: int,
    mismatch_details: dict[str, Any] | None = None,
) -> str:
    """Return human-readable notes for a scenario."""
    if scenario_type == "missing_settlement":
        return "Order exists; no settlement record was generated."
    if scenario_type == "missing_bank_transaction":
        return "Settlement exists; no valid bank transaction references it via settlement_ref."
    if scenario_type == "settlement_amount_mismatch" and mismatch_details:
        return (
            "Settlement gross_amount differs from order amount; bank amount differs "
            f"from settlement net by {mismatch_details['bank_net_delta_paise']} paise."
        )
    if scenario_type == "refund_adjusted":
        return "Settlement gross reflects refund deduction; bank matches settlement net."
    if scenario_type == "refund_unadjusted_mismatch":
        return (
            "Refund exists but settlement gross was not adjusted; "
            f"total_refund_paise={total_refund}."
        )
    if scenario_type == "duplicate_settlement":
        return (
            "Two settlements exist; only the primary settlement has a valid bank "
            "transaction via settlement_ref."
        )
    if scenario_type == "reference_variation":
        return "Bank settlement_ref uses STL- prefix; normalizes to SET_ settlement_id."
    if scenario_type == "timestamp_within_tolerance":
        return f"Bank timestamp within {TIMESTAMP_TOLERANCE_HOURS}h of settlement settled_at."
    if scenario_type == "timestamp_outside_tolerance":
        return f"Bank timestamp exceeds {TIMESTAMP_TOLERANCE_HOURS}h tolerance from settled_at."
    return "Order, settlement, and bank amounts align via settlement_ref linkage."


def build_ground_truth(
    orders_df: pd.DataFrame,
    settlements_df: pd.DataFrame,
    refunds_df: pd.DataFrame,
    bank_df: pd.DataFrame,
) -> dict[str, Any]:
    """Build machine-readable expected outcomes for metrics evaluation."""
    valid_settlement_ids = set(settlements_df["settlement_id"])
    scenarios: list[dict[str, Any]] = []

    for order_index in range(1, NUM_ORDERS + 1):
        order_id = order_id_for_index(order_index)
        scenario_type = SCENARIO_BY_ORDER_INDEX[order_index]
        expected_status = SCENARIO_TO_EXPECTED_STATUS[scenario_type]
        expected_reconciled = EXPECTED_RECONCILED_BY_STATUS[expected_status]

        order_amount = int(
            orders_df.loc[orders_df["order_id"] == order_id, "amount"].iloc[0]
        )
        order_settlements = settlements_df[settlements_df["order_id"] == order_id]
        settlement_ids = order_settlements["settlement_id"].tolist()
        order_refunds = refunds_df[refunds_df["order_id"] == order_id]
        total_refund = (
            int(order_refunds["refund_amount"].sum()) if not order_refunds.empty else 0
        )

        primary_settlement_id: str | None = settlement_ids[0] if settlement_ids else None
        secondary_settlement_id: str | None = (
            settlement_ids[1] if len(settlement_ids) > 1 else None
        )

        valid_banks = valid_bank_transactions_for_settlements(
            bank_df, settlement_ids, valid_settlement_ids
        )
        valid_bank_ids = valid_banks["bank_transaction_id"].tolist()
        primary_bank_id: str | None = None
        if primary_settlement_id:
            primary_matches = valid_bank_transactions_for_settlements(
                bank_df, [primary_settlement_id], valid_settlement_ids
            )
            if not primary_matches.empty:
                primary_bank_id = str(primary_matches.iloc[0]["bank_transaction_id"])

        mismatch_details: dict[str, Any] | None = None
        if scenario_type == "settlement_amount_mismatch" and primary_settlement_id:
            settlement_row = order_settlements.iloc[0]
            settlement_gross = int(settlement_row["gross_amount"])
            settlement_net = int(settlement_row["net_amount"])
            bank_row = valid_banks.iloc[0] if not valid_banks.empty else None
            bank_amount = int(bank_row["amount"]) if bank_row is not None else None
            mismatch_details = {
                "order_amount_paise": order_amount,
                "settlement_gross_paise": settlement_gross,
                "settlement_net_paise": settlement_net,
                "bank_amount_paise": bank_amount,
                "settlement_gross_delta_paise": settlement_gross - order_amount,
                "bank_net_delta_paise": SETTLEMENT_AMOUNT_MISMATCH_BANK_OFFSET_PAISE,
            }

        entry: dict[str, Any] = {
            "order_id": order_id,
            "scenario_type": scenario_type,
            "expected_status": expected_status,
            "expected_reconciled": expected_reconciled,
            "evaluation_grain": EVALUATION_GRAIN,
            "primary_settlement_id": primary_settlement_id,
            "secondary_settlement_id": secondary_settlement_id,
            "primary_bank_transaction_id": primary_bank_id,
            "order_amount_paise": order_amount,
            "total_refund_paise": total_refund,
            "settlement_ids": settlement_ids,
            "refund_ids": order_refunds["refund_id"].tolist(),
            "valid_bank_transaction_ids": valid_bank_ids,
            "notes": _scenario_notes(
                scenario_type,
                total_refund=total_refund,
                mismatch_details=mismatch_details,
            ),
        }
        if mismatch_details:
            entry["mismatch_details"] = mismatch_details

        scenarios.append(entry)

    scenario_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for scenario in scenarios:
        scenario_counts[scenario["scenario_type"]] = (
            scenario_counts.get(scenario["scenario_type"], 0) + 1
        )
        status_counts[scenario["expected_status"]] = (
            status_counts.get(scenario["expected_status"], 0) + 1
        )

    settlements_without_bank = sorted(
        sid
        for sid in valid_settlement_ids
        if valid_bank_transactions_for_settlements(
            bank_df, [sid], valid_settlement_ids
        ).empty
    )

    duplicate_settlement_records: list[dict[str, Any]] = []
    for order_index in range(1, NUM_ORDERS + 1):
        if SCENARIO_BY_ORDER_INDEX[order_index] != "duplicate_settlement":
            continue
        order_id = order_id_for_index(order_index)
        order_settlements = settlements_df[settlements_df["order_id"] == order_id]
        if len(order_settlements) < 2:
            continue
        primary_sid = str(order_settlements.iloc[0]["settlement_id"])
        secondary_sid = str(order_settlements.iloc[1]["settlement_id"])
        primary_bank = valid_bank_transactions_for_settlements(
            bank_df, [primary_sid], valid_settlement_ids
        )
        duplicate_settlement_records.append(
            {
                "order_id": order_id,
                "primary_settlement_id": primary_sid,
                "secondary_settlement_id": secondary_sid,
                "primary_bank_transaction_id": (
                    str(primary_bank.iloc[0]["bank_transaction_id"])
                    if not primary_bank.empty
                    else None
                ),
                "secondary_has_valid_bank": False,
            }
        )

    orphan_bank_records: list[dict[str, Any]] = []
    for _, row in bank_df[bank_df["settlement_ref"].str.startswith("ORPHAN-")].iterrows():
        related_order = str(row["settlement_ref"]).replace("ORPHAN-", "")
        orphan_bank_records.append(
            {
                "bank_transaction_id": str(row["bank_transaction_id"]),
                "settlement_ref": str(row["settlement_ref"]),
                "related_order_id": related_order,
                "resolves_to_settlement": False,
            }
        )

    duplicate_bank_records: list[dict[str, Any]] = []
    for _, row in bank_df[bank_df["settlement_ref"].str.startswith("DUP-")].iterrows():
        source_settlement = str(row["settlement_ref"]).replace("DUP-", "")
        related_order = None
        if source_settlement in valid_settlement_ids:
            related_order = str(
                settlements_df.loc[
                    settlements_df["settlement_id"] == source_settlement, "order_id"
                ].iloc[0]
            )
        duplicate_bank_records.append(
            {
                "bank_transaction_id": str(row["bank_transaction_id"]),
                "settlement_ref": str(row["settlement_ref"]),
                "source_settlement_id": source_settlement,
                "related_order_id": related_order,
                "is_valid_bank_link": False,
                "erroneous_duplicate": True,
            }
        )

    return {
        "metadata": {
            "random_seed": RANDOM_SEED,
            "generated_at": BASE_DATE.isoformat(),
            "timestamp_tolerance_hours": TIMESTAMP_TOLERANCE_HOURS,
            "currency": "INR",
            "minor_unit": "paise",
            "evaluation_grain": EVALUATION_GRAIN,
            "expected_status_vocabulary": sorted(EXPECTED_STATUS_VOCABULARY),
            "true_negative_definition": (
                "At order-level grain: TN is an order the engine correctly marks as "
                "not fully reconciled (expected_reconciled=false) when ground truth "
                "expected_reconciled is false. Link-level or transaction-level metrics "
                "may omit TN where negative predictions are not meaningfully defined."
            ),
            "record_counts": {
                "orders": len(orders_df),
                "settlements": len(settlements_df),
                "refunds": len(refunds_df),
                "bank_transactions": len(bank_df),
            },
        },
        "scenario_counts": scenario_counts,
        "expected_status_counts": status_counts,
        "scenarios": scenarios,
        "special_records": {
            "orphan_bank_transactions": orphan_bank_records,
            "duplicate_bank_transactions": duplicate_bank_records,
            "duplicate_settlements": duplicate_settlement_records,
            "settlements_without_bank": settlements_without_bank,
            "alternate_reference_map": {
                str(row["settlement_id"]): alternate_settlement_ref(str(row["settlement_id"]))
                for _, row in settlements_df.iterrows()
                if SCENARIO_BY_ORDER_INDEX[order_index_from_id(str(row["order_id"]))]
                == "reference_variation"
            },
        },
    }


# ---------------------------------------------------------
# Validation
# ---------------------------------------------------------


def _validate_columns(df: pd.DataFrame, expected: tuple[str, ...], name: str) -> None:
    missing = set(expected) - set(df.columns)
    extra = set(df.columns) - set(expected)
    if missing or extra:
        raise ValueError(
            f"{name} column mismatch. Missing: {sorted(missing)} Extra: {sorted(extra)}"
        )


def _validate_unique_ids(df: pd.DataFrame, id_column: str, name: str) -> None:
    if df[id_column].duplicated().any():
        dupes = df[df[id_column].duplicated()][id_column].tolist()
        raise ValueError(f"Duplicate {name} IDs: {dupes}")


def _validate_ground_truth_bank_linkage(
    scenarios: list[dict[str, Any]],
    bank_df: pd.DataFrame,
    settlements_df: pd.DataFrame,
) -> None:
    """Ensure ground-truth bank IDs match settlement_ref resolution only."""
    valid_settlement_ids = set(settlements_df["settlement_id"])
    dup_bank_ids = set(
        bank_df.loc[bank_df["settlement_ref"].str.startswith("DUP-"), "bank_transaction_id"]
    )

    for scenario in scenarios:
        order_id = scenario["order_id"]
        settlement_ids = scenario["settlement_ids"]
        valid_ids = set(scenario["valid_bank_transaction_ids"])

        computed = set(
            valid_bank_transactions_for_settlements(
                bank_df, settlement_ids, valid_settlement_ids
            )["bank_transaction_id"]
        )
        if valid_ids != computed:
            raise ValueError(
                f"{order_id}: valid_bank_transaction_ids {sorted(valid_ids)} != "
                f"settlement_ref-derived {sorted(computed)}"
            )

        if scenario["primary_bank_transaction_id"] not in (
            scenario["valid_bank_transaction_ids"] + [None]
        ):
            raise ValueError(
                f"{order_id}: primary_bank_transaction_id not in valid_bank_transaction_ids"
            )

        if dup_bank_ids & valid_ids:
            raise ValueError(
                f"{order_id}: duplicate bank transaction incorrectly listed as valid"
            )

        if scenario["scenario_type"] == "exact_match" and scenario["total_refund_paise"] > 0:
            raise ValueError(
                f"{order_id}: exact_match order must not have undisclosed refund mismatch"
            )

        if scenario["scenario_type"] == "refund_unadjusted_mismatch":
            if scenario["total_refund_paise"] <= 0:
                raise ValueError(
                    f"{order_id}: refund_unadjusted_mismatch requires a refund"
                )
            if settlement_ids:
                order_amount = scenario["order_amount_paise"]
                gross = int(
                    settlements_df.loc[
                        settlements_df["settlement_id"] == settlement_ids[0],
                        "gross_amount",
                    ].iloc[0]
                )
                if gross != order_amount:
                    raise ValueError(
                        f"{order_id}: refund_unadjusted_mismatch requires unadjusted gross"
                    )


def validate_dataset(
    orders_df: pd.DataFrame,
    settlements_df: pd.DataFrame,
    refunds_df: pd.DataFrame,
    bank_df: pd.DataFrame,
    ground_truth: dict[str, Any],
) -> list[str]:
    """Validate generated datasets; return list of validation messages."""
    messages: list[str] = []

    if len(orders_df) != NUM_ORDERS:
        raise ValueError(f"Expected {NUM_ORDERS} orders, got {len(orders_df)}")
    if len(settlements_df) != NUM_SETTLEMENTS:
        raise ValueError(
            f"Expected {NUM_SETTLEMENTS} settlements, got {len(settlements_df)}"
        )
    if len(refunds_df) != NUM_REFUNDS:
        raise ValueError(f"Expected {NUM_REFUNDS} refunds, got {len(refunds_df)}")
    if len(bank_df) != NUM_BANK_TRANSACTIONS:
        raise ValueError(
            f"Expected {NUM_BANK_TRANSACTIONS} bank transactions, got {len(bank_df)}"
        )

    _validate_columns(orders_df, ORDERS_COLUMNS, "orders")
    _validate_columns(settlements_df, SETTLEMENTS_COLUMNS, "settlements")
    _validate_columns(refunds_df, REFUNDS_COLUMNS, "refunds")
    _validate_columns(bank_df, BANK_COLUMNS, "bank")

    _validate_unique_ids(orders_df, "order_id", "order")
    _validate_unique_ids(settlements_df, "settlement_id", "settlement")
    _validate_unique_ids(refunds_df, "refund_id", "refund")
    _validate_unique_ids(bank_df, "bank_transaction_id", "bank transaction")

    order_ids = set(orders_df["order_id"])
    if not set(settlements_df["order_id"]).issubset(order_ids):
        raise ValueError("Settlement order_id references unknown orders")
    if not set(refunds_df["order_id"]).issubset(order_ids):
        raise ValueError("Refund order_id references unknown orders")

    if (orders_df["amount"] <= 0).any():
        raise ValueError("Order amounts must be positive")
    if (settlements_df[["gross_amount", "fee", "tax", "net_amount"]] <= 0).any().any():
        raise ValueError("Settlement monetary fields must be positive")
    if (refunds_df["refund_amount"] <= 0).any():
        raise ValueError("Refund amounts must be positive")
    if (bank_df["amount"] <= 0).any():
        raise ValueError("Bank amounts must be positive")

    orders_by_id = orders_df.set_index("order_id")["amount"]
    for _, refund in refunds_df.iterrows():
        order_amount = int(orders_by_id[refund["order_id"]])
        if int(refund["refund_amount"]) > order_amount:
            raise ValueError(
                f"Refund {refund['refund_id']} exceeds order amount for {refund['order_id']}"
            )

    for _, settlement in settlements_df.iterrows():
        gross = int(settlement["gross_amount"])
        fee, tax, net = compute_settlement_amounts(gross)
        if int(settlement["fee"]) != fee or int(settlement["tax"]) != tax:
            raise ValueError(
                f"Settlement {settlement['settlement_id']} fee/tax calculation mismatch"
            )
        if int(settlement["net_amount"]) != net:
            raise ValueError(
                f"Settlement {settlement['settlement_id']} net_amount calculation mismatch"
            )

    for order_index in range(1, NUM_ORDERS + 1):
        order_id = order_id_for_index(order_index)
        order_created = parse_iso_datetime(
            orders_df.loc[orders_df["order_id"] == order_id, "created_at"].iloc[0]
        )
        order_settlements = settlements_df[settlements_df["order_id"] == order_id]
        for _, settlement in order_settlements.iterrows():
            settled_at = parse_iso_datetime(settlement["settled_at"])
            if settled_at <= order_created:
                raise ValueError(
                    f"Settlement {settlement['settlement_id']} settled_at "
                    f"must be after order creation"
                )

    reset_random_state()
    regenerated_orders = generate_orders()
    if not regenerated_orders.equals(orders_df):
        raise ValueError("Order generation is not deterministic for RANDOM_SEED")

    metadata = ground_truth["metadata"]
    if metadata.get("evaluation_grain") != EVALUATION_GRAIN:
        raise ValueError("Ground truth metadata missing or incorrect evaluation_grain")

    required_scenarios = set(SCENARIO_TO_EXPECTED_STATUS.keys())
    present_scenarios = set(ground_truth["scenario_counts"].keys())
    missing_scenarios = required_scenarios - present_scenarios
    if missing_scenarios:
        raise ValueError(f"Missing reconciliation scenarios: {sorted(missing_scenarios)}")

    for scenario in ground_truth["scenarios"]:
        for field in REQUIRED_GROUND_TRUTH_ORDER_FIELDS:
            if field not in scenario:
                raise ValueError(f"{scenario['order_id']}: missing ground-truth field {field}")
        if scenario["expected_status"] not in EXPECTED_STATUS_VOCABULARY:
            raise ValueError(
                f"{scenario['order_id']}: unsupported expected_status "
                f"{scenario['expected_status']}"
            )
        if scenario["expected_reconciled"] != EXPECTED_RECONCILED_BY_STATUS[
            scenario["expected_status"]
        ]:
            raise ValueError(
                f"{scenario['order_id']}: expected_reconciled inconsistent with expected_status"
            )
        if scenario["evaluation_grain"] != EVALUATION_GRAIN:
            raise ValueError(f"{scenario['order_id']}: incorrect evaluation_grain")

        if scenario["scenario_type"] in (
            "exact_match",
            "timestamp_within_tolerance",
            "timestamp_outside_tolerance",
            "settlement_amount_mismatch",
            "refund_adjusted",
            "refund_unadjusted_mismatch",
            "reference_variation",
            "duplicate_settlement",
        ):
            if scenario["primary_settlement_id"] is None:
                raise ValueError(
                    f"{scenario['order_id']}: expected primary_settlement_id"
                )

        if scenario["scenario_type"] in (
            "exact_match",
            "timestamp_within_tolerance",
            "timestamp_outside_tolerance",
            "settlement_amount_mismatch",
            "refund_adjusted",
            "refund_unadjusted_mismatch",
            "reference_variation",
            "duplicate_settlement",
        ):
            if scenario["primary_bank_transaction_id"] is None:
                raise ValueError(
                    f"{scenario['order_id']}: expected primary_bank_transaction_id"
                )

        if scenario["scenario_type"] == "exact_match":
            if len(scenario["valid_bank_transaction_ids"]) != 1:
                raise ValueError(
                    f"{scenario['order_id']}: exact_match must have exactly one valid bank tx"
                )

        if scenario["order_id"] == order_id_for_index(50):
            if scenario["valid_bank_transaction_ids"] != ["BNK_0041"]:
                raise ValueError("ORD_0050 must have only BNK_0041 as valid bank tx")
            dup_ids = {
                r["bank_transaction_id"]
                for r in ground_truth["special_records"]["duplicate_bank_transactions"]
            }
            if "BNK_0050" not in dup_ids:
                raise ValueError("BNK_0050 must be classified as erroneous duplicate")

    _validate_ground_truth_bank_linkage(
        ground_truth["scenarios"], bank_df, settlements_df
    )

    if not ground_truth["special_records"]["orphan_bank_transactions"]:
        raise ValueError("Expected orphan bank transactions for missing settlement cases")
    if not ground_truth["special_records"]["duplicate_bank_transactions"]:
        raise ValueError("Expected duplicate bank transaction records")
    if not ground_truth["special_records"]["duplicate_settlements"]:
        raise ValueError("Expected duplicate settlement records")

    messages.append("Record counts validated")
    messages.append("Required columns validated")
    messages.append("Unique IDs validated")
    messages.append("Foreign-key relationships validated")
    messages.append("Positive monetary values validated")
    messages.append("Refund amount bounds validated")
    messages.append("Settlement net amount calculations validated")
    messages.append("Settlement timestamps after order creation validated")
    messages.append("Deterministic order generation validated")
    messages.append("All required mismatch scenarios present")
    messages.append("Ground-truth schema and vocabulary validated")
    messages.append("Ground-truth bank linkage validated")
    messages.append("Special records validated")

    return messages


# ---------------------------------------------------------
# Persistence
# ---------------------------------------------------------


def write_csv_outputs(
    orders_df: pd.DataFrame,
    settlements_df: pd.DataFrame,
    refunds_df: pd.DataFrame,
    bank_df: pd.DataFrame,
) -> None:
    """Write production-style CSV inputs to the data directory."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    orders_df.to_csv(DATA_DIR / "orders.csv", index=False)
    settlements_df.to_csv(DATA_DIR / "settlements.csv", index=False)
    refunds_df.to_csv(DATA_DIR / "refunds.csv", index=False)
    bank_df.to_csv(DATA_DIR / "bank.csv", index=False)


def write_ground_truth(ground_truth: dict[str, Any]) -> None:
    """Write ground-truth metadata for offline evaluation."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with GROUND_TRUTH_PATH.open("w", encoding="utf-8") as handle:
        json.dump(ground_truth, handle, indent=2)
        handle.write("\n")


# ---------------------------------------------------------
# Entry Point
# ---------------------------------------------------------


def main() -> None:
    """Generate datasets, apply scenarios, persist CSVs, and validate."""
    reset_random_state()

    orders_df = generate_orders()
    settlements_df = generate_settlements(orders_df)
    refunds_df = generate_refunds(orders_df)
    bank_df = generate_bank_transactions(settlements_df, orders_df)
    ground_truth = build_ground_truth(
        orders_df, settlements_df, refunds_df, bank_df
    )

    write_csv_outputs(orders_df, settlements_df, refunds_df, bank_df)
    write_ground_truth(ground_truth)
    validation_messages = validate_dataset(
        orders_df, settlements_df, refunds_df, bank_df, ground_truth
    )

    print("ReconEngine synthetic data generation complete")
    print(f"  orders:       {len(orders_df)}")
    print(f"  settlements:  {len(settlements_df)}")
    print(f"  refunds:      {len(refunds_df)}")
    print(f"  bank:         {len(bank_df)}")
    print(f"  ground truth: {GROUND_TRUTH_PATH}")
    print(f"  evaluation grain: {EVALUATION_GRAIN}")
    print()
    print("Scenario distribution:")
    for scenario, count in sorted(ground_truth["scenario_counts"].items()):
        print(f"  {scenario}: {count}")
    print()
    print("Expected status distribution:")
    for status, count in sorted(ground_truth["expected_status_counts"].items()):
        print(f"  {status}: {count}")
    print()
    print("Validation:")
    for message in validation_messages:
        print(f"  [OK] {message}")


if __name__ == "__main__":
    main()
