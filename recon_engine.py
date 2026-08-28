"""Deterministic financial reconciliation engine for ReconEngine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

DEFAULT_TIMESTAMP_TOLERANCE_HOURS = 24

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORT_PATH = DATA_DIR / "report.json"

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

RECONCILIATION_STATUSES: frozenset[str] = frozenset(
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

EXCEPTION_TYPES: frozenset[str] = frozenset(
    {
        "MISSING_SETTLEMENT",
        "MISSING_BANK_TRANSACTION",
        "SETTLEMENT_AMOUNT_MISMATCH",
        "BANK_AMOUNT_MISMATCH",
        "TIMESTAMP_OUTSIDE_TOLERANCE",
        "TIMESTAMP_WITHIN_TOLERANCE",
        "REFUND_NOT_REFLECTED",
        "REFUND_ADJUSTED",
        "DUPLICATE_SETTLEMENT",
        "DUPLICATE_BANK_TRANSACTION",
        "ORPHAN_BANK_TRANSACTION",
        "REFERENCE_VARIATION",
    }
)


# ---------------------------------------------------------
# Data structures
# ---------------------------------------------------------


@dataclass
class NormalizedOrder:
    order_id: str
    amount_paise: int
    created_at: datetime


@dataclass
class NormalizedSettlement:
    settlement_id: str
    order_id: str
    gross_amount_paise: int
    fee_paise: int
    tax_paise: int
    net_amount_paise: int
    settled_at: datetime


@dataclass
class NormalizedRefund:
    refund_id: str
    order_id: str
    refund_amount_paise: int
    created_at: datetime


@dataclass
class NormalizedBankTransaction:
    bank_transaction_id: str
    settlement_ref: str
    amount_paise: int
    transaction_date: datetime
    description: str
    ref_category: str
    resolved_settlement_id: str | None


@dataclass
class AmountComparison:
    order_amount_paise: int
    settlement_gross_paise: int | None
    settlement_net_paise: int | None
    bank_amount_paise: int | None
    expected_post_refund_gross_paise: int | None
    total_refund_paise: int
    settlement_gross_matches_order: bool | None
    settlement_reflects_refund: bool | None
    bank_matches_settlement_net: bool | None


@dataclass
class TimestampComparison:
    settlement_settled_at: str | None
    bank_transaction_date: str | None
    difference_hours: float | None
    tolerance_hours: int
    within_tolerance: bool | None


@dataclass
class OrderReconciliationResult:
    order_id: str
    status: str
    reconciled: bool
    confidence_score: int
    order_amount_paise: int
    settlement_ids_considered: list[str] = field(default_factory=list)
    primary_settlement_id: str | None = None
    secondary_settlement_ids: list[str] = field(default_factory=list)
    refund_ids: list[str] = field(default_factory=list)
    total_refund_paise: int = 0
    bank_transaction_ids_considered: list[str] = field(default_factory=list)
    valid_bank_transaction_id: str | None = None
    normalized_references: dict[str, str] = field(default_factory=dict)
    amount_comparison: dict[str, Any] = field(default_factory=dict)
    timestamp_comparison: dict[str, Any] = field(default_factory=dict)
    rules_triggered: list[str] = field(default_factory=list)
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    audit_trail: list[str] = field(default_factory=list)


# ---------------------------------------------------------
# Loading
# ---------------------------------------------------------


def load_data(data_dir: Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    """Load production CSV inputs from the data directory."""
    paths = {
        "orders": data_dir / "orders.csv",
        "settlements": data_dir / "settlements.csv",
        "refunds": data_dir / "refunds.csv",
        "bank": data_dir / "bank.csv",
    }
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required CSV files: {', '.join(missing)}")

    return {name: pd.read_csv(path) for name, path in paths.items()}


# ---------------------------------------------------------
# Normalization
# ---------------------------------------------------------


def normalize_id(value: str) -> str:
    """Normalize identifier strings."""
    return str(value).strip()


def normalize_amount(value: Any, field_name: str) -> int:
    """Normalize monetary values to integer paise."""
    try:
        amount = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid monetary value for {field_name}: {value!r}") from exc
    if amount <= 0:
        raise ValueError(f"Monetary value must be positive for {field_name}: {amount}")
    return amount


def normalize_timestamp(value: Any, field_name: str) -> datetime:
    """Parse and validate ISO timestamps."""
    try:
        return datetime.fromisoformat(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Malformed timestamp for {field_name}: {value!r}") from exc


def classify_settlement_ref(settlement_ref: str) -> str:
    """Classify a bank settlement_ref by prefix pattern."""
    if settlement_ref.startswith("ORPHAN-"):
        return "orphan"
    if settlement_ref.startswith("DUP-"):
        return "duplicate"
    if settlement_ref.startswith("STL-"):
        return "reference_variation"
    if settlement_ref.startswith("SET_"):
        return "canonical"
    return "unknown"


def normalize_settlement_ref(
    settlement_ref: str,
    valid_settlement_ids: set[str],
) -> str | None:
    """Resolve a bank settlement_ref to a canonical settlement_id."""
    ref = normalize_id(settlement_ref)
    category = classify_settlement_ref(ref)

    if category in ("orphan", "duplicate"):
        return None
    if category == "canonical" and ref in valid_settlement_ids:
        return ref
    if category == "reference_variation":
        canonical = ref.replace("STL-", "SET_", 1)
        if canonical in valid_settlement_ids:
            return canonical
    return None


def normalize_orders(df: pd.DataFrame) -> list[NormalizedOrder]:
    """Normalize order records."""
    return [
        NormalizedOrder(
            order_id=normalize_id(row["order_id"]),
            amount_paise=normalize_amount(row["amount"], "order.amount"),
            created_at=normalize_timestamp(row["created_at"], "order.created_at"),
        )
        for _, row in df.iterrows()
    ]


def normalize_settlements(df: pd.DataFrame) -> list[NormalizedSettlement]:
    """Normalize settlement records."""
    return [
        NormalizedSettlement(
            settlement_id=normalize_id(row["settlement_id"]),
            order_id=normalize_id(row["order_id"]),
            gross_amount_paise=normalize_amount(row["gross_amount"], "settlement.gross_amount"),
            fee_paise=normalize_amount(row["fee"], "settlement.fee"),
            tax_paise=normalize_amount(row["tax"], "settlement.tax"),
            net_amount_paise=normalize_amount(row["net_amount"], "settlement.net_amount"),
            settled_at=normalize_timestamp(row["settled_at"], "settlement.settled_at"),
        )
        for _, row in df.iterrows()
    ]


def normalize_refunds(df: pd.DataFrame) -> list[NormalizedRefund]:
    """Normalize refund records."""
    return [
        NormalizedRefund(
            refund_id=normalize_id(row["refund_id"]),
            order_id=normalize_id(row["order_id"]),
            refund_amount_paise=normalize_amount(row["refund_amount"], "refund.refund_amount"),
            created_at=normalize_timestamp(row["created_at"], "refund.created_at"),
        )
        for _, row in df.iterrows()
    ]


def normalize_bank_transactions(
    df: pd.DataFrame,
    valid_settlement_ids: set[str],
) -> list[NormalizedBankTransaction]:
    """Normalize bank transaction records with reference resolution."""
    records: list[NormalizedBankTransaction] = []
    for _, row in df.iterrows():
        settlement_ref = normalize_id(row["settlement_ref"])
        category = classify_settlement_ref(settlement_ref)
        records.append(
            NormalizedBankTransaction(
                bank_transaction_id=normalize_id(row["bank_transaction_id"]),
                settlement_ref=settlement_ref,
                amount_paise=normalize_amount(row["amount"], "bank.amount"),
                transaction_date=normalize_timestamp(
                    row["transaction_date"], "bank.transaction_date"
                ),
                description=str(row["description"]),
                ref_category=category,
                resolved_settlement_id=normalize_settlement_ref(
                    settlement_ref, valid_settlement_ids
                ),
            )
        )
    return records


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


def validate_inputs(raw_data: dict[str, pd.DataFrame]) -> None:
    """Validate loaded CSV structure and basic integrity."""
    _validate_columns(raw_data["orders"], ORDERS_COLUMNS, "orders")
    _validate_columns(raw_data["settlements"], SETTLEMENTS_COLUMNS, "settlements")
    _validate_columns(raw_data["refunds"], REFUNDS_COLUMNS, "refunds")
    _validate_columns(raw_data["bank"], BANK_COLUMNS, "bank")

    _validate_unique_ids(raw_data["orders"], "order_id", "order")
    _validate_unique_ids(raw_data["settlements"], "settlement_id", "settlement")
    _validate_unique_ids(raw_data["refunds"], "refund_id", "refund")
    _validate_unique_ids(raw_data["bank"], "bank_transaction_id", "bank transaction")

    order_ids = set(raw_data["orders"]["order_id"])
    if not set(raw_data["settlements"]["order_id"]).issubset(order_ids):
        raise ValueError("Settlement references unknown order_id")
    if not set(raw_data["refunds"]["order_id"]).issubset(order_ids):
        raise ValueError("Refund references unknown order_id")


# ---------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------


def build_bank_index(
    bank_transactions: list[NormalizedBankTransaction],
) -> dict[str, list[NormalizedBankTransaction]]:
    """Index valid bank transactions by resolved settlement_id."""
    index: dict[str, list[NormalizedBankTransaction]] = {}
    for bank_tx in bank_transactions:
        if bank_tx.resolved_settlement_id is None:
            continue
        index.setdefault(bank_tx.resolved_settlement_id, []).append(bank_tx)
    for settlement_id in index:
        index[settlement_id].sort(key=lambda tx: tx.bank_transaction_id)
    return index


def build_duplicate_bank_index(
    bank_transactions: list[NormalizedBankTransaction],
) -> dict[str, list[NormalizedBankTransaction]]:
    """Index duplicate (DUP-*) bank transactions by extracted settlement suffix."""
    index: dict[str, list[NormalizedBankTransaction]] = {}
    for bank_tx in bank_transactions:
        if bank_tx.ref_category != "duplicate":
            continue
        source_settlement = bank_tx.settlement_ref.replace("DUP-", "", 1)
        index.setdefault(source_settlement, []).append(bank_tx)
    return index


# ---------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------


def match_settlements_for_order(
    order_id: str,
    settlements: list[NormalizedSettlement],
) -> tuple[NormalizedSettlement | None, list[NormalizedSettlement]]:
    """Return primary settlement and secondary settlements for an order."""
    order_settlements = sorted(
        [s for s in settlements if s.order_id == order_id],
        key=lambda s: (s.settled_at, s.settlement_id),
    )
    if not order_settlements:
        return None, []
    return order_settlements[0], order_settlements[1:]


def match_bank_for_settlement(
    settlement_id: str,
    bank_index: dict[str, list[NormalizedBankTransaction]],
) -> NormalizedBankTransaction | None:
    """Select the canonical valid bank transaction for a settlement."""
    candidates = bank_index.get(settlement_id, [])
    if not candidates:
        return None
    if len(candidates) > 1:
        # Prefer canonical SET_ ref over STL- when multiple valid links exist.
        canonical = [tx for tx in candidates if tx.ref_category == "canonical"]
        if canonical:
            return canonical[0]
    return candidates[0]


def calculate_refund_totals(
    order_id: str,
    refunds: list[NormalizedRefund],
) -> tuple[list[str], int]:
    """Return refund IDs and total refund amount for an order."""
    order_refunds = sorted(
        [r for r in refunds if r.order_id == order_id],
        key=lambda r: r.refund_id,
    )
    refund_ids = [r.refund_id for r in order_refunds]
    total = sum(r.refund_amount_paise for r in order_refunds)
    return refund_ids, total


def compare_amounts(
    order: NormalizedOrder,
    primary: NormalizedSettlement | None,
    bank: NormalizedBankTransaction | None,
    total_refund_paise: int,
) -> AmountComparison:
    """Build structured amount comparison for audit trail."""
    expected_post_refund = order.amount_paise - total_refund_paise if total_refund_paise else None
    settlement_gross = primary.gross_amount_paise if primary else None
    settlement_net = primary.net_amount_paise if primary else None
    bank_amount = bank.amount_paise if bank else None

    settlement_gross_matches_order = (
        settlement_gross == order.amount_paise if settlement_gross is not None else None
    )
    settlement_reflects_refund = None
    if primary is not None and total_refund_paise > 0 and expected_post_refund is not None:
        settlement_reflects_refund = settlement_gross == expected_post_refund
    bank_matches_settlement_net = (
        bank_amount == settlement_net
        if bank_amount is not None and settlement_net is not None
        else None
    )

    return AmountComparison(
        order_amount_paise=order.amount_paise,
        settlement_gross_paise=settlement_gross,
        settlement_net_paise=settlement_net,
        bank_amount_paise=bank_amount,
        expected_post_refund_gross_paise=expected_post_refund,
        total_refund_paise=total_refund_paise,
        settlement_gross_matches_order=settlement_gross_matches_order,
        settlement_reflects_refund=settlement_reflects_refund,
        bank_matches_settlement_net=bank_matches_settlement_net,
    )


def compare_timestamps(
    primary: NormalizedSettlement | None,
    bank: NormalizedBankTransaction | None,
    tolerance_hours: int,
) -> TimestampComparison:
    """Compare settlement and bank timestamps."""
    if primary is None or bank is None:
        return TimestampComparison(
            settlement_settled_at=primary.settled_at.isoformat() if primary else None,
            bank_transaction_date=bank.transaction_date.isoformat() if bank else None,
            difference_hours=None,
            tolerance_hours=tolerance_hours,
            within_tolerance=None,
        )

    diff_seconds = abs((bank.transaction_date - primary.settled_at).total_seconds())
    diff_hours = diff_seconds / 3600
    return TimestampComparison(
        settlement_settled_at=primary.settled_at.isoformat(),
        bank_transaction_date=bank.transaction_date.isoformat(),
        difference_hours=round(diff_hours, 2),
        tolerance_hours=tolerance_hours,
        within_tolerance=diff_hours <= tolerance_hours,
    )


# ---------------------------------------------------------
# Exception generation
# ---------------------------------------------------------


def add_exception(
    exceptions: list[dict[str, Any]],
    exception_type: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an exception if not already present for the same type."""
    if exception_type not in EXCEPTION_TYPES:
        raise ValueError(f"Unsupported exception type: {exception_type}")
    existing = {exc["type"] for exc in exceptions}
    if exception_type in existing:
        return
    entry: dict[str, Any] = {"type": exception_type, "message": message}
    if details:
        entry["details"] = details
    exceptions.append(entry)


