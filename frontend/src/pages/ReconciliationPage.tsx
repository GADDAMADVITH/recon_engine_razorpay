import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { OrderDetailDrawer } from "../components/orders/OrderDetailDrawer";
import { RazorpayBankLimitationBanner } from "../components/sources/DataSourceBar";
import {
  Button,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  PageHeader,
  Select,
  StatPill,
  StatusBadge,
} from "../components/ui/primitives";
import { useConsoleReport } from "../context/ConsoleReportContext";
import type { OrderResult } from "../types/api";
import { formatPaise } from "../utils/format";

const PAGE_SIZE = 12;

export function ReconciliationPage() {
  const {
    isCsv,
    isRazorpay,
    report: data,
    csvLoading,
    csvError,
    refetchCsv,
    razorpay,
  } = useConsoleReport();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [confidenceFilter, setConfidenceFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [selectedOrder, setSelectedOrder] = useState<OrderResult | null>(null);

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.order_results.filter((order) => {
      const matchesSearch = order.order_id.toLowerCase().includes(search.toLowerCase());
      const matchesStatus = statusFilter === "all" || order.status === statusFilter;
      const matchesConfidence =
        confidenceFilter === "all" ||
        (confidenceFilter === "high" && order.confidence_score >= 80) ||
        (confidenceFilter === "medium" &&
          order.confidence_score >= 50 &&
          order.confidence_score < 80) ||
        (confidenceFilter === "low" && order.confidence_score < 50);
      return matchesSearch && matchesStatus && matchesConfidence;
    });
  }, [data, search, statusFilter, confidenceFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const statuses = data ? Object.keys(data.status_counts) : [];

  if (isCsv && csvLoading && !data) return <LoadingState />;
  if (isCsv && (csvError || !data)) {
    return <ErrorState message={csvError ?? "No data"} onRetry={() => void refetchCsv()} />;
  }
  if (isRazorpay && razorpay.loading && !data) {
    return <LoadingState label="Syncing Razorpay data..." />;
  }
  if (isRazorpay && razorpay.error && !data) {
    return <ErrorState message={razorpay.error} onRetry={() => void razorpay.sync()} />;
  }
  if (isRazorpay && !data) {
    return (
      <div className="mx-auto max-w-6xl">
        <PageHeader
          title="Reconciliation"
          subtitle="Review order-level reconciliation outcomes across the full dataset."
        />
        <RazorpayBankLimitationBanner />
        <EmptyState
          title={razorpay.empty ? "No Razorpay orders to reconcile" : "No Razorpay sync yet"}
          description={
            razorpay.empty
              ? "The last Razorpay sync returned no orders."
              : "Select Razorpay on the Command Center and click “Sync from Razorpay” first."
          }
        />
      </div>
    );
  }
  if (!data) return <LoadingState />;

  const attentionCount = data.summary.unreconciled_orders;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Reconciliation"
        subtitle="Review order-level reconciliation outcomes across the full dataset."
      />

      {isRazorpay ? <RazorpayBankLimitationBanner /> : null}

      <div className="mb-8 flex flex-wrap items-center gap-8 border-b border-[var(--color-border)] pb-6">
        <StatPill value={data.summary.total_orders} label="Orders" />
        <StatPill value={data.summary.reconciled_orders} label="Reconciled" />
        <StatPill value={attentionCount} label="Requiring attention" />
        <StatPill value={isCsv ? "CSV" : "Razorpay"} label="Source" />
      </div>

      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        <Input
          type="search"
          placeholder="Search order ID"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        <Select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="all">All statuses</option>
          {statuses.map((status) => (
            <option key={status} value={status}>
              {status.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
        <Select
          value={confidenceFilter}
          onChange={(e) => {
            setConfidenceFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="all">All confidence levels</option>
          <option value="high">High (80+)</option>
          <option value="medium">Medium (50–79)</option>
          <option value="low">Low (&lt;50)</option>
        </Select>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[800px] text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--color-muted)]">
              <th className="pb-3 pr-4 font-medium">Order</th>
              <th className="pb-3 pr-4 font-medium">Status</th>
              <th className="pb-3 pr-4 font-medium">Confidence</th>
              <th className="pb-3 pr-4 font-medium">Settlement</th>
              <th className="pb-3 pr-4 font-medium">Bank</th>
              <th className="pb-3 pr-4 font-medium">Refund</th>
              <th className="pb-3 pr-4 font-medium">Timestamp</th>
              <th className="pb-3 font-medium" aria-label="Action" />
            </tr>
          </thead>
          <tbody>
            {pageItems.map((order) => (
              <tr
                key={order.order_id}
                role="button"
                tabIndex={0}
                className="group cursor-pointer border-b border-[var(--color-border)] transition-colors hover:bg-black/[0.02] focus-visible:bg-black/[0.02] focus-visible:outline-none"
                onClick={() => setSelectedOrder(order)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelectedOrder(order);
                  }
                }}
              >
                <td className="py-4 pr-4 font-medium">{order.order_id}</td>
                <td className="py-4 pr-4">
                  <StatusBadge status={order.status} reconciled={order.reconciled} />
                </td>
                <td className="py-4 pr-4 tabular-nums">{order.confidence_score}</td>
                <td className="py-4 pr-4 font-mono text-xs text-[var(--color-muted)]">
                  {order.primary_settlement_id ?? "—"}
                </td>
                <td className="py-4 pr-4 font-mono text-xs text-[var(--color-muted)]">
                  {order.valid_bank_transaction_id ?? "—"}
                </td>
                <td className="py-4 pr-4 tabular-nums">
                  {order.total_refund_paise > 0 ? formatPaise(order.total_refund_paise) : "—"}
                </td>
                <td className="py-4 pr-4 tabular-nums text-[var(--color-muted)]">
                  {order.timestamp_comparison.difference_hours != null
                    ? `${order.timestamp_comparison.difference_hours}h`
                    : "—"}
                </td>
                <td className="py-4">
                  <ChevronRight className="h-4 w-4 text-[var(--color-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-ink)]" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pageItems.length === 0 ? (
        <p className="py-10 text-center text-sm text-[var(--color-muted)]">
          No orders match the current filters.
        </p>
      ) : null}

      <div className="mt-6 flex items-center justify-between">
        <p className="text-xs text-[var(--color-muted)]">
          {filtered.length === 0
            ? "0 orders"
            : `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, filtered.length)} of ${filtered.length} orders`}
        </p>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next
          </Button>
        </div>
      </div>

      <OrderDetailDrawer order={selectedOrder} onClose={() => setSelectedOrder(null)} />
    </div>
  );
}
