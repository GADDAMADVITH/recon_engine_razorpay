# ReconEngine Architecture

ReconEngine is a deterministic financial reconciliation engine. This document
describes the current synthetic data foundation and how production inputs differ
from evaluation metadata.

For the evaluator walkthrough, current HTTP routes, demo scenarios, and local
run commands (API on port **8001**), see [README.md](README.md).

## Components (current milestone)

| Component | Role | Consumes ground truth? |
|-----------|------|------------------------|
| `data_gen.py` | Generates synthetic CSV inputs and evaluation metadata | Writes it |
| `data/*.csv` | Production-style reconciliation inputs | No |
| `data/ground_truth.json` | Evaluation-only expected outcomes for `metrics.py` | N/A |
| `data/finance_controller_eval_v1.json` | Held-out labels for Finance Controller decisions | N/A |
| `recon_engine.py` | Reconciliation engine; discovers relationships from CSVs | **Must not** |
| `metrics.py` | Scores engine output against ground truth | Yes |
| `finance_agent.py` | Advisory Finance Controller (deterministic policy) | **Must not** |
| `finance_agent_run.py` | Agent run / decision trace | **Must not** |
| `finance_agent_plan.py` | Batch orchestration / priority work plan | **Must not** |
| `finance_agent_eval.py` | Scores Finance Controller vs held-out labels | Uses FC eval dataset only |
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
| `/api/v1/reconciliation/{order_id}/audit` | GET | Structured audit for one order (production report) |
| `/api/v1/reconciliation/{order_id}/audit/explain` | GET | Gemini explanation of that production-report audit |
| `/api/v1/reconciliation/audit` | POST | Structured audit from a supplied `order_result` |
| `/api/v1/reconciliation/audit/explain` | POST | Gemini explanation from a supplied `order_result` |
| `/api/v1/reconciliation/import-bank` | POST | Upload bank CSV; reconcile against production orders/settlements |
| `/api/v1/evaluation` | GET | Run reconciliation, then evaluate against `ground_truth.json` |
| `/api/v1/finance-controller/run` | POST | Run advisory Finance Controller on recon results (read-only) |
| `/api/v1/finance-controller/run-agent` | POST | Agent run + decision trace (deterministic policy) |
| `/api/v1/finance-controller/agent-plan` | POST | Batch orchestration: analysis, priority queue, work plan |
| `/api/v1/finance-controller/evaluation` | GET | Finance Controller metrics on held-out labeled dataset |
| `/api/v1/finance-controller/demo-status` | GET | Demo readiness (no secrets) |
| `/api/v1/finance-controller/demo-reset` | POST | Clear local demo action store only |
| `/api/v1/finance-controller/actions/approve` | POST | Human-gated simulated action record (no money movement) |
| `/api/v1/sources/razorpay/sync` | POST | Live Razorpay fetch + map + reconcile when possible |
| `/api/v1/sources/razorpay/reconcile-demo` | POST | Synthetic Razorpay-shaped demo (does not call live Razorpay) |
| `/api/v1/sources/razorpay/verify-payment` | POST | Checkout signature verification (dev utility) |