# ---------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------


def calculate_confidence(
    exceptions: list[dict[str, Any]],
    amount_comparison: AmountComparison,
    timestamp_comparison: TimestampComparison,
    has_valid_bank: bool,
    has_primary_settlement: bool,
) -> int:
    """Compute deterministic confidence score from observable evidence.

    Scoring model (starts at 100, deducts for issues):
    - Missing settlement: -100
    - Missing bank: -35
    - Settlement amount mismatch: -30
    - Bank amount mismatch: -25
    - Refund not reflected: -20
    - Timestamp outside tolerance: -15
    - Duplicate settlement: -10
    - Duplicate bank present: -5
    - Reference variation (non-blocking): -5
    Bonus for clean timestamp within tolerance with non-zero diff: +0 (already 100)
    """
    score = 100
    exception_types = {exc["type"] for exc in exceptions}

    penalties = {
        "MISSING_SETTLEMENT": 100,
        "MISSING_BANK_TRANSACTION": 35,
        "SETTLEMENT_AMOUNT_MISMATCH": 30,
        "BANK_AMOUNT_MISMATCH": 25,
        "REFUND_NOT_REFLECTED": 20,
        "TIMESTAMP_OUTSIDE_TOLERANCE": 15,
        "DUPLICATE_SETTLEMENT": 10,
        "DUPLICATE_BANK_TRANSACTION": 5,
        "REFERENCE_VARIATION": 5,
    }
    for exc_type, penalty in penalties.items():
        if exc_type in exception_types:
            score -= penalty

    if not has_primary_settlement:
        score = min(score, 0)
    if has_primary_settlement and not has_valid_bank:
        score = min(score, 40)

    return max(0, min(100, score))


