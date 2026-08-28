"""Tests for exception handling."""

from __future__ import annotations

import pytest

from recon_engine import add_exception, collect_global_exceptions
from tests.conftest import make_bank_tx, make_settlement


def test_add_exception_appends():
    exceptions: list[dict] = []
    add_exception(exceptions, "MISSING_SETTLEMENT", "no settlement")
    assert len(exceptions) == 1
    assert exceptions[0]["type"] == "MISSING_SETTLEMENT"


def test_add_exception_deduplicates_by_type():
    exceptions: list[dict] = []
    add_exception(exceptions, "MISSING_SETTLEMENT", "first")
    add_exception(exceptions, "MISSING_SETTLEMENT", "second")
    assert len(exceptions) == 1
    assert exceptions[0]["message"] == "first"


def test_add_exception_preserves_details():
    exceptions: list[dict] = []
    add_exception(exceptions, "SETTLEMENT_AMOUNT_MISMATCH", "mismatch", details={"delta_paise": 100})
    assert exceptions[0]["details"]["delta_paise"] == 100


def test_add_exception_rejects_unknown_type():
    exceptions: list[dict] = []
    with pytest.raises(ValueError, match="Unsupported exception type"):
        add_exception(exceptions, "NOT_A_REAL_TYPE", "bad")


def test_collect_global_exceptions_orphan_and_dup():
    orphan = make_bank_tx(
        "BNK_O1", "ORPHAN-ORD_0001", ref_category="orphan", resolved_settlement_id=None
    )
    dup = make_bank_tx(
        "BNK_D1", "DUP-SET_0001", ref_category="duplicate", resolved_settlement_id=None
    )
    settlement = make_settlement()
    records = collect_global_exceptions([orphan, dup], [settlement], {})
    types = {r["type"] for r in records}
    assert "ORPHAN_BANK_TRANSACTION" in types
    assert "DUPLICATE_BANK_TRANSACTION" in types
    assert "MISSING_BANK_TRANSACTION" in types