The full table with purpose notes is also in [README.md](README.md#10-api-endpoints).

**Ground truth boundary:** `ground_truth.json` is used **only** by the
evaluation endpoint (via `metrics.py`). Reconciliation endpoints read only the
four production CSV files.

**Local development:**

```bash
./venv/bin/uvicorn api:app --reload --port 8001
```

The frontend defaults to `http://127.0.0.1:8001` (`VITE_API_BASE_URL`).

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

## Finance Controller (advisory decision layer)

```
Razorpay / Bank CSV
        ↓
Deterministic Reconciliation Engine
        ↓
Reconciliation Result
        ↓
Structured Audit / Evidence
        ↓
Finance Controller Agent (`finance_agent.py`)
  — deterministic policy: classification / safety boundary
        ↓
Agent Run / Decision Trace (`finance_agent_run.py`)
        ↓
Agent Orchestration / Work Plan (`finance_agent_plan.py`)
  — batch analysis / prioritization / work planning
        ↓
Human Approval → Simulated Action → Audit Trail
```

### Layer boundaries

| Layer | Responsibility | Must not |
|-------|----------------|----------|
| **Deterministic policy** (`finance_agent.py`) | Classify each order into allowlisted decisions; set approval gates | Call Gemini; mutate recon facts |
| **Agent orchestration** (`finance_agent_plan.py`) | Analyze the full batch, group unresolved cases, compute reproducible priority, emit a work queue + bounded agent plan | Reclassify with an LLM; bypass approval; move money |
| **Gemini** (`ai_explainer.py` / chat) | Explain audits and answer questions from structured evidence | Decide status, priority, or actions |

The Finance Controller is **downstream** of reconciliation. It never mutates
status, amounts, confidence, or Razorpay/bank records. Orchestration reuses
`run_finance_controller_agent` so decision distribution stays identical to the
agent-run contract. Gemini remains explanation/chat only — it is not in the
decision or priority path.

`POST /api/v1/finance-controller/agent-plan` — empty body uses the production
100-record reconciliation report; optional `order_results` supports Bank Import
demo batches.

### Demo data vs held-out evaluation data

| Path | Data | Purpose |
|------|------|---------|
| **Demo / product** | Production CSVs + `data/demo_bank.csv` | Walkthrough and live 100-record agent batch |
| **Held-out evaluation** | `data/finance_controller_eval_v1.json` | Measure Finance Controller decision accuracy |

These paths must stay separate. Do not use the held-out file as the Bank Import
demo, and do not treat demo metrics as evaluation accuracy.

### How evaluation labels were created

Labels in `finance_controller_eval_v1.json` follow a human-authored
**labeling guide** (priority rules documented in `finance_agent_eval.LABELING_GUIDE`
and embedded in the dataset metadata). Expected decisions were written into the
dataset **without** calling `decide_for_order` / `run_finance_controller`.

- **False positive** (class C): agent predicted C when expected was not C.
- **False negative** (class C): expected was C but agent predicted something else.

### Running Finance Controller evaluation

```bash
./venv/bin/python finance_agent_eval.py
# or
curl -sS http://127.0.0.1:8001/api/v1/finance-controller/evaluation
```

Output: `data/finance_controller_evaluation.json` (also returned by the API).

**Measured on the held-out synthetic evaluation dataset** (not production ops):

| Metric | Value |
|--------|-------|
| Records evaluated | 69 |
| Accuracy | 1.0 |
| Errors | 0 |

Per-decision precision / recall / F1 are 1.0 for all five allowlisted decisions
on this held-out set (policy-aligned labels). Throughput is reported as
`records_processed`, `elapsed_seconds`, and `records_per_second` in the JSON
output (environment-dependent; not a published benchmark).

This is **policy-fidelity measurement on synthetic fixtures**, not a claim of
production accuracy. If the agent policy and labeling guide diverge later,
accuracy will drop and `errors[]` will list mismatches.

### Human-gated simulated actions

```
Decision → Approval Required → Human Approval → Simulated Action Record → Audit Event
```

`finance_actions.py` + `POST /api/v1/finance-controller/actions/approve` close one
ops loop **without money movement**. The server recomputes the agent decision;
`NO_ACTION` is rejected; approvals are idempotent; reconciliation facts stay
immutable.

**ReconEngine does not move money or execute live Razorpay financial actions in this MVP.**

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

finance_agent.py ◄── order_results (engine)
finance_agent_eval.py ◄── data/finance_controller_eval_v1.json (held-out labels)
        └──► data/finance_controller_evaluation.json / GET .../finance-controller/evaluation
```

## Razorpay integration (Phase 3A — read-only client)

An isolated integration layer lives under `integrations/razorpay/`. It authenticates
with the official Razorpay REST API using environment variables and exposes **read-only**
fetch methods. It does **not** modify `recon_engine.py`, CSV ingestion, or the HTTP API.

| Variable | Required | Description |
|----------|----------|-------------|
| `RAZORPAY_KEY_ID` | Yes | Razorpay Test/Live Key ID |
| `RAZORPAY_KEY_SECRET` | Yes | Razorpay Key Secret (never commit) |
| `RAZORPAY_BASE_URL` | No | Defaults to `https://api.razorpay.com/v1` |
| `RAZORPAY_TIMEOUT_SECONDS` | No | Request timeout (default 30) |

**Local connectivity check (developer only):**

```bash
export RAZORPAY_KEY_ID=...
export RAZORPAY_KEY_SECRET=...
python -m integrations.razorpay.verify_connectivity
```

This performs a minimal `GET /orders?count=1` call. Credentials are never printed or
returned. Use Razorpay **Test Mode** keys for development.
