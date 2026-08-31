import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ReconciliationHealthRing,
  StatusDistributionViz,
} from "../components/charts/ReconCharts";
import {
  EngineStatus,
  ErrorState,
  InteractiveRow,
  LoadingState,
  PageHeader,
  PrimaryCTA,
  SectionLabel,
} from "../components/ui/primitives";
import { useHealth, useReconciliationReport } from "../hooks/useApi";
import { CONSOLE_PATHS, getSummaryExceptions, SUMMARY_TO_EXCEPTION_FILTER } from "../utils/format";

export function DashboardPage() {
  const { data, loading, error, refreshing, refetch } = useReconciliationReport();
  const health = useHealth();
  const navigate = useNavigate();
  const [refreshSuccess, setRefreshSuccess] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  const exceptions = useMemo(
    () => (data ? getSummaryExceptions(data.summary) : []),
    [data],
  );

  const handleRefresh = async () => {
    setRefreshSuccess(false);
    setIsRunning(true);
    try {
      await refetch({ silent: true });
      setRefreshSuccess(true);
      window.setTimeout(() => setRefreshSuccess(false), 3000);
    } catch {
      // Error surfaced via hook state; keep page mounted.
    } finally {
      setIsRunning(false);
    }
  };

  if (loading && !data) return <LoadingState />;
  if (error || !data) return <ErrorState message={error ?? "No data"} onRetry={() => void refetch()} />;

  const reconciliationRate =
    data.summary.total_orders > 0
      ? data.summary.reconciled_orders / data.summary.total_orders
      : 0;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Reconciliation Command Center"
        subtitle="Monitor transaction integrity, reconciliation health and operational exceptions."
        action={
          <PrimaryCTA
            onClick={() => void handleRefresh()}
            loading={isRunning || refreshing}
            success={refreshSuccess}
            label="Run reconciliation"
          />
        }
      />

      <div className="mb-10 flex items-center gap-3 text-sm text-[var(--color-muted)]">
        <EngineStatus online={health.data?.status === "ok" && !health.error} />
        <span className="text-[var(--color-border)]">·</span>
        <span>Last run · {data.metadata.generated_at}</span>
        <span className="text-[var(--color-border)]">·</span>
        <span>
          {data.metadata.currency} · {data.summary.total_orders} orders
        </span>
        {refreshSuccess ? (
          <>
            <span className="text-[var(--color-border)]">·</span>
            <span className="font-medium text-[var(--color-success)]">Data refreshed</span>
          </>
        ) : null}
      </div>

      <section className="mb-14 border-b border-[var(--color-border)] pb-14">
        <SectionLabel title="Reconciliation Health" />
        <ReconciliationHealthRing
          rate={reconciliationRate}
          reconciled={data.summary.reconciled_orders}
          unreconciled={data.summary.unreconciled_orders}
          total={data.summary.total_orders}
        />
      </section>

      <div className="mb-14 grid gap-12 lg:grid-cols-2">
        <section>
          <SectionLabel title="Status Distribution" description="Breakdown by reconciliation outcome" />
          <StatusDistributionViz statusCounts={data.status_counts} />
        </section>

        <section>
          <SectionLabel
            title="Exceptions Requiring Attention"
            description="Operational issues detected in the current run"
            action={
              <button
                type="button"
                onClick={() => navigate(CONSOLE_PATHS.exceptions)}
                className="cursor-pointer text-xs font-medium text-[var(--color-accent)] transition hover:text-[var(--color-accent-hover)]"
              >
                View all →
              </button>
            }
          />
          <div className="rounded-lg border border-[var(--color-border)] bg-white px-4">
            {exceptions.length ? (
              exceptions.map((item) => (
                <InteractiveRow
                  key={item.key}
                  label={item.label}
                  count={item.count}
                  severity={item.severity}
                  onClick={() => {
                    const filter = SUMMARY_TO_EXCEPTION_FILTER[item.key];
                    navigate(
                      filter
                        ? `${CONSOLE_PATHS.exceptions}?filter=${encodeURIComponent(filter)}`
                        : CONSOLE_PATHS.exceptions,
                    );
                  }}
                />
              ))
            ) : (
              <p className="py-8 text-center text-sm text-[var(--color-muted)]">
                No exceptions detected in this run.
              </p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