# ---------------------------------------------------------
# Reconciliation decision
# ---------------------------------------------------------


def determine_status(
    exceptions: list[dict[str, Any]],
    amount_comparison: AmountComparison,
    timestamp_comparison: TimestampComparison,
    used_reference_variation: bool,
    has_secondary_settlements: bool,
) -> tuple[str, bool]:
    """Determine final reconciliation status and reconciled flag."""
    exception_types = {exc["type"] for exc in exceptions}

    if "MISSING_SETTLEMENT" in exception_types:
        return "unreconciled_missing_settlement", False
    if "MISSING_BANK_TRANSACTION" in exception_types:
        return "unreconciled_missing_bank", False
    if has_secondary_settlements or "DUPLICATE_SETTLEMENT" in exception_types:
        if any(
            exc in exception_types
            for exc in (
                "SETTLEMENT_AMOUNT_MISMATCH",
                "BANK_AMOUNT_MISMATCH",
                "REFUND_NOT_REFLECTED",
                "TIMESTAMP_OUTSIDE_TOLERANCE",
                "MISSING_BANK_TRANSACTION",
            )
        ):
            return "partially_reconciled_duplicate_settlement", False
        # Primary chain may be clean but secondary settlement unresolved.
        if "DUPLICATE_SETTLEMENT" in exception_types:
            return "partially_reconciled_duplicate_settlement", False
    if "REFUND_NOT_REFLECTED" in exception_types:
        return "unreconciled_refund_not_adjusted", False
    if "SETTLEMENT_AMOUNT_MISMATCH" in exception_types:
        return "unreconciled_settlement_amount", False
    if "BANK_AMOUNT_MISMATCH" in exception_types:
        return "unreconciled_settlement_amount", False
    if "TIMESTAMP_OUTSIDE_TOLERANCE" in exception_types:
        return "unreconciled_timestamp_exceeded", False

    if amount_comparison.settlement_reflects_refund is True:
        if used_reference_variation:
            return "reconciled_with_reference_variation", True
        return "reconciled_with_refund_adjustment", True

    if used_reference_variation:
        return "reconciled_with_reference_variation", True

    if (
        timestamp_comparison.difference_hours is not None
        and timestamp_comparison.difference_hours > 0
        and timestamp_comparison.within_tolerance
    ):
        return "reconciled_within_timestamp_tolerance", True

    return "reconciled", True


