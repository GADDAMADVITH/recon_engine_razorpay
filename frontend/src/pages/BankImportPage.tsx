import { ChevronRight, Upload } from "lucide-react";
import { cn } from "../utils/format";
import { useCallback, useRef, useState } from "react";
import { api, ApiClientError } from "../api/client";
import { AgentDecisionChip } from "../components/finance/AgentDecisionSection";
import { FinanceControllerPanel } from "../components/finance/FinanceControllerPanel";
import { OrderDetailDrawer } from "../components/orders/OrderDetailDrawer";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  MetricCard,
  PageHeader,
  SectionLabel,
  StatusBadge,
} from "../components/ui/primitives";
import type {
  FinanceAgentRunResponse,
  FinanceControllerDecision,
  OrderResult,
  ReconciliationReport,
} from "../types/api";
import { decisionFromTrace } from "../utils/financeAgent";

const DEMO_CSV_ROWS = `bank_transaction_id,settlement_ref,amount,transaction_date,description
DEMO_BNK_0001,SET_0001,370605,2026-08-08T02:00:00,DEMO SYNTHETIC - Payout ORD_0001 correct amount
DEMO_BNK_0002,SET_0002,61713,2026-08-15T20:24:00,DEMO SYNTHETIC - Payout ORD_0002 deliberate amount mismatch
DEMO_BNK_0004,SET_0029,254473,2026-08-12T01:01:00,DEMO SYNTHETIC - Payout ORD_0033 refund-adjusted amount
`;

const DEMO_SCENARIOS = [
  {
    id: "ORD_0001",
    label: "Reconciled",
    description: "Order, settlement, and bank amounts match.",
    tone: "ok" as const,
    primaryFailure: false,
  },
  {
    id: "ORD_0002",
    label: "Bank Amount Mismatch",
    description: "Primary failure demo — bank payout does not match settlement net.",
    tone: "error" as const,
    primaryFailure: true,
  },
  {
    id: "ORD_0003",
    label: "Missing Bank",
    description: "Settlement exists, but no bank row was imported.",
    tone: "warning" as const,
    primaryFailure: false,
  },
  {
    id: "ORD_0033",
    label: "Refund Adjusted",
    description: "Refund is correctly reflected in settlement.",
    tone: "ok" as const,
    primaryFailure: false,
  },
  {
    id: "ORD_0024",
    label: "Missing Settlement",
    description: "Order has no linked settlement record.",
    tone: "error" as const,
    primaryFailure: false,
  },
] as const;

export const DEMO_SCENARIO_LABELS: Record<string, string> = Object.fromEntries(
  DEMO_SCENARIOS.map((scenario) => [scenario.id, scenario.label]),
);

const REQUIRED_COLUMNS = [
  "bank_transaction_id",
  "settlement_ref",
  "amount",
  "transaction_date",
  "description",
];

