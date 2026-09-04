"""Deterministic evaluation of ReconEngine reconciliation output against ground truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.json"
REPORT_PATH = DATA_DIR / "report.json"
EVALUATION_PATH = DATA_DIR / "evaluation.json"

EVALUATION_GRAIN = "order"
EXPECTED_ORDER_COUNT = 100

RELAXED_EQUIVALENT_SUCCESS_STATUSES = frozenset(
    {"reconciled", "reconciled_within_timestamp_tolerance"}
)

REQUIRED_GT_SCENARIO_FIELDS = (
    "order_id",
    "scenario_type",
    "expected_status",
    "expected_reconciled",
    "evaluation_grain",
    "primary_settlement_id",
    "primary_bank_transaction_id",
    "valid_bank_transaction_ids",
)

REQUIRED_REPORT_ORDER_FIELDS = (
    "order_id",
    "status",
    "reconciled",
    "primary_settlement_id",
    "valid_bank_transaction_id",
    "bank_transaction_ids_considered",
    "amount_comparison",
)


# ---------------------------------------------------------
# Loading
# ---------------------------------------------------------


def load_ground_truth(path: Path = GROUND_TRUTH_PATH) -> dict[str, Any]:
    """Load evaluation ground truth."""
    if not path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_report(path: Path = REPORT_PATH) -> dict[str, Any]:
    """Load reconciliation report."""
    if not path.exists():
        raise FileNotFoundError(f"Report file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------
# Validation
# ---------------------------------------------------------


def _validate_unique_order_ids(records: list[dict[str, Any]], source: str) -> None:
    order_ids = [record["order_id"] for record in records]
    if len(order_ids) != len(set(order_ids)):
        raise ValueError(f"Duplicate order_id values found in {source}")


def _validate_evaluation_grain(metadata: dict[str, Any], source: str) -> None:
    if metadata.get("evaluation_grain") != EVALUATION_GRAIN:
        raise ValueError(
            f"{source} evaluation_grain must be {EVALUATION_GRAIN!r}, "
            f"got {metadata.get('evaluation_grain')!r}"
        )


def validate_schemas(ground_truth: dict[str, Any], report: dict[str, Any]) -> None:
    """Validate ground truth and report structure before evaluation."""
    if "scenarios" not in ground_truth:
        raise ValueError("ground_truth.json missing scenarios[]")
    if "order_results" not in report:
        raise ValueError("report.json missing order_results[]")

    gt_scenarios = ground_truth["scenarios"]
    report_orders = report["order_results"]

    if len(gt_scenarios) != EXPECTED_ORDER_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_ORDER_COUNT} ground-truth scenarios, got {len(gt_scenarios)}"
        )
    if len(report_orders) != EXPECTED_ORDER_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_ORDER_COUNT} report order results, got {len(report_orders)}"
        )

    _validate_unique_order_ids(gt_scenarios, "ground_truth.scenarios")
    _validate_unique_order_ids(report_orders, "report.order_results")
    _validate_evaluation_grain(ground_truth.get("metadata", {}), "ground_truth")
    _validate_evaluation_grain(report.get("metadata", {}), "report")

    for scenario in gt_scenarios:
        for field in REQUIRED_GT_SCENARIO_FIELDS:
            if field not in scenario:
                raise ValueError(
                    f"Ground truth scenario {scenario.get('order_id')} missing {field}"
                )

    for order_result in report_orders:
        for field in REQUIRED_REPORT_ORDER_FIELDS:
            if field not in order_result:
                raise ValueError(
                    f"Report order result {order_result.get('order_id')} missing {field}"
                )

    gt_ids = {scenario["order_id"] for scenario in gt_scenarios}
    report_ids = {order_result["order_id"] for order_result in report_orders}
    missing_in_report = sorted(gt_ids - report_ids)
    missing_in_gt = sorted(report_ids - gt_ids)
    if missing_in_report:
        raise ValueError(f"Ground-truth orders missing from report: {missing_in_report}")
    if missing_in_gt:
        raise ValueError(f"Report orders missing from ground truth: {missing_in_gt}")


def join_records(
    ground_truth: dict[str, Any],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Join ground truth and report records by order_id."""
    report_by_order = {
        order_result["order_id"]: order_result
        for order_result in report["order_results"]
    }
    joined: list[dict[str, Any]] = []
    for scenario in sorted(ground_truth["scenarios"], key=lambda s: s["order_id"]):
        order_id = scenario["order_id"]
        joined.append(
            {
                "order_id": order_id,
                "ground_truth": scenario,
                "report": report_by_order[order_id],
            }
        )
    return joined