def reconcile_order(
    order: NormalizedOrder,
    settlements: list[NormalizedSettlement],
    refunds: list[NormalizedRefund],
    bank_index: dict[str, list[NormalizedBankTransaction]],
    duplicate_bank_index: dict[str, list[NormalizedBankTransaction]],
    tolerance_hours: int = DEFAULT_TIMESTAMP_TOLERANCE_HOURS,
) -> OrderReconciliationResult:
    """Reconcile a single order through the full rule pipeline."""
    exceptions: list[dict[str, Any]] = []
    rules_triggered: list[str] = []
    audit_trail: list[str] = []

    refund_ids, total_refund_paise = calculate_refund_totals(order.order_id, refunds)
    primary, secondary = match_settlements_for_order(order.order_id, settlements)
    settlement_ids = ([primary.settlement_id] if primary else []) + [
        s.settlement_id for s in secondary
    ]

    audit_trail.append(f"Evaluating order {order.order_id} amount={order.amount_paise} paise.")

    # RULE 1 — ORDER → SETTLEMENT
    rules_triggered.append("RULE_1_ORDER_TO_SETTLEMENT")
    if primary is None:
        add_exception(
            exceptions,
            "MISSING_SETTLEMENT",
            f"No settlement found for order {order.order_id}.",
        )
        audit_trail.append("No settlements reference this order.")
        amount_comparison = compare_amounts(order, None, None, total_refund_paise)
        timestamp_comparison = compare_timestamps(None, None, tolerance_hours)
        status, reconciled = determine_status(exceptions, amount_comparison, timestamp_comparison, False, False)
        confidence = calculate_confidence(exceptions, amount_comparison, timestamp_comparison, False, False)
        return OrderReconciliationResult(
            order_id=order.order_id,
            status=status,
            reconciled=reconciled,
            confidence_score=confidence,
            order_amount_paise=order.amount_paise,
            settlement_ids_considered=settlement_ids,
            refund_ids=refund_ids,
            total_refund_paise=total_refund_paise,
            amount_comparison=amount_comparison.__dict__,
            timestamp_comparison=timestamp_comparison.__dict__,
            rules_triggered=rules_triggered,
            exceptions=exceptions,
            audit_trail=audit_trail,
        )

    audit_trail.append(
        f"Primary settlement {primary.settlement_id} gross={primary.gross_amount_paise} paise."
    )
    if secondary:
        add_exception(
            exceptions,
            "DUPLICATE_SETTLEMENT",
            f"Multiple settlements found; primary={primary.settlement_id}, "
            f"secondary={[s.settlement_id for s in secondary]}.",
            details={
                "primary_settlement_id": primary.settlement_id,
                "secondary_settlement_ids": [s.settlement_id for s in secondary],
            },
        )
        audit_trail.append(
            f"Secondary settlements present: {[s.settlement_id for s in secondary]}."
        )

    # Amount / refund checks on primary settlement
    if total_refund_paise > 0:
        rules_triggered.append("RULE_3_REFUND_ADJUSTMENT")
        expected_post_refund = order.amount_paise - total_refund_paise
        if primary.gross_amount_paise == expected_post_refund:
            add_exception(
                exceptions,
                "REFUND_ADJUSTED",
                "Settlement gross reflects refund deduction.",
                details={"total_refund_paise": total_refund_paise},
            )
            audit_trail.append(
                f"Refund adjusted: gross {primary.gross_amount_paise} == "
                f"order {order.amount_paise} - refund {total_refund_paise}."
            )
        elif primary.gross_amount_paise == order.amount_paise:
            add_exception(
                exceptions,
                "REFUND_NOT_REFLECTED",
                "Refund exists but settlement gross was not adjusted.",
                details={
                    "total_refund_paise": total_refund_paise,
                    "settlement_gross_paise": primary.gross_amount_paise,
                    "expected_post_refund_gross_paise": expected_post_refund,
                },
            )
            audit_trail.append("Refund not reflected in settlement gross.")
        else:
            add_exception(
                exceptions,
                "SETTLEMENT_AMOUNT_MISMATCH",
                "Settlement gross does not match order amount or post-refund expectation.",
                details={
                    "order_amount_paise": order.amount_paise,
                    "settlement_gross_paise": primary.gross_amount_paise,
                    "expected_post_refund_gross_paise": expected_post_refund,
                },
            )
    elif primary.gross_amount_paise != order.amount_paise:
        add_exception(
            exceptions,
            "SETTLEMENT_AMOUNT_MISMATCH",
            "Settlement gross differs from order amount.",
            details={
                "order_amount_paise": order.amount_paise,
                "settlement_gross_paise": primary.gross_amount_paise,
                "delta_paise": primary.gross_amount_paise - order.amount_paise,
            },
        )
        audit_trail.append(
            f"Settlement gross mismatch: {primary.gross_amount_paise} != {order.amount_paise}."
        )

    # RULE 2 — SETTLEMENT → BANK
    rules_triggered.append("RULE_2_SETTLEMENT_TO_BANK")
    valid_bank = match_bank_for_settlement(primary.settlement_id, bank_index)
    bank_ids_considered = [
        tx.bank_transaction_id
        for tx in bank_index.get(primary.settlement_id, [])
    ]
    normalized_references: dict[str, str] = {}

    dup_banks = duplicate_bank_index.get(primary.settlement_id, [])
    if dup_banks:
        add_exception(
            exceptions,
            "DUPLICATE_BANK_TRANSACTION",
            f"Erroneous duplicate bank transaction(s) for settlement {primary.settlement_id}.",
            details={
                "bank_transaction_ids": [tx.bank_transaction_id for tx in dup_banks],
                "settlement_refs": [tx.settlement_ref for tx in dup_banks],
            },
        )
        audit_trail.append(
            f"Duplicate bank transactions detected: {[tx.bank_transaction_id for tx in dup_banks]}."
        )

    used_reference_variation = False
    if valid_bank is None:
        add_exception(
            exceptions,
            "MISSING_BANK_TRANSACTION",
            f"No valid bank transaction resolves to settlement {primary.settlement_id}.",
        )
        audit_trail.append("No valid bank transaction found via settlement_ref.")
    else:
        normalized_references[valid_bank.settlement_ref] = primary.settlement_id
        if valid_bank.ref_category == "reference_variation":
            used_reference_variation = True
            add_exception(
                exceptions,
                "REFERENCE_VARIATION",
                f"Bank ref {valid_bank.settlement_ref} normalizes to {primary.settlement_id}.",
                details={
                    "bank_settlement_ref": valid_bank.settlement_ref,
                    "normalized_settlement_id": primary.settlement_id,
                },
            )
            audit_trail.append(
                f"Reference variation: {valid_bank.settlement_ref} -> {primary.settlement_id}."
            )
        if valid_bank.amount_paise != primary.net_amount_paise:
            add_exception(
                exceptions,
                "BANK_AMOUNT_MISMATCH",
                "Bank amount differs from settlement net amount.",
                details={
                    "settlement_net_paise": primary.net_amount_paise,
                    "bank_amount_paise": valid_bank.amount_paise,
                    "delta_paise": valid_bank.amount_paise - primary.net_amount_paise,
                },
            )
            audit_trail.append(
                f"Bank amount mismatch: bank {valid_bank.amount_paise} != "
                f"net {primary.net_amount_paise}."
            )

        ts = compare_timestamps(primary, valid_bank, tolerance_hours)
        if ts.within_tolerance is False:
            add_exception(
                exceptions,
                "TIMESTAMP_OUTSIDE_TOLERANCE",
                f"Timestamp difference {ts.difference_hours}h exceeds {tolerance_hours}h.",
                details=ts.__dict__,
            )
            audit_trail.append(
                f"Timestamp outside tolerance: {ts.difference_hours}h > {tolerance_hours}h."
            )
        elif ts.difference_hours and ts.difference_hours > 0:
            add_exception(
                exceptions,
                "TIMESTAMP_WITHIN_TOLERANCE",
                f"Timestamp difference {ts.difference_hours}h within {tolerance_hours}h.",
                details=ts.__dict__,
            )

    amount_comparison = compare_amounts(order, primary, valid_bank, total_refund_paise)
    timestamp_comparison = compare_timestamps(primary, valid_bank, tolerance_hours)

    status, reconciled = determine_status(
        exceptions,
        amount_comparison,
        timestamp_comparison,
        used_reference_variation,
        bool(secondary),
    )
    confidence = calculate_confidence(
        exceptions,
        amount_comparison,
        timestamp_comparison,
        valid_bank is not None,
        primary is not None,
    )

    if reconciled:
        audit_trail.append(f"Order reconciled with status={status}.")
    else:
        audit_trail.append(f"Order not reconciled; status={status}.")

    return OrderReconciliationResult(
        order_id=order.order_id,
        status=status,
        reconciled=reconciled,
        confidence_score=confidence,
        order_amount_paise=order.amount_paise,
        settlement_ids_considered=settlement_ids,
        primary_settlement_id=primary.settlement_id,
        secondary_settlement_ids=[s.settlement_id for s in secondary],
        refund_ids=refund_ids,
        total_refund_paise=total_refund_paise,
        bank_transaction_ids_considered=bank_ids_considered,
        valid_bank_transaction_id=valid_bank.bank_transaction_id if valid_bank else None,
        normalized_references=normalized_references,
        amount_comparison=amount_comparison.__dict__,
        timestamp_comparison=timestamp_comparison.__dict__,
        rules_triggered=rules_triggered,
        exceptions=exceptions,
        audit_trail=audit_trail,
    )