function ResultsTable({
  orders,
  onSelect,
  testId = "import-results-table",
}: {
  orders: OrderResult[];
  onSelect: (order: OrderResult) => void;
  testId?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[700px] text-left text-sm" data-testid={testId}>
        <thead>
          <tr className="border-b border-[var(--color-border)] text-[12px] font-medium text-[var(--color-muted)]">
            <th className="pb-3 pr-4 font-medium">Order</th>
            <th className="pb-3 pr-4 font-medium">Status</th>
            <th className="pb-3 pr-4 font-medium">Confidence</th>
            <th className="pb-3 pr-4 font-medium">Settlement</th>
            <th className="pb-3 pr-4 font-medium">Bank</th>
            <th className="pb-3 font-medium" aria-label="Action" />
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr
              key={order.order_id}
              role="button"
              tabIndex={0}
              className="group cursor-pointer border-b border-[var(--color-border)] transition-colors hover:bg-[rgba(37,99,235,0.02)] focus-visible:bg-[rgba(37,99,235,0.02)] focus-visible:outline-none"
              onClick={() => onSelect(order)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(order);
                }
              }}
            >
              <td className="py-4 pr-4 font-mono text-xs font-medium">{order.order_id}</td>
              <td className="py-4 pr-4">
                <StatusBadge status={order.status} reconciled={order.reconciled} />
              </td>
              <td className="py-4 pr-4 tabular-nums text-sm">
                <span
                  className={cn(
                    "mr-1.5 inline-block h-1.5 w-1.5 rounded-full",
                    order.confidence_score >= 80
                      ? "bg-[var(--color-success)]"
                      : order.confidence_score >= 50
                        ? "bg-[var(--color-warning)]"
                        : "bg-[var(--color-danger)]",
                  )}
                />
                {order.confidence_score}%
              </td>
              <td className="py-4 pr-4 font-mono text-xs text-[var(--color-muted)]">
                {order.primary_settlement_id ?? "—"}
              </td>
              <td className="py-4 pr-4 font-mono text-xs text-[var(--color-muted)]">
                {order.valid_bank_transaction_id ?? "—"}
              </td>
              <td className="py-4">
                <ChevronRight className="h-4 w-4 text-[var(--color-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-ink)]" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DemoScenarioCards({
  orders,
  decisionsByOrderId,
  onSelect,
}: {
  orders: OrderResult[];
  decisionsByOrderId: Map<string, FinanceControllerDecision>;
  onSelect: (order: OrderResult) => void;
}) {
  const byId = new Map(orders.map((order) => [order.order_id, order]));

  return (
    <div
      className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"
      data-testid="demo-scenarios-table"
    >
      {DEMO_SCENARIOS.map((scenario) => {
        const order = byId.get(scenario.id);
        if (!order) return null;
        const decision = decisionsByOrderId.get(scenario.id);
        const toneClass =
          scenario.tone === "ok"
            ? "border-[var(--color-success)]/25 hover:border-[var(--color-success)]/50"
            : scenario.tone === "warning"
              ? "border-[var(--color-warning)]/30 hover:border-[var(--color-warning)]/55"
              : "border-[var(--color-danger)]/25 hover:border-[var(--color-danger)]/50";
        return (
          <button
            key={scenario.id}
            type="button"
            aria-label={`Open ${scenario.id} — ${scenario.label}`}
            onClick={() => onSelect(order)}
            className={cn(
              "group flex flex-col rounded-xl border bg-white p-4 text-left shadow-[0_1px_3px_rgba(11,27,43,0.04)] transition hover:shadow-[0_6px_18px_rgba(11,27,43,0.07)]",
              toneClass,
            )}
          >
            <span className="font-mono text-[11px] font-medium text-[var(--color-muted)]">
              {scenario.id}
            </span>
            {scenario.primaryFailure ? (
              <span
                className="mt-1 inline-flex w-fit rounded-md bg-[var(--color-danger)]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-danger)]"
                data-testid="primary-failure-badge"
              >
                Primary failure demo
              </span>
            ) : null}
            <span className="mt-2 text-sm font-semibold tracking-tight text-[var(--color-ink)]">
              {scenario.label}
            </span>
            <span className="mt-1 min-h-[2.5rem] text-xs leading-relaxed text-[var(--color-muted)]">
              {scenario.description}
            </span>
            <span className="mt-3">
              <StatusBadge status={order.status} reconciled={order.reconciled} />
            </span>
            <AgentDecisionChip decision={decision} />
            <span className="mt-3 inline-flex items-center text-[11px] font-medium text-[var(--color-accent)]">
              Open order
              <ChevronRight className="ml-0.5 h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function BankImportPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ReconciliationReport | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<OrderResult | null>(null);
  const [agentBatch, setAgentBatch] = useState<FinanceAgentRunResponse | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);

  const runAgentOnResults = async (orderResults: OrderResult[]) => {
    setAgentLoading(true);
    setAgentError(null);
    try {
      const batch = await api.runFinanceControllerAgent({ order_results: orderResults });
      setAgentBatch(batch);
    } catch (err) {
      setAgentBatch(null);
      setAgentError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to run Finance Controller on imported results.",
      );
    } finally {
      setAgentLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setError(null);
    setReport(null);
    setAgentBatch(null);
    setAgentError(null);
  };

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) {
      setFile(f);
      setError(null);
      setReport(null);
      setAgentBatch(null);
      setAgentError(null);
    }
  }, []);

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const runImport = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setReport(null);
    setAgentBatch(null);
    setAgentError(null);
    try {
      const result = await api.importBankCsv(file);
      setReport(result);
      await runAgentOnResults(result.order_results);
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to import bank CSV.",
      );
    } finally {
      setLoading(false);
    }
  };

  const loadDemo = () => {
    const blob = new Blob([DEMO_CSV_ROWS], { type: "text/csv" });
    const demoFile = new File([blob], "demo_bank.csv", { type: "text/csv" });
    setFile(demoFile);
    setError(null);
    setReport(null);
    setAgentBatch(null);
    setAgentError(null);
  };

  const reset = () => {
    setFile(null);
    setError(null);
    setReport(null);
    setAgentBatch(null);
    setAgentError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const decisionsByOrderId = new Map(
    (agentBatch?.decisions ?? []).map((d) => [d.order_id, decisionFromTrace(d)]),
  );
  const tracesByOrderId = new Map(
    (agentBatch?.decisions ?? []).map((d) => [d.order_id, d]),
  );
  const selectedDecision = selectedOrder
    ? decisionsByOrderId.get(selectedOrder.order_id) ?? null
    : null;
  const selectedTrace = selectedOrder
    ? tracesByOrderId.get(selectedOrder.order_id) ?? null
    : null;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Bank CSV Import"
        subtitle="Reconcile a bank statement against production orders. The primary demo uses a deterministic CSV — not live Razorpay settlements."
      />

      <section className="mb-8 rounded-xl border border-[var(--color-border)] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)]" data-testid="demo-walkthrough-hint">
        <p className="text-[11px] font-medium tracking-wide text-[var(--color-muted)]">
          Evaluator walkthrough
        </p>
        <p className="mt-1 text-sm leading-relaxed text-[var(--color-ink)]">
          Load Demo CSV → Run Reconciliation → open a scenario → Pipeline → Agent Decision →
          Approve/Reject → Recorded action → Audit Trail. Use{" "}
          <span className="font-mono text-xs">ORD_0002</span> as the primary failure demo.
          Decisions come from the API — not hardcoded in the UI.
        </p>
        <p className="mt-2 text-xs text-[var(--color-muted)]">
          Human approval required · Money moved: false · Gemini is explanation/chat only
        </p>
      </section>

      <section className="mb-8">
        <SectionLabel
          title="Bank CSV"
          description={`Required columns: ${REQUIRED_COLUMNS.join(", ")}`}
        />

        <div
          role="region"
          aria-label="Bank CSV upload area"
          className="flex flex-col items-center gap-4 rounded-xl border-2 border-dashed border-[var(--color-border)] bg-white px-6 py-10 text-center"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <Upload className="h-10 w-10 text-[var(--color-muted)]" strokeWidth={1.25} />
          <div>
            <p className="text-sm font-medium text-[var(--color-ink)]">
              Drop a bank CSV here or{" "}
              <button
                type="button"
                className="cursor-pointer text-[var(--color-accent)] hover:underline"
                onClick={() => fileInputRef.current?.click()}
              >
                browse
              </button>
            </p>
            <p className="mt-1 text-xs text-[var(--color-muted)]">CSV format only · demo file is synthetic</p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            aria-label="Upload bank CSV"
            onChange={handleFileChange}
          />
        </div>

        {file ? (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="rounded-md border border-[var(--color-border)] bg-white px-3 py-1.5 font-mono text-xs">
              {file.name} ({(file.size / 1024).toFixed(1)} KB)
            </span>
            <Button variant="ghost" size="sm" onClick={reset}>
              Remove
            </Button>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-3">
          <Button
            variant={file ? "secondary" : "primary"}
            onClick={loadDemo}
          >
            Load Demo CSV
          </Button>
          <Button
            variant={file ? "primary" : "secondary"}
            disabled={!file || loading}
            onClick={() => void runImport()}
            aria-label="Run reconciliation"
          >
            {loading ? "Importing…" : "Run Reconciliation"}
          </Button>
        </div>
      </section>

      {error ? (
        <div className="mb-8">
          <ErrorState message={error} onRetry={() => void runImport()} />
        </div>
      ) : null}

      {loading ? <LoadingState label="Running reconciliation against the uploaded bank CSV…" /> : null}

      {report && !loading ? (
        <>
          <section className="mb-8">
            <SectionLabel
              title="Reconciliation Summary"
              description={`Bank source: ${report.metadata.bank_source ?? "uploaded_csv"} · ${report.metadata.bank_rows_imported ?? "?"} bank rows imported`}
            />
            <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              <MetricCard value={report.summary.total_orders} label="Orders" accent="brand" />
              <MetricCard
                value={report.summary.reconciled_orders}
                label="Reconciled"
                accent="success"
              />
              <MetricCard
                value={report.summary.unreconciled_orders}
                label="Unreconciled"
                accent={report.summary.unreconciled_orders > 0 ? "danger" : "default"}
              />
              <MetricCard
                value={report.summary.missing_bank_transactions ?? 0}
                label="Missing bank"
                accent={(report.summary.missing_bank_transactions ?? 0) > 0 ? "warning" : "default"}
              />
              <MetricCard
                value={report.summary.bank_amount_mismatches ?? 0}
                label="Bank mismatches"
                accent={(report.summary.bank_amount_mismatches ?? 0) > 0 ? "danger" : "default"}
              />
            </div>
          </section>

          <FinanceControllerPanel
            data={agentBatch}
            loading={agentLoading}
            error={agentError}
            onRetry={() => void runAgentOnResults(report.order_results)}
            orderResults={report.order_results}
          />

          <section className="mb-8">
            <SectionLabel
              title="Demo scenarios"
              description="Five curated outcomes from the deterministic demo CSV. Agent decisions use the same imported order_results as Pipeline and Audit Trail."
            />
            {(() => {
              const demoIds = new Set<string>(DEMO_SCENARIOS.map((scenario) => scenario.id));
              const demoOrders = report.order_results.filter((order) => demoIds.has(order.order_id));
              if (demoOrders.length === 0) {
                return (
                  <EmptyState
                    title="Demo orders missing"
                    description="The import report did not include the expected demo order IDs."
                  />
                );
              }
              return (
                <DemoScenarioCards
                  orders={demoOrders}
                  decisionsByOrderId={decisionsByOrderId}
                  onSelect={setSelectedOrder}
                />
              );
            })()}
          </section>

          <section>
            <details className="group rounded-xl border border-[var(--color-border)] bg-white shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
              <summary className="cursor-pointer list-none px-5 py-4 text-sm font-medium text-[var(--color-ink)] marker:content-none [&::-webkit-details-marker]:hidden">
                <span className="flex items-center justify-between gap-3">
                  <span>
                    All order results
                    <span className="ml-2 text-xs font-normal text-[var(--color-muted)]">
                      {report.order_results.length} orders from the production set
                    </span>
                  </span>
                  <ChevronRight className="h-4 w-4 text-[var(--color-muted)] transition group-open:rotate-90" />
                </span>
              </summary>
              {report.order_results.length === 0 ? (
                <div className="px-5 pb-5">
                  <EmptyState title="No orders" description="The reconciliation returned no order results." />
                </div>
              ) : (
                <div className="overflow-x-auto px-4 pb-3">
                  <ResultsTable
                    orders={report.order_results}
                    onSelect={setSelectedOrder}
                    testId="import-results-table"
                  />
                </div>
              )}
            </details>
          </section>
        </>
      ) : null}

      <OrderDetailDrawer
        order={selectedOrder}
        scenarioLabel={selectedOrder ? DEMO_SCENARIO_LABELS[selectedOrder.order_id] : undefined}
        agentDecision={selectedDecision}
        agentDecisionTrace={selectedTrace}
        onClose={() => setSelectedOrder(null)}
      />
    </div>
  );
}
