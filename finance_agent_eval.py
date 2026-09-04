"""Finance Controller held-out evaluation harness.

Observes ``finance_agent.decide_for_order`` / ``run_finance_controller``.
Does NOT reimplement decision policy and does NOT participate in decisions.

Labels live in ``data/finance_controller_eval_v1.json`` and were authored from the
Track 04 labeling guide (see dataset metadata) — not by copying agent output.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from finance_agent import (
    ALLOWED_DECISIONS,
    DECISION_ESCALATE_MISSING_BANK,
    DECISION_ESCALATE_MISSING_SETTLEMENT,
    DECISION_FLAG_FOR_REVIEW,
    DECISION_NO_ACTION,
    DECISION_VERIFY_REFUND,
    decide_for_order,
)

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
EVAL_DATASET_PATH = DATA_DIR / "finance_controller_eval_v1.json"
EVAL_OUTPUT_PATH = DATA_DIR / "finance_controller_evaluation.json"

DATASET_ID = "held_out_finance_controller_v1"

DECISION_LABELS: tuple[str, ...] = tuple(sorted(ALLOWED_DECISIONS))

# ---------------------------------------------------------------------------
# Labeling guide (human-authored rubric for expected decisions).
# This is the SOURCE OF TRUTH for labels in the held-out dataset.
# It is intentionally separate from finance_agent._policy_decide so that
# evaluation measures the agent against fixed labels, not against itself.
# ---------------------------------------------------------------------------

LABELING_GUIDE: dict[str, Any] = {
    "version": "1.0",
    "summary": (
        "Expected Finance Controller decisions for held-out synthetic order_results. "
        "Labels follow this priority rubric from Track 04 agent requirements — "
        "they were NOT produced by calling finance_agent.py."
    ),
    "priority": [
        {
            "when": "MISSING_SETTLEMENT in exceptions",
            "expected": DECISION_ESCALATE_MISSING_SETTLEMENT,
        },
        {
            "when": "MISSING_BANK_TRANSACTION in exceptions",
            "expected": DECISION_ESCALATE_MISSING_BANK,
        },
        {
            "when": "BANK_AMOUNT_MISMATCH or SETTLEMENT_AMOUNT_MISMATCH",
            "expected": DECISION_FLAG_FOR_REVIEW,
        },
        {
            "when": "REFUND_NOT_REFLECTED",
            "expected": DECISION_FLAG_FOR_REVIEW,
        },
        {
            "when": (
                "DUPLICATE_SETTLEMENT / DUPLICATE_BANK_TRANSACTION / "
                "ORPHAN_BANK_TRANSACTION / TIMESTAMP_OUTSIDE_TOLERANCE"
            ),
            "expected": DECISION_FLAG_FOR_REVIEW,
        },
        {
            "when": "REFUND_ADJUSTED (and no higher-priority blocking exception)",
            "expected": DECISION_VERIFY_REFUND,
        },
        {
            "when": (
                "reconciled=true and exceptions ⊆ "
                "{TIMESTAMP_WITHIN_TOLERANCE, REFERENCE_VARIATION, REFUND_ADJUSTED} "
                "with no REFUND_ADJUSTED already handled above, or empty exceptions"
            ),
            "expected": DECISION_NO_ACTION,
            "note": (
                "REFUND_ADJUSTED alone is VERIFY_REFUND (higher priority). "
                "Informational-only reconciled orders are NO_ACTION."
            ),
        },
        {
            "when": "Ambiguous, unreconciled without mapped exception, or unknown type",
            "expected": DECISION_FLAG_FOR_REVIEW,
        },
    ],
    "definitions": {
        "false_positive": (
            "For a decision class C: the agent predicted C when the labeled "
            "expected decision was not C."
        ),
        "false_negative": (
            "For a decision class C: the labeled expected decision was C but "
            "the agent predicted a different decision."
        ),
    },
}


def _minimal_order_result(
    *,
    order_id: str,
    status: str,
    reconciled: bool,
    confidence_score: int,
    exceptions: list[dict[str, str]],
    primary_settlement_id: str | None = "SET_EVAL_1",
    valid_bank_transaction_id: str | None = "BNK_EVAL_1",
    total_refund_paise: int = 0,
    rules_triggered: list[str] | None = None,
) -> dict[str, Any]:
    """Minimal engine-shaped order_result for held-out evaluation fixtures."""
    return {
        "order_id": order_id,
        "status": status,
        "reconciled": reconciled,
        "confidence_score": confidence_score,
        "order_amount_paise": 100_000,
        "settlement_ids_considered": [primary_settlement_id] if primary_settlement_id else [],
        "primary_settlement_id": primary_settlement_id,
        "secondary_settlement_ids": [],
        "refund_ids": ["RFN_EVAL_1"] if total_refund_paise else [],
        "total_refund_paise": total_refund_paise,
        "bank_transaction_ids_considered": (
            [valid_bank_transaction_id] if valid_bank_transaction_id else []
        ),
        "valid_bank_transaction_id": valid_bank_transaction_id,
        "normalized_references": {},
        "amount_comparison": {
            "order_amount_paise": 100_000,
            "settlement_gross_paise": 100_000 if primary_settlement_id else None,
            "settlement_net_paise": 95_000 if primary_settlement_id else None,
            "bank_amount_paise": 95_000 if valid_bank_transaction_id else None,
            "expected_post_refund_gross_paise": 100_000 - total_refund_paise,
            "total_refund_paise": total_refund_paise,
            "settlement_gross_matches_order": primary_settlement_id is not None,
            "settlement_reflects_refund": True if total_refund_paise else None,
            "bank_matches_settlement_net": valid_bank_transaction_id is not None,
        },
        "timestamp_comparison": {
            "settlement_settled_at": "2026-01-01T10:00:00",
            "bank_transaction_date": "2026-01-01T11:00:00",
            "difference_hours": 1.0,
            "tolerance_hours": 24,
            "within_tolerance": True,
        },
        "rules_triggered": rules_triggered
        or ["RULE_1_ORDER_TO_SETTLEMENT", "RULE_2_SETTLEMENT_TO_BANK"],
        "exceptions": exceptions,
        "audit_trail": [f"Held-out eval fixture {order_id}"],
    }


def _rec(
    n: int,
    *,
    scenario_type: str,
    expected: str,
    rationale: str,
    status: str,
    reconciled: bool,
    confidence: int,
    exceptions: list[dict[str, str]],
    **kwargs: Any,
) -> dict[str, Any]:
    order_id = f"FCEVAL_{n:04d}"
    return {
        "record_id": order_id,
        "scenario_type": scenario_type,
        "expected_decision": expected,
        "label_rationale": rationale,
        "order_result": _minimal_order_result(
            order_id=order_id,
            status=status,
            reconciled=reconciled,
            confidence_score=confidence,
            exceptions=exceptions,
            **kwargs,
        ),
    }


def build_held_out_records() -> list[dict[str, Any]]:
    """Author held-out labeled records using the labeling guide (not the agent).

    Callers must set ``expected_decision`` from the guide / rationale — never
    from ``decide_for_order``.
    """
    records: list[dict[str, Any]] = []
    n = 0

    def add(**kwargs: Any) -> None:
        nonlocal n
        n += 1
        records.append(_rec(n, **kwargs))

    # --- NO_ACTION (15): reconciled, no blocking exceptions ---
    for i in range(8):
        add(
            scenario_type="reconciled_clean",
            expected=DECISION_NO_ACTION,
            rationale="Reconciled with empty exceptions → NO_ACTION per labeling guide.",
            status="reconciled",
            reconciled=True,
            confidence=90 + (i % 10),
            exceptions=[],
        )
    for i in range(4):
        add(
            scenario_type="reconciled_timestamp_info",
            expected=DECISION_NO_ACTION,
            rationale="Reconciled with only TIMESTAMP_WITHIN_TOLERANCE (informational).",
            status="reconciled_within_timestamp_tolerance",
            reconciled=True,
            confidence=85 + i,
            exceptions=[
                {
                    "type": "TIMESTAMP_WITHIN_TOLERANCE",
                    "message": "Within tolerance",
                }
            ],
        )
    for _ in range(3):
        add(
            scenario_type="reconciled_reference_variation",
            expected=DECISION_NO_ACTION,
            rationale="Reconciled with only REFERENCE_VARIATION (informational).",
            status="reconciled",
            reconciled=True,
            confidence=88,
            exceptions=[
                {"type": "REFERENCE_VARIATION", "message": "Normalized reference"}
            ],
        )

    # --- ESCALATE_MISSING_SETTLEMENT (10) ---
    for i in range(8):
        add(
            scenario_type="missing_settlement",
            expected=DECISION_ESCALATE_MISSING_SETTLEMENT,
            rationale="MISSING_SETTLEMENT is highest-priority escalate rule.",
            status="unreconciled_missing_settlement",
            reconciled=False,
            confidence=20 + i,
            exceptions=[
                {"type": "MISSING_SETTLEMENT", "message": "No settlement found"}
            ],
            primary_settlement_id=None,
            valid_bank_transaction_id=None,
            rules_triggered=["RULE_1_ORDER_TO_SETTLEMENT"],
        )
    # Priority: MISSING_SETTLEMENT wins over amount mismatch
    add(
        scenario_type="missing_settlement_plus_mismatch",
        expected=DECISION_ESCALATE_MISSING_SETTLEMENT,
        rationale="MISSING_SETTLEMENT outranks SETTLEMENT_AMOUNT_MISMATCH.",
        status="unreconciled_missing_settlement",
        reconciled=False,
        confidence=15,
        exceptions=[
            {"type": "MISSING_SETTLEMENT", "message": "No settlement"},
            {"type": "SETTLEMENT_AMOUNT_MISMATCH", "message": "Also mismatched"},
        ],
        primary_settlement_id=None,
        valid_bank_transaction_id=None,
    )
    add(
        scenario_type="missing_settlement_plus_unknown",
        expected=DECISION_ESCALATE_MISSING_SETTLEMENT,
        rationale="MISSING_SETTLEMENT outranks unknown exception type.",
        status="unreconciled_missing_settlement",
        reconciled=False,
        confidence=18,
        exceptions=[
            {"type": "MISSING_SETTLEMENT", "message": "No settlement"},
            {"type": "UNKNOWN_PROCESSOR_CODE", "message": "Unrecognized code"},
        ],
        primary_settlement_id=None,
        valid_bank_transaction_id=None,
    )

    # --- ESCALATE_MISSING_BANK (10) ---
    for i in range(8):
        add(
            scenario_type="missing_bank",
            expected=DECISION_ESCALATE_MISSING_BANK,
            rationale="MISSING_BANK_TRANSACTION → escalate bank follow-up.",
            status="unreconciled_missing_bank",
            reconciled=False,
            confidence=30 + i,
            exceptions=[
                {
                    "type": "MISSING_BANK_TRANSACTION",
                    "message": "No bank transaction",
                }
            ],
            valid_bank_transaction_id=None,
        )
    add(
        scenario_type="missing_bank_plus_timestamp",
        expected=DECISION_ESCALATE_MISSING_BANK,
        rationale="MISSING_BANK_TRANSACTION outranks TIMESTAMP_OUTSIDE_TOLERANCE.",
        status="unreconciled_missing_bank",
        reconciled=False,
        confidence=28,
        exceptions=[
            {"type": "MISSING_BANK_TRANSACTION", "message": "No bank"},
            {
                "type": "TIMESTAMP_OUTSIDE_TOLERANCE",
                "message": "Outside tolerance",
            },
        ],
        valid_bank_transaction_id=None,
    )
    add(
        scenario_type="missing_bank_plus_refund_adjusted",
        expected=DECISION_ESCALATE_MISSING_BANK,
        rationale="MISSING_BANK_TRANSACTION outranks REFUND_ADJUSTED.",
        status="unreconciled_missing_bank",
        reconciled=False,
        confidence=25,
        exceptions=[
            {"type": "MISSING_BANK_TRANSACTION", "message": "No bank"},
            {"type": "REFUND_ADJUSTED", "message": "Refund noted"},
        ],
        valid_bank_transaction_id=None,
        total_refund_paise=5000,
    )

    # --- VERIFY_REFUND (10) ---
    for i in range(8):
        add(
            scenario_type="refund_adjusted",
            expected=DECISION_VERIFY_REFUND,
            rationale="REFUND_ADJUSTED without higher-priority blockers → VERIFY_REFUND.",
            status="reconciled_with_refund_adjustment",
            reconciled=True,
            confidence=80 + i,
            exceptions=[{"type": "REFUND_ADJUSTED", "message": "Refund reflected"}],
            total_refund_paise=10_000,
            rules_triggered=[
                "RULE_1_ORDER_TO_SETTLEMENT",
                "RULE_2_SETTLEMENT_TO_BANK",
                "RULE_3_REFUND_ADJUSTMENT",
            ],
        )
    add(
        scenario_type="refund_adjusted_plus_info",
        expected=DECISION_VERIFY_REFUND,
        rationale="REFUND_ADJUSTED + informational timestamp still VERIFY_REFUND.",
        status="reconciled_with_refund_adjustment",
        reconciled=True,
        confidence=82,
        exceptions=[
            {"type": "REFUND_ADJUSTED", "message": "Refund reflected"},
            {
                "type": "TIMESTAMP_WITHIN_TOLERANCE",
                "message": "Within tolerance",
            },
        ],
        total_refund_paise=8000,
    )
    add(
        scenario_type="refund_adjusted_unreconciled_edge",
        expected=DECISION_VERIFY_REFUND,
        rationale=(
            "REFUND_ADJUSTED present without higher-priority exceptions → "
            "VERIFY_REFUND even if reconciled=false (labeling guide priority)."
        ),
        status="unreconciled_settlement_amount",
        reconciled=False,
        confidence=55,
        exceptions=[{"type": "REFUND_ADJUSTED", "message": "Refund adjusted only"}],
        total_refund_paise=3000,
    )

    # --- FLAG_FOR_REVIEW: amount mismatches (8) ---
    for i in range(4):
        add(
            scenario_type="bank_amount_mismatch",
            expected=DECISION_FLAG_FOR_REVIEW,
            rationale="BANK_AMOUNT_MISMATCH → FLAG_FOR_REVIEW.",
            status="unreconciled_bank_amount",
            reconciled=False,
            confidence=40 + i,
            exceptions=[
                {"type": "BANK_AMOUNT_MISMATCH", "message": "Bank amount differs"}
            ],
        )
    for i in range(4):
        add(
            scenario_type="settlement_amount_mismatch",
            expected=DECISION_FLAG_FOR_REVIEW,
            rationale="SETTLEMENT_AMOUNT_MISMATCH → FLAG_FOR_REVIEW.",
            status="unreconciled_settlement_amount",
            reconciled=False,
            confidence=45 + i,
            exceptions=[
                {
                    "type": "SETTLEMENT_AMOUNT_MISMATCH",
                    "message": "Settlement gross differs",
                }
            ],
            valid_bank_transaction_id=None,
        )

    # --- FLAG_FOR_REVIEW: refund not reflected (3) ---
    for _ in range(3):
        add(
            scenario_type="refund_not_reflected",
            expected=DECISION_FLAG_FOR_REVIEW,
            rationale="REFUND_NOT_REFLECTED → FLAG_FOR_REVIEW.",
            status="unreconciled_refund_not_reflected",
            reconciled=False,
            confidence=50,
            exceptions=[
                {
                    "type": "REFUND_NOT_REFLECTED",
                    "message": "Refund missing from settlement",
                }
            ],
            total_refund_paise=7000,
            rules_triggered=[
                "RULE_1_ORDER_TO_SETTLEMENT",
                "RULE_2_SETTLEMENT_TO_BANK",
                "RULE_3_REFUND_ADJUSTMENT",
            ],
        )

    # --- FLAG_FOR_REVIEW: severe duplicates / orphan / timestamp (6) ---
    add(
        scenario_type="duplicate_settlement",
        expected=DECISION_FLAG_FOR_REVIEW,
        rationale="DUPLICATE_SETTLEMENT → FLAG_FOR_REVIEW.",
        status="unreconciled_duplicate_settlement",
        reconciled=False,
        confidence=35,
        exceptions=[
            {"type": "DUPLICATE_SETTLEMENT", "message": "Multiple settlements"}
        ],
    )
    add(
        scenario_type="duplicate_bank",
        expected=DECISION_FLAG_FOR_REVIEW,
        rationale="DUPLICATE_BANK_TRANSACTION → FLAG_FOR_REVIEW.",
        status="unreconciled_duplicate_bank",
        reconciled=False,
        confidence=35,
        exceptions=[
            {
                "type": "DUPLICATE_BANK_TRANSACTION",
                "message": "Duplicate bank rows",
            }
        ],
    )
    add(
        scenario_type="orphan_bank",
        expected=DECISION_FLAG_FOR_REVIEW,
        rationale="ORPHAN_BANK_TRANSACTION → FLAG_FOR_REVIEW.",
        status="unreconciled_orphan_bank",
        reconciled=False,
        confidence=30,
        exceptions=[
            {"type": "ORPHAN_BANK_TRANSACTION", "message": "Orphan bank credit"}
        ],
    )
    for _ in range(3):
        add(
            scenario_type="timestamp_outside_tolerance",
            expected=DECISION_FLAG_FOR_REVIEW,
            rationale="TIMESTAMP_OUTSIDE_TOLERANCE → FLAG_FOR_REVIEW.",
            status="unreconciled_timestamp",
            reconciled=False,
            confidence=42,
            exceptions=[
                {
                    "type": "TIMESTAMP_OUTSIDE_TOLERANCE",
                    "message": "Beyond 24h tolerance",
                }
            ],
        )

    # --- FLAG_FOR_REVIEW: unknown / ambiguous / unreconciled edge (7) ---
    for i in range(3):
        add(
            scenario_type="unknown_exception",
            expected=DECISION_FLAG_FOR_REVIEW,
            rationale="Unknown exception type → fail-safe FLAG_FOR_REVIEW.",
            status="unreconciled_unknown",
            reconciled=False,
            confidence=33 + i,
            exceptions=[
                {
                    "type": f"UNKNOWN_EXCEPTION_TYPE_{i}",
                    "message": "Unsupported exception vocabulary entry",
                }
            ],
        )
    for _ in range(2):
        add(
            scenario_type="unreconciled_no_exceptions",
            expected=DECISION_FLAG_FOR_REVIEW,
            rationale="Unreconciled with empty exceptions → ambiguous FLAG_FOR_REVIEW.",
            status="unreconciled",
            reconciled=False,
            confidence=40,
            exceptions=[],
        )
    add(
        scenario_type="reconciled_with_unknown_exception",
        expected=DECISION_FLAG_FOR_REVIEW,
        rationale="Reconciled but unknown exception is not informational → FLAG_FOR_REVIEW.",
        status="reconciled",
        reconciled=True,
        confidence=70,
        exceptions=[
            {"type": "PROCESSOR_TIMEOUT_SIGNAL", "message": "Timeout signal from processor"}
        ],
    )
    add(
        scenario_type="combined_mismatch_and_refund_not_reflected",
        expected=DECISION_FLAG_FOR_REVIEW,
        rationale="BANK_AMOUNT_MISMATCH present (priority over REFUND_NOT_REFLECTED alone).",
        status="unreconciled_bank_amount",
        reconciled=False,
        confidence=38,
        exceptions=[
            {"type": "BANK_AMOUNT_MISMATCH", "message": "Bank differs"},
            {
                "type": "REFUND_NOT_REFLECTED",
                "message": "Refund also missing",
            },
        ],
        total_refund_paise=2000,
    )

    assert len(records) >= 50, f"Need ≥50 records, got {len(records)}"
    return records


def build_held_out_dataset() -> dict[str, Any]:
    records = build_held_out_records()
    expected_counts: dict[str, int] = {d: 0 for d in DECISION_LABELS}
    for rec in records:
        expected_counts[rec["expected_decision"]] = (
            expected_counts.get(rec["expected_decision"], 0) + 1
        )
    return {
        "dataset_id": DATASET_ID,
        "held_out": True,
        "purpose": "Finance Controller decision evaluation only — not demo data.",
        "demo_data_note": (
            "Demonstration continues to use production CSVs + data/demo_bank.csv. "
            "This file is held-out evaluation data and must not replace the demo path."
        ),
        "label_source": (
            "Human-authored expected_decision labels following LABELING_GUIDE priority "
            "rules in finance_agent_eval.py. Labels were written into this dataset "
            "without calling decide_for_order / run_finance_controller."
        ),
        "labeling_guide": LABELING_GUIDE,
        "record_count": len(records),
        "expected_decision_counts": expected_counts,
        "records": records,
    }


def write_held_out_dataset(path: Path = EVAL_DATASET_PATH) -> dict[str, Any]:
    dataset = build_held_out_dataset()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(dataset, handle, indent=2)
        handle.write("\n")
    return dataset


def load_held_out_dataset(path: Path = EVAL_DATASET_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Held-out Finance Controller evaluation dataset not found: {path}"
        )
    with path.open(encoding="utf-8") as handle:
        dataset = json.load(handle)
    if not dataset.get("held_out"):
        raise ValueError("Dataset must be marked held_out=true")
    if dataset.get("dataset_id") != DATASET_ID:
        raise ValueError(
            f"Unexpected dataset_id {dataset.get('dataset_id')!r}; "
            f"expected {DATASET_ID!r}"
        )
    records = dataset.get("records")
    if not isinstance(records, list) or len(records) < 50:
        raise ValueError("Held-out dataset must contain at least 50 labeled records")
    for rec in records:
        if "expected_decision" not in rec:
            raise ValueError(f"Record {rec.get('record_id')} missing expected_decision")
        if rec["expected_decision"] not in ALLOWED_DECISIONS:
            raise ValueError(
                f"Record {rec.get('record_id')} has unsupported expected_decision "
                f"{rec['expected_decision']!r}"
            )
        if "order_result" not in rec:
            raise ValueError(f"Record {rec.get('record_id')} missing order_result")
    return dataset


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return None
    return 2 * precision * recall / (precision + recall)


PredictFn = Callable[[dict[str, Any]], str]


def _default_predict(order_result: dict[str, Any]) -> str:
    return decide_for_order(order_result).decision


def evaluate_finance_controller(
    dataset: dict[str, Any] | None = None,
    *,
    predict_fn: PredictFn | None = None,
    dataset_path: Path = EVAL_DATASET_PATH,
) -> dict[str, Any]:
    """Run Finance Controller predictions against held-out expected labels.

    ``predict_fn`` defaults to the real agent. Tests may inject a mock predictor
    to prove error detection without changing agent policy.
    """
    data = dataset if dataset is not None else load_held_out_dataset(dataset_path)
    predict = predict_fn or _default_predict
    records = data["records"]

    labels = list(DECISION_LABELS)
    confusion: dict[str, dict[str, int]] = {
        exp: {pred: 0 for pred in labels} for exp in labels
    }

    correct = 0
    incorrect = 0
    errors: list[dict[str, Any]] = []
    unknown_unsupported_predictions = 0
    predictions: list[str] = []

    started = time.perf_counter()
    for rec in records:
        order_result = rec["order_result"]
        expected = rec["expected_decision"]
        predicted = predict(order_result)
        predictions.append(predicted)

        if predicted not in ALLOWED_DECISIONS:
            unknown_unsupported_predictions += 1
            # Map into FLAG_FOR_REVIEW bucket for matrix display of unexpected output.
            matrix_pred = DECISION_FLAG_FOR_REVIEW
        else:
            matrix_pred = predicted

        if expected not in confusion:
            confusion[expected] = {pred: 0 for pred in labels}
        if matrix_pred not in confusion[expected]:
            confusion[expected][matrix_pred] = 0
        confusion[expected][matrix_pred] += 1

        if predicted == expected:
            correct += 1
        else:
            incorrect += 1
            exceptions = order_result.get("exceptions") or []
            errors.append(
                {
                    "record_id": rec.get("record_id"),
                    "order_id": order_result.get("order_id"),
                    "expected_decision": expected,
                    "predicted_decision": predicted,
                    "reconciliation_status": order_result.get("status"),
                    "reconciled": order_result.get("reconciled"),
                    "confidence_score": order_result.get("confidence_score"),
                    "exception_types": [
                        e.get("type")
                        for e in exceptions
                        if isinstance(e, dict) and e.get("type")
                    ],
                    "label_rationale": rec.get("label_rationale"),
                    "mismatch_reason": (
                        f"Expected {expected} per labeling guide "
                        f"({rec.get('scenario_type')}); agent predicted {predicted}."
                    ),
                }
            )
    elapsed = time.perf_counter() - started
    n = len(records)
    accuracy = _safe_div(correct, n)

    per_decision: dict[str, Any] = {}
    for label in labels:
        support = sum(1 for rec in records if rec["expected_decision"] == label)
        tp = confusion.get(label, {}).get(label, 0)
        fp = sum(
            confusion.get(exp, {}).get(label, 0)
            for exp in labels
            if exp != label
        )
        fn = sum(
            confusion.get(label, {}).get(pred, 0)
            for pred in labels
            if pred != label
        )
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        per_decision[label] = {
            "support": support,
            "correct": tp,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
        }

    unresolved_cases = sum(1 for p in predictions if p != DECISION_NO_ACTION)

    return {
        "dataset": data.get("dataset_id", DATASET_ID),
        "held_out": True,
        "label_source": data.get("label_source"),
        "measurement_note": (
            "Measured on the held-out synthetic evaluation dataset. "
            "This is not a claim of production accuracy."
        ),
        "records_evaluated": n,
        "correct_decisions": correct,
        "incorrect_decisions": incorrect,
        "accuracy": accuracy,
        "throughput": {
            "records_processed": n,
            "elapsed_seconds": round(elapsed, 6),
            "records_per_second": (
                round(n / elapsed, 3) if elapsed > 0 else None
            ),
        },
        "per_decision": per_decision,
        "confusion_matrix": {
            "labels": labels,
            "matrix": confusion,
            "rows_are_expected": True,
            "columns_are_predicted": True,
        },
        "error_analysis": {
            "false_positive_definition": LABELING_GUIDE["definitions"]["false_positive"],
            "false_negative_definition": LABELING_GUIDE["definitions"]["false_negative"],
            "unresolved_cases": unresolved_cases,
            "unknown_unsupported_predictions": unknown_unsupported_predictions,
            "incorrect_count": incorrect,
        },
        "errors": errors,
        "definitions": LABELING_GUIDE["definitions"],
    }


def write_evaluation_result(
    result: dict[str, Any],
    path: Path = EVAL_OUTPUT_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")


def format_evaluation_summary(result: dict[str, Any]) -> str:
    lines = [
        "Finance Controller evaluation (held-out)",
        f"  dataset: {result['dataset']}",
        f"  records_evaluated: {result['records_evaluated']}",
        f"  accuracy: {result['accuracy']}",
        (
            f"  correct/incorrect: {result['correct_decisions']}/"
            f"{result['incorrect_decisions']}"
        ),
        (
            f"  throughput: {result['throughput']['records_processed']} records in "
            f"{result['throughput']['elapsed_seconds']}s "
            f"({result['throughput']['records_per_second']} rec/s)"
        ),
        "  per_decision:",
    ]
    for label, metrics in result["per_decision"].items():
        lines.append(
            f"    {label}: support={metrics['support']} "
            f"P={metrics['precision']} R={metrics['recall']} F1={metrics['f1']}"
        )
    lines.append(f"  errors: {len(result['errors'])}")
    lines.append(f"  note: {result['measurement_note']}")
    return "\n".join(lines)


def main() -> None:
    if not EVAL_DATASET_PATH.exists():
        write_held_out_dataset()
        print(f"Wrote held-out dataset → {EVAL_DATASET_PATH}")
    result = evaluate_finance_controller()
    write_evaluation_result(result)
    print(format_evaluation_summary(result))
    print(f"  wrote: {EVAL_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