# ---------------------------------------------------------
# Global exception scan
# ---------------------------------------------------------


def collect_global_exceptions(
    bank_transactions: list[NormalizedBankTransaction],
    settlements: list[NormalizedSettlement],
    bank_index: dict[str, list[NormalizedBankTransaction]],
) -> list[dict[str, Any]]:
    """Collect orphan banks and unmatched settlements not tied to order results."""
    records: list[dict[str, Any]] = []

    for bank_tx in bank_transactions:
        if bank_tx.ref_category == "orphan":
            related_order = bank_tx.settlement_ref.replace("ORPHAN-", "", 1)
            records.append(
                {
                    "type": "ORPHAN_BANK_TRANSACTION",
                    "bank_transaction_id": bank_tx.bank_transaction_id,
                    "settlement_ref": bank_tx.settlement_ref,
                    "related_order_id": related_order,
                    "amount_paise": bank_tx.amount_paise,
                    "message": "Bank transaction with no resolvable settlement.",
                }
            )
        elif bank_tx.ref_category == "duplicate":
            source_settlement = bank_tx.settlement_ref.replace("DUP-", "", 1)
            records.append(
                {
                    "type": "DUPLICATE_BANK_TRANSACTION",
                    "bank_transaction_id": bank_tx.bank_transaction_id,
                    "settlement_ref": bank_tx.settlement_ref,
                    "source_settlement_id": source_settlement,
                    "amount_paise": bank_tx.amount_paise,
                    "is_valid_bank_link": False,
                    "message": "Erroneous duplicate bank transaction.",
                }
            )

    for settlement in settlements:
        if settlement.settlement_id not in bank_index:
            records.append(
                {
                    "type": "MISSING_BANK_TRANSACTION",
                    "settlement_id": settlement.settlement_id,
                    "order_id": settlement.order_id,
                    "message": "Settlement has no valid bank transaction via settlement_ref.",
                }
            )

    return records


