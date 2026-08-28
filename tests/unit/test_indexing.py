"""Tests for bank transaction indexing."""

from __future__ import annotations

from recon_engine import build_bank_index, build_duplicate_bank_index
from tests.conftest import make_bank_tx


def test_build_bank_index_skips_unresolved():
    txs = [
        make_bank_tx("BNK_0001", "SET_0001", resolved_settlement_id="SET_0001"),
        make_bank_tx("BNK_0002", "ORPHAN-ORD_0001", ref_category="orphan", resolved_settlement_id=None),
    ]
    index = build_bank_index(txs)
    assert list(index.keys()) == ["SET_0001"]
    assert len(index["SET_0001"]) == 1


def test_build_bank_index_includes_stl_resolved():
    txs = [
        make_bank_tx(
            "BNK_0001",
            "STL-0001",
            ref_category="reference_variation",
            resolved_settlement_id="SET_0001",
        )
    ]
    index = build_bank_index(txs)
    assert "SET_0001" in index


def test_build_bank_index_sorts_multiple_banks():
    txs = [
        make_bank_tx("BNK_0002", "SET_0001", resolved_settlement_id="SET_0001"),
        make_bank_tx("BNK_0001", "SET_0001", resolved_settlement_id="SET_0001"),
    ]
    index = build_bank_index(txs)
    assert [tx.bank_transaction_id for tx in index["SET_0001"]] == ["BNK_0001", "BNK_0002"]


def test_build_duplicate_bank_index_only_dup_refs():
    txs = [
        make_bank_tx("BNK_0001", "DUP-SET_0001", ref_category="duplicate", resolved_settlement_id=None),
        make_bank_tx("BNK_0002", "SET_0001", resolved_settlement_id="SET_0001"),
    ]
    index = build_duplicate_bank_index(txs)
    assert "SET_0001" in index
    assert len(index["SET_0001"]) == 1
    assert index["SET_0001"][0].bank_transaction_id == "BNK_0001"
