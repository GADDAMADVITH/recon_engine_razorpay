# Track 04 Demo Guide — ReconEngine Finance Controller Agent

This document is for evaluators. It describes the **implemented** system only.
It does **not** claim production accuracy, autonomous money movement, live financial
execution, or multi-tenant production readiness.

---

## A. 30-second project explanation

ReconEngine reconciles orders, settlements, refunds, and bank credits with a
**deterministic** engine. A **Finance Controller Agent** then consumes that evidence,
makes **bounded** finance-ops decisions over a **100-record** synthetic batch,
prioritizes unresolved work, and waits for **human approval** before recording a
**simulated** action and audit event.

Gemini is an **explanation / chat** layer only — never the decision-maker.

---

## B. Architecture

```
100 synthetic financial records
        ↓
Reconciliation Engine          ← financial source of truth
        ↓
Structured Audit / Evidence
        ↓
Finance Controller Agent       ← deterministic policy (finance_agent.py)
        ↓
Agent Run / Decision Trace
        ↓
Batch Analysis + Prioritized Work Queue   ← orchestration (finance_agent_plan.py)
        ↓
Human Approval / Rejection
        ↓
Simulated Action Recording     ← money_moved: false
        ↓
Audit Trail
```

| Layer | Role |
|-------|------|
| Reconciliation engine | Status, amounts, confidence — source of financial truth |
| Finance Controller | Allowlisted classification / safety boundary |
| Agent orchestration | Batch analysis, grouping, deterministic priority, work plan |
| Human | Approval gate for every non-`NO_ACTION` decision |
| Gemini | Explain audits / chat grounded in evidence only |

---

## C. 2–3 minute live demo sequence

**Prerequisites:** API on port **8001**, frontend pointing at `http://127.0.0.1:8001`.

```bash
./venv/bin/uvicorn api:app --host 127.0.0.1 --port 8001
# frontend
cd frontend && npm run dev
```

1. Open ReconEngine → **Bank Import**
2. **Load Demo CSV** → **Run Reconciliation**
3. Open **ORD_0002** (primary failure — bank amount mismatch)
4. Inspect Pipeline / reconciliation evidence
5. Inspect **Agent Decision** (decision, rationale, proposed action)
6. **Approve** or **Reject** → see simulated action (`Money moved: false`)
7. Open **Audit Trail**
8. Optional: with the ORD_0002 drawer still open, use **Explain with AI** / chatbot
   (the console chat passes the drawer `order_result`, so it explains the **demo**
   mismatch — not the production-batch row with the same ID)
9. Return to console **Dashboard** → Finance Controller Agent
10. Show **100-record** operational metrics + Agent Work Queue / Agent Plan
11. Show **69-record** held-out evaluation (policy fidelity wording)

**ID note:** Production CSV `ORD_0002` and Bank Import demo `ORD_0002` are different
scenarios. The **mismatch failure demo** is the Bank Import path. Always open the
demo order drawer before asking Gemini about ORD_0002.

Optional: **Reset demo actions** clears local simulated action state only
(not CSVs, held-out labels, or policy).

---

## D. Five scenario table

Decisions come from the Finance Controller policy over engine evidence —
**not** hardcoded in the UI.

| Order | Story | Decision | Simulated action (if approved) |
|-------|--------|----------|--------------------------------|
| ORD_0001 | Clean match | `NO_ACTION` | — (cannot approve) |
| ORD_0002 | **Primary failure** — bank amount mismatch | `FLAG_FOR_REVIEW` | `RECORD_REVIEW` |
| ORD_0003 | Missing bank | `ESCALATE_MISSING_BANK` | `RECORD_MISSING_BANK_ESCALATION` |
| ORD_0033 | Refund-adjusted | `VERIFY_REFUND` | `RECORD_REFUND_VERIFICATION` |
| ORD_0024 | Missing settlement | `ESCALATE_MISSING_SETTLEMENT` | `RECORD_MISSING_SETTLEMENT_ESCALATION` |

---

## E. 100-record operational metrics

Full batch (production reconciliation report) — **not** cherry-picked:

| Decision | Count |
|----------|------:|
| `NO_ACTION` | 40 |
| `FLAG_FOR_REVIEW` | 32 |
| `ESCALATE_MISSING_BANK` | 10 |
| `VERIFY_REFUND` | 10 |
| `ESCALATE_MISSING_SETTLEMENT` | 8 |
| **Total** | **100** |

- Unresolved / review required / pending approval: **60**
- `money_moved`: **false**

API: `POST /api/v1/finance-controller/run-agent` and `POST /api/v1/finance-controller/agent-plan` with empty body.

---

## F. Held-out evaluation explanation

Separate dataset: `data/finance_controller_eval_v1.json` (`FCEVAL_*` IDs).

| Metric | Value |
|--------|------:|
| Records | 69 |
| Correct | 69 |
| Incorrect | 0 |
| Accuracy | 1.0 |
| Errors | [] |

**This measures policy fidelity on the synthetic held-out dataset, not production accuracy.**

Labels were human-authored from the labeling guide **without** calling the agent
to copy its outputs. Do not conflate this score with the operational 100-record batch.

API: `GET /api/v1/finance-controller/evaluation`

---

## G. Human approval flow

```
Agent decision (non-NO_ACTION)
        ↓
Requires approval
        ↓
Human Approve  →  RECORDED (simulated action + audit)
   or Reject   →  REJECTED (no simulated follow-up + audit)
```

- Repeated approve / reject: **idempotent**
- `NO_ACTION` cannot be approved
- Mismatched client decision claims: rejected
- Terminal states cannot be illegally reversed (e.g. RECORDED → REJECT)
- Original order results remain **immutable**

---

## H. Safety / guardrails

- Deterministic engine + policy remain financial truth
- No real Razorpay refunds / captures / payouts in this MVP
- Simulated actions only — **`money_moved: false`**
- Gemini does not classify, prioritize, approve, or execute
- Secrets (`GEMINI_API_KEY`, `RAZORPAY_KEY_SECRET`) stay server-side / gitignored
- Demo reset affects local action store only

---

## I. Why this qualifies as an AGENT

This is **not** merely a dashboard. The agent:

1. Consumes reconciliation evidence
2. Makes **bounded** finance-ops decisions (allowlisted)
3. Produces rationale and immutable decision traces
4. Analyzes the **full** batch (100 records)
5. Prioritizes unresolved work (deterministic scores)
6. Proposes allowlisted simulated actions
7. **Waits** for human approval
8. Records approved / rejected outcomes
9. Emits an audit trail

Orchestration plans work; it does **not** replace the deterministic policy with an LLM.

---

## J. Known intentional limitations

- No live Razorpay financial actions
- No autonomous money movement
- No multi-tenant production auth
- No hosted SLA / production-grade durable action store claim
- Held-out **1.0** = synthetic policy fidelity, **not** production ops accuracy
- Gemini optional — without `GEMINI_API_KEY`, explain/chat may be unavailable;
  reconciliation and the Finance Controller still work

---

## Quick API smoke (port 8001)

```bash
curl -sS -X POST http://127.0.0.1:8001/api/v1/finance-controller/run-agent \
  -H 'Content-Type: application/json' -d '{}' | jq '.records_processed,.decisions_by_type'

curl -sS -X POST http://127.0.0.1:8001/api/v1/finance-controller/agent-plan \
  -H 'Content-Type: application/json' -d '{}' | jq '.records_processed,.money_moved,.unresolved_count'

curl -sS http://127.0.0.1:8001/api/v1/finance-controller/evaluation \
  | jq '.records_evaluated,.accuracy,.measurement_note'
```