# ---------------------------------------------------------
# Reconciliation orchestration
# ---------------------------------------------------------


def reconcile_all(
    orders: list[NormalizedOrder],
    settlements: list[NormalizedSettlement],
    refunds: list[NormalizedRefund],
    bank_transactions: list[NormalizedBankTransaction],
    tolerance_hours: int = DEFAULT_TIMESTAMP_TOLERANCE_HOURS,
) -> tuple[list[OrderReconciliationResult], list[dict[str, Any]]]:
    """Reconcile all orders and collect global exceptions."""
    valid_settlement_ids = {s.settlement_id for s in settlements}
    bank_index = build_bank_index(bank_transactions)
    duplicate_bank_index = build_duplicate_bank_index(bank_transactions)

    results = [
        reconcile_order(
            order,
            settlements,
            refunds,
            bank_index,
            duplicate_bank_index,
            tolerance_hours,
        )
        for order in sorted(orders, key=lambda o: o.order_id)
    ]
    global_exceptions = collect_global_exceptions(
        bank_transactions, settlements, bank_index
    )
    return results, global_exceptions


# ---------------------------------------------------------
# Report generation
# ---------------------------------------------------------


def build_summary(
    order_results: list[OrderReconciliationResult],
    global_exceptions: list[dict[str, Any]],
) -> dict[str, int]:
    """Build aggregate summary counts."""
    exception_types = [
        exc["type"]
        for result in order_results
        for exc in result.exceptions
    ]
    global_types = [exc["type"] for exc in global_exceptions]

    return {
        "total_orders": len(order_results),
        "reconciled_orders": sum(1 for r in order_results if r.reconciled),
        "unreconciled_orders": sum(1 for r in order_results if not r.reconciled),
        "missing_settlements": exception_types.count("MISSING_SETTLEMENT"),
        "missing_bank_transactions": exception_types.count("MISSING_BANK_TRANSACTION"),
        "settlement_amount_mismatches": exception_types.count("SETTLEMENT_AMOUNT_MISMATCH"),
        "bank_amount_mismatches": exception_types.count("BANK_AMOUNT_MISMATCH"),
        "timestamp_violations": exception_types.count("TIMESTAMP_OUTSIDE_TOLERANCE"),
        "refund_mismatches": exception_types.count("REFUND_NOT_REFLECTED"),
        "refund_adjusted": exception_types.count("REFUND_ADJUSTED"),
        "duplicate_settlements": exception_types.count("DUPLICATE_SETTLEMENT"),
        "duplicate_bank_transactions": global_types.count("DUPLICATE_BANK_TRANSACTION"),
        "orphan_bank_transactions": global_types.count("ORPHAN_BANK_TRANSACTION"),
        "reference_variations": exception_types.count("REFERENCE_VARIATION"),
    }


