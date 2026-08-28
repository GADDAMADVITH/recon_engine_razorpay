"""Small synthetic pipeline integration tests."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from metrics import build_evaluation
from tests.conftest import DT_BASE, compute_settlement_amounts, run_engine_pipeline, write_csv_dataset


def _three_order_dataset() -> dict[str, pd.DataFrame]:
    """One success, one missing bank, one settlement mismatch."""
    rows = []
    settlements = []
    refunds = []
    bank = []
    for idx, (order_id, scenario) in enumerate(
        [("ORD_0001", "ok"), ("ORD_0002", "missing_bank"), ("ORD_0003", "mismatch")],
        start=1,
    ):
        gross = 100_000 * idx
        fee, tax, net = compute_settlement_amounts(gross)
        rows.append(
            {"order_id": order_id, "amount": gross, "created_at": DT_BASE.isoformat()}
        )
        settled_at = (DT_BASE + timedelta(hours=idx)).isoformat()
        if scenario != "missing_settlement":
            settlements.append(
                {
                    "settlement_id": f"SET_{idx:04d}",
                    "order_id": order_id,
                    "gross_amount": gross if scenario != "mismatch" else gross + 5000,
                    "fee": fee,
                    "tax": tax,
                    "net_amount": net if scenario != "mismatch" else compute_settlement_amounts(gross + 5000)[2],
                    "settled_at": settled_at,
                }
            )
        if scenario == "ok":
            bank.append(
                {
                    "bank_transaction_id": f"BNK_{idx:04d}",
                    "settlement_ref": f"SET_{idx:04d}",
                    "amount": net,
                    "transaction_date": settled_at,
                    "description": f"Payout {order_id}",
                }
            )

    return {
        "orders": pd.DataFrame(rows),
        "settlements": pd.DataFrame(settlements),
        "refunds": pd.DataFrame(columns=["refund_id", "order_id", "refund_amount", "created_at"]),
        "bank": pd.DataFrame(bank),
    }


@pytest.mark.integration
def test_three_order_pipeline(tmp_path: Path):
    write_csv_dataset(tmp_path, _three_order_dataset())
    report = run_engine_pipeline(tmp_path)
    assert report["summary"]["total_orders"] == 3
    by_id = {r["order_id"]: r for r in report["order_results"]}
    assert by_id["ORD_0001"]["reconciled"] is True
    assert by_id["ORD_0002"]["reconciled"] is False
    assert by_id["ORD_0003"]["reconciled"] is False


@pytest.mark.integration
def test_report_json_round_trip(tmp_path: Path):
    from recon_engine import write_report

    write_csv_dataset(tmp_path, _three_order_dataset())
    report = run_engine_pipeline(tmp_path)
    out_path = tmp_path / "report.json"
    write_report(report, out_path)
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["summary"] == report["summary"]
