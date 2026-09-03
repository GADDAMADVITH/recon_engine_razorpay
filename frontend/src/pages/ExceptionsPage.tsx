import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { OrderDetailDrawer } from "../components/orders/OrderDetailDrawer";
import { RazorpayBankLimitationBanner } from "../components/sources/DataSourceBar";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  SeverityBadge,
} from "../components/ui/primitives";
import { useConsoleReport } from "../context/ConsoleReportContext";
import type { OrderResult } from "../types/api";
import { SEVERE_EXCEPTIONS, type ExceptionType } from "../types/reconciliation";
import { formatExceptionLabel, getExceptionSeverity } from "../utils/format";

const EXCEPTION_DESCRIPTIONS: Partial<Record<ExceptionType, string>> = {
  MISSING_SETTLEMENT: "Order has no linked settlement record in the dataset.",
  MISSING_BANK_TRANSACTION: "Settlement exists but no matching bank transaction was found.",
  SETTLEMENT_AMOUNT_MISMATCH: "Settlement gross amount does not match the order amount.",
  BANK_AMOUNT_MISMATCH: "Bank transaction amount does not match settlement net.",
  TIMESTAMP_OUTSIDE_TOLERANCE: "Settlement and bank timestamps exceed configured tolerance.",
  REFUND_NOT_REFLECTED: "Refund was issued but settlement was not adjusted accordingly.",
  DUPLICATE_SETTLEMENT: "Multiple settlements reference the same order.",
  DUPLICATE_BANK_TRANSACTION: "Duplicate bank entries detected for the same reference.",
  ORPHAN_BANK_TRANSACTION: "Bank transaction with no resolvable order link.",
  REFERENCE_VARIATION: "Settlement reference uses a non-canonical format.",
  REFUND_ADJUSTED: "Settlement was correctly adjusted for refund.",
  TIMESTAMP_WITHIN_TOLERANCE: "Timestamps differ but remain within tolerance window.",
};

export function ExceptionsPage() {
  const {
    isCsv,
    isRazorpay,
    report: data,
    csvLoading,
    csvError,
    refetchCsv,
    razorpay,
  } = useConsoleReport();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filter, setFilter] = useState(() => searchParams.get("filter") ?? "all");
  const [selectedOrder, setSelectedOrder] = useState<OrderResult | null>(null);
  const [expandedType, setExpandedType] = useState<string | null>(
    () => searchParams.get("filter"),
  );

  useEffect(() => {
    const param = searchParams.get("filter");
    if (param) {
      setFilter(param);
      setExpandedType(param);
    }
  }, [searchParams]);

  const grouped = useMemo(() => {
    if (!data) return {} as Record<string, { count: number; orders: OrderResult[] }>;
    const map: Record<string, { count: number; orders: OrderResult[] }> = {};
    for (const order of data.order_results) {
      for (const exception of order.exceptions) {
        if (!map[exception.type]) map[exception.type] = { count: 0, orders: [] };
        map[exception.type].count += 1;
        if (!map[exception.type].orders.find((o) => o.order_id === order.order_id)) {
          map[exception.type].orders.push(order);
        }
      }
    }
    for (const global of data.global_exceptions) {
      if (!map[global.type]) map[global.type] = { count: 0, orders: [] };
      map[global.type].count += 1;
    }
    return map;
  }, [data]);

  const sortedTypes = useMemo(
    () =>
      Object.entries(grouped).sort(([typeA, a], [typeB, b]) => {
        const sevA = SEVERE_EXCEPTIONS.includes(typeA as ExceptionType) ? 0 : 1;
        const sevB = SEVERE_EXCEPTIONS.includes(typeB as ExceptionType) ? 0 : 1;
        return sevA - sevB || b.count - a.count;
      }),
    [grouped],
  );

  const visibleTypes = sortedTypes.filter(([type]) =>
    filter === "all" ? true : type === filter,
  );

  const applyFilter = (type: string) => {
    setFilter(type);
    if (type === "all") {
      setSearchParams({});
      setExpandedType(null);
    } else {
      setSearchParams({ filter: type });
      setExpandedType(type);
    }
  };

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
          title="Exceptions"
          subtitle="Investigate reconciliation failures and anomalies."
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

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Exceptions"
        subtitle="Investigate reconciliation failures and anomalies."
      />

      {isRazorpay ? <RazorpayBankLimitationBanner /> : null}

      <div className="mb-8 flex flex-wrap gap-2">
        <Button
          variant={filter === "all" ? "primary" : "secondary"}
          size="sm"
          onClick={() => applyFilter("all")}
        >
          All ({Object.keys(grouped).length})
        </Button>
        {Object.keys(grouped).map((type) => (
          <Button
            key={type}
            variant={filter === type ? "primary" : "secondary"}
            size="sm"
            onClick={() => applyFilter(type)}
          >
            {formatExceptionLabel(type)}
          </Button>
        ))}
      </div>

      <div className="space-y-px overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-[0_1px_0_rgba(11,27,43,0.04),0_8px_24px_rgba(11,27,43,0.04)]">
        {visibleTypes.map(([type, info]) => {
          const severity = getExceptionSeverity(type);
          const isExpanded = expandedType === type;
          const description =
            EXCEPTION_DESCRIPTIONS[type as ExceptionType] ??
            "Reconciliation exception detected during engine processing.";

          return (
            <div key={type} className="bg-white">
              <button
                type="button"
                onClick={() => setExpandedType(isExpanded ? null : type)}
                className="flex w-full cursor-pointer items-center gap-4 px-5 py-5 text-left transition hover:bg-black/[0.02]"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-3">
                    <p className="text-[15px] font-medium">{formatExceptionLabel(type)}</p>
                    <SeverityBadge severity={severity} />
                  </div>
                  <p className="mt-1 text-sm text-[var(--color-muted)]">{description}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-xl font-semibold tabular-nums">{info.count}</p>
                  <p className="text-xs text-[var(--color-muted)]">
                    {info.orders.length} order{info.orders.length === 1 ? "" : "s"}
                  </p>
                </div>
                <ChevronRight
                  className={`h-4 w-4 shrink-0 text-[var(--color-muted)] transition-transform ${isExpanded ? "rotate-90" : ""}`}
                />
              </button>

              {isExpanded ? (
                <div className="border-t border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-4">
                  <div className="mb-3 flex items-center justify-between">
                    <p className="text-xs font-medium text-[var(--color-muted)]">
                      Affected orders
                    </p>
                    {info.orders[0] ? (
                      <button
                        type="button"
                        onClick={() => setSelectedOrder(info.orders[0])}
                        className="cursor-pointer text-xs font-medium text-[var(--color-accent)] hover:text-[var(--color-accent-hover)]"
                      >
                        View orders →
                      </button>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {info.orders.slice(0, 12).map((order) => (
                      <button
                        key={order.order_id}
                        type="button"
                        onClick={() => setSelectedOrder(order)}
                        className="cursor-pointer rounded-md border border-[var(--color-border)] bg-white px-3 py-1.5 font-mono text-xs transition hover:border-black/20"
                      >
                        {order.order_id}
                      </button>
                    ))}
                    {info.orders.length > 12 ? (
                      <span className="px-2 py-1.5 text-xs text-[var(--color-muted)]">
                        +{info.orders.length - 12} more
                      </span>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {visibleTypes.length === 0 ? (
        <p className="py-16 text-center text-sm text-[var(--color-muted)]">
          No exceptions match the selected filter.
        </p>
      ) : null}

      <OrderDetailDrawer order={selectedOrder} onClose={() => setSelectedOrder(null)} />
    </div>
  );
}