# ---------------------------------------------------------
# Layer A — Binary classification
# ---------------------------------------------------------


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def evaluate_binary_classification(
    joined: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute order-level reconciled vs expected_reconciled metrics."""
    tp = fp = fn = tn = 0
    mismatches: list[dict[str, Any]] = []

    for record in joined:
        expected = bool(record["ground_truth"]["expected_reconciled"])
        predicted = bool(record["report"]["reconciled"])

        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1
        else:
            tn += 1

        if predicted != expected:
            mismatches.append(
                {
                    "order_id": record["order_id"],
                    "expected_reconciled": expected,
                    "actual_reconciled": predicted,
                    "expected_status": record["ground_truth"]["expected_status"],
                    "actual_status": record["report"]["status"],
                    "scenario_type": record["ground_truth"]["scenario_type"],
                }
            )

    total = tp + fp + fn + tn
    precision = _safe_rate(tp, tp + fp)
    recall = _safe_rate(tp, tp + fn)
    if precision is None or recall is None or (precision + recall) == 0:
        f1 = 0.0 if total else None
    else:
        f1 = round(2 * precision * recall / (precision + recall), 6)

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "accuracy": _safe_rate(tp + tn, total),
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


# ---------------------------------------------------------
# Layer B — Status evaluation
# ---------------------------------------------------------


def _statuses_equivalent_relaxed(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    return (
        expected in RELAXED_EQUIVALENT_SUCCESS_STATUSES
        and actual in RELAXED_EQUIVALENT_SUCCESS_STATUSES
    )


def evaluate_status(
    joined: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute strict and relaxed status accuracy metrics."""
    strict_correct = 0
    relaxed_correct = 0
    strict_mismatches: list[dict[str, Any]] = []
    relaxed_mismatches: list[dict[str, Any]] = []
    expected_counts: dict[str, int] = {}
    actual_counts: dict[str, int] = {}
    confusion: dict[str, dict[str, int]] = {}

    for record in joined:
        expected = record["ground_truth"]["expected_status"]
        actual = record["report"]["status"]
        expected_counts[expected] = expected_counts.get(expected, 0) + 1
        actual_counts[actual] = actual_counts.get(actual, 0) + 1
        confusion.setdefault(expected, {})
        confusion[expected][actual] = confusion[expected].get(actual, 0) + 1

        if expected == actual:
            strict_correct += 1
        else:
            strict_mismatches.append(
                {
                    "order_id": record["order_id"],
                    "expected_status": expected,
                    "actual_status": actual,
                    "scenario_type": record["ground_truth"]["scenario_type"],
                }
            )

        if _statuses_equivalent_relaxed(expected, actual):
            relaxed_correct += 1
        else:
            relaxed_mismatches.append(
                {
                    "order_id": record["order_id"],
                    "expected_status": expected,
                    "actual_status": actual,
                    "scenario_type": record["ground_truth"]["scenario_type"],
                }
            )

    total = len(joined)
    return {
        "strict": {
            "correct": strict_correct,
            "incorrect": total - strict_correct,
            "accuracy": _safe_rate(strict_correct, total),
            "mismatches": strict_mismatches,
        },
        "relaxed": {
            "equivalence_policy": sorted(RELAXED_EQUIVALENT_SUCCESS_STATUSES),
            "correct": relaxed_correct,
            "incorrect": total - relaxed_correct,
            "accuracy": _safe_rate(relaxed_correct, total),
            "mismatches": relaxed_mismatches,
        },
        "expected_status_counts": dict(sorted(expected_counts.items())),
        "actual_status_counts": dict(sorted(actual_counts.items())),
        "confusion_matrix": {
            expected: dict(sorted(actuals.items()))
            for expected, actuals in sorted(confusion.items())
        },
    }


# ---------------------------------------------------------
# Layer C — Link-level validation
# ---------------------------------------------------------


def _normalize_optional_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ids_match(expected: Any, actual: Any) -> bool:
    return _normalize_optional_id(expected) == _normalize_optional_id(actual)


def _valid_bank_set_match(
    expected_ids: list[str],
    considered_ids: list[str],
    valid_bank_id: str | None,
) -> bool | None:
    expected_set = set(expected_ids)
    if not expected_set and valid_bank_id is None and not considered_ids:
        return True
    if not expected_set:
        return valid_bank_id is None and not considered_ids

    actual_valid_set = {valid_bank_id} if valid_bank_id else set()
    if actual_valid_set == expected_set:
        return True

    # bank_transaction_ids_considered should reflect settlement_ref-resolved valid links
    if set(considered_ids) == expected_set:
        return True

    return False


def evaluate_link_level(joined: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate primary settlement/bank and valid bank set matches."""
    settlement_matches = 0
    bank_matches = 0
    bank_set_matches = 0
    bank_set_applicable = 0
    per_order: list[dict[str, Any]] = []

    for record in joined:
        gt = record["ground_truth"]
        rep = record["report"]

        settlement_match = _ids_match(gt["primary_settlement_id"], rep["primary_settlement_id"])
        bank_match = _ids_match(gt["primary_bank_transaction_id"], rep["valid_bank_transaction_id"])
        expected_valid_ids = list(gt["valid_bank_transaction_ids"])
        considered_ids = list(rep["bank_transaction_ids_considered"])
        valid_bank_id = _normalize_optional_id(rep["valid_bank_transaction_id"])

        set_match = _valid_bank_set_match(expected_valid_ids, considered_ids, valid_bank_id)
        if set_match is not None:
            bank_set_applicable += 1
            if set_match:
                bank_set_matches += 1

        if settlement_match:
            settlement_matches += 1
        if bank_match:
            bank_matches += 1

        per_order.append(
            {
                "order_id": record["order_id"],
                "primary_settlement_match": settlement_match,
                "primary_bank_match": bank_match,
                "valid_bank_set_match": set_match,
                "expected_primary_settlement_id": gt["primary_settlement_id"],
                "actual_primary_settlement_id": rep["primary_settlement_id"],
                "expected_primary_bank_transaction_id": gt["primary_bank_transaction_id"],
                "actual_valid_bank_transaction_id": rep["valid_bank_transaction_id"],
                "expected_valid_bank_transaction_ids": expected_valid_ids,
                "actual_bank_transaction_ids_considered": considered_ids,
            }
        )

    total = len(joined)
    return {
        "primary_settlement_match_count": settlement_matches,
        "primary_settlement_match_rate": _safe_rate(settlement_matches, total),
        "primary_bank_match_count": bank_matches,
        "primary_bank_match_rate": _safe_rate(bank_matches, total),
        "valid_bank_set_match_count": bank_set_matches,
        "valid_bank_set_match_rate": _safe_rate(bank_set_matches, bank_set_applicable),
        "valid_bank_set_applicable_orders": bank_set_applicable,
        "per_order": per_order,
    }


# ---------------------------------------------------------
# Layer D — Scenario-level evaluation
# ---------------------------------------------------------


def evaluate_scenarios(joined: list[dict[str, Any]]) -> dict[str, Any]:
    """Group evaluation metrics by ground-truth scenario_type."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in joined:
        scenario_type = record["ground_truth"]["scenario_type"]
        grouped.setdefault(scenario_type, []).append(record)

    results: dict[str, Any] = {}
    for scenario_type in sorted(grouped):
        records = grouped[scenario_type]
        total = len(records)
        binary_correct = 0
        strict_correct = 0
        relaxed_correct = 0
        settlement_matches = 0
        bank_matches = 0

        for record in records:
            expected_reconciled = bool(record["ground_truth"]["expected_reconciled"])
            predicted_reconciled = bool(record["report"]["reconciled"])
            expected_status = record["ground_truth"]["expected_status"]
            actual_status = record["report"]["status"]

            if expected_reconciled == predicted_reconciled:
                binary_correct += 1
            if expected_status == actual_status:
                strict_correct += 1
            if _statuses_equivalent_relaxed(expected_status, actual_status):
                relaxed_correct += 1
            if _ids_match(
                record["ground_truth"]["primary_settlement_id"],
                record["report"]["primary_settlement_id"],
            ):
                settlement_matches += 1
            if _ids_match(
                record["ground_truth"]["primary_bank_transaction_id"],
                record["report"]["valid_bank_transaction_id"],
            ):
                bank_matches += 1

        results[scenario_type] = {
            "total_orders": total,
            "binary_correct": binary_correct,
            "binary_accuracy": _safe_rate(binary_correct, total),
            "strict_status_correct": strict_correct,
            "strict_status_accuracy": _safe_rate(strict_correct, total),
            "relaxed_status_correct": relaxed_correct,
            "relaxed_status_accuracy": _safe_rate(relaxed_correct, total),
            "primary_settlement_match_count": settlement_matches,
            "primary_settlement_match_rate": _safe_rate(settlement_matches, total),
            "primary_bank_match_count": bank_matches,
            "primary_bank_match_rate": _safe_rate(bank_matches, total),
        }

    return results


# ---------------------------------------------------------
# Layer E — Global special record validation
# ---------------------------------------------------------


def _extract_ids(records: list[dict[str, Any]], key: str) -> set[str]:
    return {str(record[key]) for record in records}


def evaluate_global_exceptions(
    ground_truth: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Compare special/global records without double-counting order-level cases."""
    special = ground_truth.get("special_records", {})
    global_exceptions = report.get("global_exceptions", [])

    orphan_expected = special.get("orphan_bank_transactions", [])
    dup_expected = special.get("duplicate_bank_transactions", [])
    settlements_without_bank_expected = set(special.get("settlements_without_bank", []))

    orphan_detected = [
        exc for exc in global_exceptions if exc.get("type") == "ORPHAN_BANK_TRANSACTION"
    ]
    dup_detected = [
        exc for exc in global_exceptions if exc.get("type") == "DUPLICATE_BANK_TRANSACTION"
    ]
    missing_bank_detected = [
        exc for exc in global_exceptions if exc.get("type") == "MISSING_BANK_TRANSACTION"
    ]

    orphan_expected_ids = _extract_ids(orphan_expected, "bank_transaction_id")
    orphan_detected_ids = _extract_ids(orphan_detected, "bank_transaction_id")

    dup_expected_ids = _extract_ids(dup_expected, "bank_transaction_id")
    dup_detected_ids = _extract_ids(dup_detected, "bank_transaction_id")

    missing_bank_detected_ids = {
        exc["settlement_id"] for exc in missing_bank_detected if "settlement_id" in exc
    }

    def _compare(expected_ids: set[str], detected_ids: set[str]) -> dict[str, Any]:
        matched = sorted(expected_ids & detected_ids)
        missing = sorted(expected_ids - detected_ids)
        unexpected = sorted(detected_ids - expected_ids)
        return {
            "expected_count": len(expected_ids),
            "detected_count": len(detected_ids),
            "matched_ids": matched,
            "missing_ids": missing,
            "unexpected_ids": unexpected,
            "detection_rate": _safe_rate(len(matched), len(expected_ids)),
        }

    return {
        "orphan_bank_transactions": _compare(orphan_expected_ids, orphan_detected_ids),
        "duplicate_bank_transactions": _compare(dup_expected_ids, dup_detected_ids),
        "settlements_without_bank": {
            "expected_count": len(settlements_without_bank_expected),
            "detected_count": len(missing_bank_detected_ids),
            "matched_ids": sorted(settlements_without_bank_expected & missing_bank_detected_ids),
            "missing_ids": sorted(settlements_without_bank_expected - missing_bank_detected_ids),
            "unexpected_ids": sorted(missing_bank_detected_ids - settlements_without_bank_expected),
            "detection_rate": _safe_rate(
                len(settlements_without_bank_expected & missing_bank_detected_ids),
                len(settlements_without_bank_expected),
            ),
        },
    }


# ---------------------------------------------------------
# Layer F — Amount / mismatch validation
# ---------------------------------------------------------


def evaluate_amount_validation(joined: list[dict[str, Any]]) -> dict[str, Any]:
    """Diagnostic validation for ground-truth mismatch_details vs report amount_comparison."""
    checked = 0
    correct = 0
    disagreements: list[dict[str, Any]] = []

    fields_to_compare = (
        "order_amount_paise",
        "settlement_gross_paise",
        "settlement_net_paise",
        "bank_amount_paise",
    )

    for record in joined:
        gt = record["ground_truth"]
        mismatch_details = gt.get("mismatch_details")
        if not mismatch_details:
            continue

        checked += 1
        amount_comparison = record["report"]["amount_comparison"]
        field_results: dict[str, Any] = {}
        order_correct = True

        for field_name in fields_to_compare:
            expected_value = mismatch_details.get(field_name)
            actual_value = amount_comparison.get(field_name)
            matches = expected_value == actual_value
            field_results[field_name] = {
                "expected": expected_value,
                "actual": actual_value,
                "match": matches,
            }
            if not matches:
                order_correct = False

        if order_correct:
            correct += 1
        else:
            disagreements.append(
                {
                    "order_id": record["order_id"],
                    "scenario_type": gt["scenario_type"],
                    "fields": field_results,
                }
            )

    return {
        "mismatch_cases_checked": checked,
        "mismatch_cases_correctly_represented": correct,
        "mismatch_validation_rate": _safe_rate(correct, checked),
        "disagreements": disagreements,
    }


# ---------------------------------------------------------
# Report assembly
# ---------------------------------------------------------


def build_evaluation(
    ground_truth: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Build the complete evaluation payload."""
    joined = join_records(ground_truth, report)

    binary = evaluate_binary_classification(joined)
    status = evaluate_status(joined)
    links = evaluate_link_level(joined)
    scenarios = evaluate_scenarios(joined)
    global_exceptions = evaluate_global_exceptions(ground_truth, report)
    amount_validation = evaluate_amount_validation(joined)

    mismatches = sorted(
        [
            *binary["mismatches"],
            *[
                {
                    **item,
                    "mismatch_type": "strict_status",
                }
                for item in status["strict"]["mismatches"]
            ],
            *[
                {
                    **item,
                    "mismatch_type": "relaxed_status",
                }
                for item in status["relaxed"]["mismatches"]
            ],
        ],
        key=lambda item: (item["order_id"], item.get("mismatch_type", "binary")),
    )

    return {
        "metadata": {
            "evaluator": "metrics",
            "evaluation_grain": EVALUATION_GRAIN,
            "orders_evaluated": len(joined),
            "report_generated_at": report.get("metadata", {}).get("generated_at"),
            "ground_truth_generated_at": ground_truth.get("metadata", {}).get("generated_at"),
            "evaluation_policy": {
                "primary_metric": "binary expected_reconciled vs report.reconciled",
                "strict_status_metric": "exact expected_status vs report.status",
                "relaxed_status_equivalence": sorted(RELAXED_EQUIVALENT_SUCCESS_STATUSES),
            },
        },
        "summary": {
            "orders_evaluated": len(joined),
            "binary_accuracy": binary["accuracy"],
            "binary_precision": binary["precision"],
            "binary_recall": binary["recall"],
            "binary_f1_score": binary["f1_score"],
            "strict_status_accuracy": status["strict"]["accuracy"],
            "relaxed_status_accuracy": status["relaxed"]["accuracy"],
            "primary_settlement_match_rate": links["primary_settlement_match_rate"],
            "primary_bank_match_rate": links["primary_bank_match_rate"],
            "valid_bank_set_match_rate": links["valid_bank_set_match_rate"],
        },
        "binary_classification": binary,
        "status_evaluation": status,
        "link_level_evaluation": links,
        "scenario_evaluation": scenarios,
        "global_exception_evaluation": global_exceptions,
        "amount_validation": amount_validation,
        "mismatches": mismatches,
    }


def write_evaluation(evaluation: dict[str, Any], path: Path = EVALUATION_PATH) -> None:
    """Write evaluation output to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(evaluation, handle, indent=2)
        handle.write("\n")


def print_summary(evaluation: dict[str, Any]) -> None:
    """Print a concise human-readable evaluation summary."""
    binary = evaluation["binary_classification"]
    status = evaluation["status_evaluation"]
    summary = evaluation["summary"]

    print("ReconEngine evaluation complete")
    print(f"  Orders evaluated: {summary['orders_evaluated']}")
    print()
    print("Binary reconciliation:")
    print(f"  TP: {binary['true_positives']}")
    print(f"  FP: {binary['false_positives']}")
    print(f"  FN: {binary['false_negatives']}")
    print(f"  TN: {binary['true_negatives']}")
    print(f"  Accuracy: {binary['accuracy']:.1%}" if binary["accuracy"] is not None else "  Accuracy: n/a")
    print(f"  Precision: {binary['precision']:.1%}" if binary["precision"] is not None else "  Precision: n/a")
    print(f"  Recall: {binary['recall']:.1%}" if binary["recall"] is not None else "  Recall: n/a")
    print(f"  F1: {binary['f1_score']:.1%}" if binary["f1_score"] is not None else "  F1: n/a")
    print()
    print("Status:")
    print(f"  Strict accuracy: {status['strict']['correct']}/{summary['orders_evaluated']}")
    print(f"  Relaxed accuracy: {status['relaxed']['correct']}/{summary['orders_evaluated']}")
    print()
    print("Scenario-level binary accuracy:")
    for scenario_type, metrics in evaluation["scenario_evaluation"].items():
        print(
            f"  {scenario_type}: {metrics['binary_correct']}/{metrics['total_orders']} "
            f"({metrics['binary_accuracy']:.1%})"
            if metrics["binary_accuracy"] is not None
            else f"  {scenario_type}: {metrics['binary_correct']}/{metrics['total_orders']}"
        )
    print()
    print(f"  evaluation: {EVALUATION_PATH}")


# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------


def main() -> None:
    """Load inputs, evaluate, print summary, and write evaluation.json."""
    ground_truth = load_ground_truth()
    report = load_report()
    validate_schemas(ground_truth, report)
    evaluation = build_evaluation(ground_truth, report)
    write_evaluation(evaluation)
    print_summary(evaluation)


if __name__ == "__main__":
    main()