def _deterministic_report_timestamp(
    orders: list[NormalizedOrder],
    settlements: list[NormalizedSettlement],
    bank_transactions: list[NormalizedBankTransaction],
) -> str:
    """Derive a stable report timestamp from input data (not wall clock)."""
    timestamps = (
        [o.created_at for o in orders]
        + [s.settled_at for s in settlements]
        + [b.transaction_date for b in bank_transactions]
    )
    return max(timestamps).isoformat()


def build_report(
    order_results: list[OrderReconciliationResult],
    global_exceptions: list[dict[str, Any]],
    *,
    report_timestamp: str,
    tolerance_hours: int = DEFAULT_TIMESTAMP_TOLERANCE_HOURS,
) -> dict[str, Any]:
    """Build the full reconciliation report."""
    summary = build_summary(order_results, global_exceptions)
    status_counts: dict[str, int] = {}
    for result in order_results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    return {
        "metadata": {
            "engine": "recon_engine",
            "generated_at": report_timestamp,
            "evaluation_grain": "order",
            "currency": "INR",
            "minor_unit": "paise",
        },
        "configuration": {
            "timestamp_tolerance_hours": tolerance_hours,
            "reference_normalization": {
                "STL-": "SET_",
                "ORPHAN-*": "unresolved",
                "DUP-*": "unresolved",
            },
            "reconciliation_status_vocabulary": sorted(RECONCILIATION_STATUSES),
            "exception_vocabulary": sorted(EXCEPTION_TYPES),
        },
        "summary": summary,
        "status_counts": dict(sorted(status_counts.items())),
        "order_results": [
            {
                "order_id": r.order_id,
                "status": r.status,
                "reconciled": r.reconciled,
                "confidence_score": r.confidence_score,
                "order_amount_paise": r.order_amount_paise,
                "settlement_ids_considered": r.settlement_ids_considered,
                "primary_settlement_id": r.primary_settlement_id,
                "secondary_settlement_ids": r.secondary_settlement_ids,
                "refund_ids": r.refund_ids,
                "total_refund_paise": r.total_refund_paise,
                "bank_transaction_ids_considered": r.bank_transaction_ids_considered,
                "valid_bank_transaction_id": r.valid_bank_transaction_id,
                "normalized_references": r.normalized_references,
                "amount_comparison": r.amount_comparison,
                "timestamp_comparison": r.timestamp_comparison,
                "rules_triggered": r.rules_triggered,
                "exceptions": r.exceptions,
                "audit_trail": r.audit_trail,
            }
            for r in order_results
        ],
        "global_exceptions": global_exceptions,
    }


def write_report(report: dict[str, Any], report_path: Path = REPORT_PATH) -> None:
    """Write reconciliation report to JSON."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")


# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------


def main() -> None:
    """Load CSVs, reconcile, validate, and write report.json."""
    raw_data = load_data()
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
    report = build_report(
        order_results,
        global_exceptions,
        report_timestamp=report_timestamp,
    )
    write_report(report)

    summary = report["summary"]
    print("ReconEngine reconciliation complete")
    print(f"  orders processed:  {summary['total_orders']}")
    print(f"  reconciled:        {summary['reconciled_orders']}")
    print(f"  unreconciled:      {summary['unreconciled_orders']}")
    print(f"  report:            {REPORT_PATH}")
    print()
    print("Status distribution:")
    for status, count in report["status_counts"].items():
        print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
