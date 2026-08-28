# ReconEngine Architecture

ReconEngine is a deterministic financial reconciliation engine. This document
describes the current synthetic data foundation and how production inputs differ
from evaluation metadata.

## Components (current milestone)

| Component | Role | Consumes ground truth? |
|-----------|------|------------------------|
| `data_gen.py` | Generates synthetic CSV inputs and evaluation metadata | Writes it |
| `data/*.csv` | Production-style reconciliation inputs | No |
| `data/ground_truth.json` | Evaluation-only expected outcomes for `metrics.py` | N/A |
| `recon_engine.py` | Reconciliation engine; discovers relationships from CSVs | **Must not** |
| `metrics.py` | Scores engine output against ground truth | Yes |
| `api.py` | HTTP API; orchestrates engine and evaluation | **Must not** (evaluation only) |

## HTTP API (`api.py`)

The API layer exposes reconciliation and evaluation over HTTP. It **does not**
contain reconciliation business logic. All matching, status, and confidence
rules remain in `recon_engine.py`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | API health check |
| `/api/v1/reconciliation/report` | GET | Run reconciliation on production CSVs; return full `report.json` structure |
| `/api/v1/reconciliation/summary` | GET | Concise summary: order counts, status counts, exception counts |
| `/api/v1/evaluation` | GET | Run reconciliation, then evaluate against `ground_truth.json` |

**Ground truth boundary:** `ground_truth.json` is used **only** by the
evaluation endpoint (via `metrics.py`). Reconciliation endpoints read only the
four production CSV files.

**Local development:**

```bash
uvicorn api:app --reload
```

**Error handling:** Missing input files return HTTP 404; validation failures
return HTTP 400; unexpected errors return HTTP 500 without Python tracebacks.

## Production input CSVs

Generated into `data/` by `data_gen.py`:

| File | Key columns | Purpose |
|------|-------------|---------|
| `orders.csv` | `order_id`, `amount`, `created_at` | Source orders (integer paise) |
| `settlements.csv` | `settlement_id`, `order_id`, `gross_amount`, `fee`, `tax`, `net_amount`, `settled_at` | Settlement records |
| `refunds.csv` | `refund_id`, `order_id`, `refund_amount`, `created_at` | Refund records |
| `bank.csv` | `bank_transaction_id`, `settlement_ref`, `amount`, `transaction_date`, `description` | Bank credits |

`recon_engine.py` must reconcile using **only these four files**. It must not
read `ground_truth.json`.

## Evaluation-only ground truth

`data/ground_truth.json` is machine-readable metadata for offline evaluation.
It documents expected outcomes per order and special records (orphan banks,
erroneous duplicates, duplicate settlements).

Ground truth is **not** a production input.

## Evaluation grain

Primary metric grain: **order-level**.

Each order receives:

- `expected_reconciled` (boolean)
- `expected_status` (finite outcome vocabulary)
- `scenario_type` (why the case exists)

### True negatives (order-level)

At order-level grain:

- **TP**: engine marks order reconciled; `expected_reconciled=true`
- **FP**: engine marks order reconciled; `expected_reconciled=false`
- **FN**: engine marks order not reconciled; `expected_reconciled=true`
- **TN**: engine marks order not reconciled; `expected_reconciled=false`

Link-level or transaction-level metrics may omit TN where negative predictions
are not meaningfully defined. Ground truth preserves link fields
(`primary_settlement_id`, `valid_bank_transaction_ids`, `special_records`) for
future extension.

## scenario_type vs expected_status

| Concept | Meaning | Example |
|---------|---------|---------|
| `scenario_type` | Why the test case exists | `refund_unadjusted_mismatch` |
| `expected_status` | Expected reconciliation outcome | `unreconciled_refund_not_adjusted` |

These are intentionally separate.

### Evaluation metrics (`metrics.py`)

`metrics.py` consumes only:

- `data/report.json` (engine output)
- `data/ground_truth.json` (expected outcomes)

It does **not** read production CSVs or re-run reconciliation.

Output: `data/evaluation.json`

**Primary metric (Layer A):** binary classification comparing
`report.reconciled` vs `ground_truth.expected_reconciled`.

**Status metrics (Layer B):**

- **Strict:** exact `report.status` vs `expected_status`
- **Relaxed:** treats `reconciled` and `reconciled_within_timestamp_tolerance`
  as equivalent successful statuses (evaluation policy only)

### Expected status vocabulary

- `reconciled`
- `reconciled_within_timestamp_tolerance`
- `unreconciled_timestamp_exceeded`
- `unreconciled_settlement_amount`
- `unreconciled_missing_settlement`
- `unreconciled_missing_bank`
- `reconciled_with_refund_adjustment`
- `unreconciled_refund_not_adjusted`
- `reconciled_with_reference_variation`
- `partially_reconciled_duplicate_settlement`

## Timestamp tolerance

Documented in ground truth metadata: **24 hours**.

Compare `settlements.settled_at` to `bank.transaction_date` for the valid bank
transaction linked via `settlement_ref`.

## Reference normalization

Bank `settlement_ref` values may use intentional variations:

| Bank ref | Normalizes to |
|----------|---------------|
| `SET_0034` | `SET_0034` |
| `STL-0034` | `SET_0034` |
| `ORPHAN-ORD_0024` | *(does not resolve)* |
| `DUP-SET_0050` | *(does not resolve)* |

Normalization is deterministic: strip `STL-` prefix to `SET_`, reject `ORPHAN-*`
and `DUP-*`.

## Primary vs duplicate semantics

### Duplicate settlements

Some orders have two settlements. The **primary** settlement (first generated)
receives the valid bank transaction. The **secondary** settlement has no valid
bank link via `settlement_ref`.

### Duplicate bank transactions

Rows with `DUP-{settlement_id}` refs are **erroneous duplicates**. They do not
resolve to settlements and must not be treated as valid bank matches. Example:
`BNK_0050` (`DUP-SET_0050`) is an erroneous duplicate; `BNK_0041` is the valid
bank transaction for `ORD_0050`.

### Orphan bank transactions

Rows with `ORPHAN-{order_id}` refs represent bank credits without a settlement
record (missing-settlement scenario).

## Determinism

All generation uses `RANDOM_SEED = 42`. Re-running `python data_gen.py`
produces identical CSV and ground-truth output.

## Data flow

```
data_gen.py
    ├── data/orders.csv      ──┐
    ├── data/settlements.csv   ├──► recon_engine.py ──► api.py (reconciliation endpoints)
    ├── data/refunds.csv       │         │                    │
    └── data/bank.csv        ──┘         └──► data/report.json (CLI only)
    └── data/ground_truth.json ───────────────► metrics.py ──► api.py (evaluation endpoint)
                                                      └──► data/evaluation.json (CLI only)
```
