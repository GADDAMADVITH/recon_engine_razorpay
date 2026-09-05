import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ReconciliationHealthRing,
  StatusDistributionViz,
} from "../components/charts/ReconCharts";
import { FinanceControllerPanel } from "../components/finance/FinanceControllerPanel";
import {
  DataSourceSelector,
  RazorpayBankLimitationBanner,
} from "../components/sources/DataSourceBar";
import { RazorpayDemoPanel } from "../components/sources/RazorpayDemoPanel";
import {
  Button,
  EmptyState,
  EngineStatus,
  ErrorState,
  InteractiveRow,
  LoadingState,
  MetricCard,
  PageHeader,
  PrimaryCTA,
  SectionLabel,
} from "../components/ui/primitives";
import { useConsoleReport } from "../context/ConsoleReportContext";
import { useFinanceControllerAgentRun, useHealth } from "../hooks/useApi";
import { CONSOLE_PATHS, getSummaryExceptions, SUMMARY_TO_EXCEPTION_FILTER } from "../utils/format";
import type { ReconciliationReport } from "../types/api";

function DashboardReportBody({
  data,
  onNavigateExceptions,
}: {
  data: ReconciliationReport;
  onNavigateExceptions: (filter?: string) => void;
}) {
  const exceptions = useMemo(() => getSummaryExceptions(data.summary), [data]);
  const reconciliationRate =
    data.summary.total_orders > 0
      ? data.summary.reconciled_orders / data.summary.total_orders
      : 0;
      const finance = useFinanceControllerAgentRun(data.order_results, { autoRun: false });

  return (
    <>
      {/* KPI cards */}
      <div className="mb-10 grid grid-cols-2 gap-3 sm:mb-12 sm:grid-cols-4 sm:gap-4">
        <MetricCard value={data.summary.total_orders} label="Total orders" accent="brand" />
        <MetricCard
          value={data.summary.reconciled_orders}
          label="Reconciled"
          accent="success"
        />
        <MetricCard
          value={data.summary.unreconciled_orders}
          label="Unreconciled"
          accent={data.summary.unreconciled_orders > 0 ? "danger" : "default"}
        />
        <MetricCard
          value={`${Math.round(reconciliationRate * 100)}%`}
          label="Match rate"
          accent={reconciliationRate >= 0.95 ? "success" : reconciliationRate >= 0.7 ? "warning" : "danger"}
        />
      </div>

      <section className="mb-10 border-b border-[var(--color-border)] pb-10 sm:mb-12 sm:pb-12">
        <SectionLabel title="Reconciliation Health" />
        <ReconciliationHealthRing
          rate={reconciliationRate}
          reconciled={data.summary.reconciled_orders}
          unreconciled={data.summary.unreconciled_orders}
          total={data.summary.total_orders}
        />
      </section>

      <FinanceControllerPanel
        data={finance.data}
        loading={finance.loading}
        error={finance.error}
        onRetry={() => void finance.refetch()}
        orderResults={data.order_results}
        requireManualRun
        onAgentRunComplete={(run) => finance.setData(run)}
        onAgentRunClear={() => finance.setData(null)}
      />

      <div className="mb-10 grid gap-10 lg:mb-12 lg:grid-cols-2 lg:gap-12">
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
                onClick={() => onNavigateExceptions()}
                className="cursor-pointer text-xs font-medium text-[var(--color-accent)] transition hover:text-[var(--color-accent-hover)]"
              >
                View all →
              </button>
            }
          />
          <div className="rounded-xl border border-[var(--color-border)] bg-white px-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
            {exceptions.length ? (
              exceptions.map((item) => (
                <InteractiveRow
                  key={item.key}
                  label={item.label}
                  count={item.count}
                  severity={item.severity}
                  onClick={() => {
                    const filter = SUMMARY_TO_EXCEPTION_FILTER[item.key];
                    onNavigateExceptions(filter);
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
    </>
  );
}

export function DashboardPage() {
  const {
    source,
    setSource,
    isCsv,
    isRazorpay,
    report,
    csvLoading,
    csvError,
    csvRefreshing,
    refetchCsv,
    razorpay,
  } = useConsoleReport();
  const health = useHealth();
  const navigate = useNavigate();
  const [refreshSuccess, setRefreshSuccess] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  const handleCsvRefresh = async () => {
    setRefreshSuccess(false);
    setIsRunning(true);
    try {
      await refetchCsv({ silent: true });
      setRefreshSuccess(true);
      window.setTimeout(() => setRefreshSuccess(false), 3000);
    } catch {
      // Error surfaced via hook state; keep page mounted.
    } finally {
      setIsRunning(false);
    }
  };

  const navigateExceptions = (filter?: string) => {
    navigate(
      filter
        ? `${CONSOLE_PATHS.exceptions}?filter=${encodeURIComponent(filter)}`
        : CONSOLE_PATHS.exceptions,
    );
  };

  const showCsvLoading = isCsv && csvLoading && !report;
  const showCsvError = isCsv && (csvError || !report);
  const showRazorpayLoading = isRazorpay && razorpay.loading && !report;
  const showRazorpayError = isRazorpay && Boolean(razorpay.error) && !report;
  const showRazorpayEmpty = isRazorpay && razorpay.empty && !report;
  const showRazorpayIdle =
    isRazorpay && !razorpay.loading && !razorpay.error && !razorpay.empty && !report;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Reconciliation Command Center"
        subtitle="Monitor transaction integrity, reconciliation health and operational exceptions."
        action={
          isCsv ? (
            <PrimaryCTA
              onClick={() => void handleCsvRefresh()}
              loading={isRunning || csvRefreshing}
              success={refreshSuccess}
              label="Run reconciliation"
            />
          ) : (
            <PrimaryCTA
              onClick={() => void razorpay.sync()}
              loading={razorpay.loading}
              label="Sync from Razorpay"
            />
          )
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <DataSourceSelector source={source} onChange={setSource} />
        <span className="text-xs text-[var(--color-muted)]">
          {isCsv ? "Local CSV dataset" : "Live Razorpay sync (explicit)"}
        </span>
      </div>

      {isCsv ? (
        <section className="mb-8 flex flex-col gap-3 rounded-xl border border-[var(--color-border)] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)] sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[13px] font-medium tracking-tight text-[var(--color-ink)]">
              Demo walkthrough
            </p>
            <p className="mt-1 text-sm text-[var(--color-ink)]">
              Bank Import uses a deterministic CSV. It does not wait on live Razorpay settlements.
            </p>
          </div>
          <Button variant="secondary" onClick={() => navigate(CONSOLE_PATHS.bankImport)}>
            Open Bank Import
          </Button>
        </section>
      ) : null}

      {isRazorpay ? <RazorpayBankLimitationBanner /> : null}

      {isRazorpay ? <RazorpayDemoPanel /> : null}

      {showCsvLoading || showRazorpayLoading ? (
        <LoadingState
          label={isRazorpay ? "Syncing Razorpay data..." : "Loading reconciliation data..."}
        />
      ) : null}

      {showCsvError && !showCsvLoading ? (
        <ErrorState message={csvError ?? "No data"} onRetry={() => void refetchCsv()} />
      ) : null}

      {showRazorpayError ? (
        <ErrorState message={razorpay.error ?? "Sync failed"} onRetry={() => void razorpay.sync()} />
      ) : null}

      {showRazorpayEmpty ? (
        <EmptyState
          title="No Razorpay orders to reconcile"
          description="The Razorpay sync completed successfully but returned no orders. Reconciliation was not run."
        />
      ) : null}

      {showRazorpayIdle ? (
        <EmptyState
          title="Razorpay source selected"
          description="Click “Sync from Razorpay” to fetch live Razorpay data. Sync does not run automatically."
        />
      ) : null}

      {report && !showCsvLoading && !showRazorpayLoading ? (
        <>
          <div className="mb-10 flex flex-wrap items-center gap-3 text-sm text-[var(--color-muted)]">
            <EngineStatus online={health.data?.status === "ok" && !health.error} />
            <span className="text-[var(--color-border)]">·</span>
            <span>Last run · {report.metadata.generated_at}</span>
            <span className="text-[var(--color-border)]">·</span>
            <span>
              {report.metadata.currency} · {report.summary.total_orders} orders
            </span>
            <span className="text-[var(--color-border)]">·</span>
            <span className="font-medium text-[var(--color-ink)]">
              Source · {isCsv ? "CSV" : "Razorpay"}
            </span>
            {isRazorpay ? (
              <>
                <span className="text-[var(--color-border)]">·</span>
                <span>Bank · Not available from Razorpay</span>
              </>
            ) : null}
            {refreshSuccess && isCsv ? (
              <>
                <span className="text-[var(--color-border)]">·</span>
                <span className="font-medium text-[var(--color-success)]">Data refreshed</span>
              </>
            ) : null}
          </div>

          <DashboardReportBody data={report} onNavigateExceptions={navigateExceptions} />
        </>
      ) : null}
    </div>
  );
}
