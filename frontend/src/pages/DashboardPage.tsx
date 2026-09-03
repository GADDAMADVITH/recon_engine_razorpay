import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ReconciliationHealthRing,
  StatusDistributionViz,
} from "../components/charts/ReconCharts";
import {
  DataSourceSelector,
  RazorpayBankLimitationBanner,
} from "../components/sources/DataSourceBar";
import { RazorpayDemoPanel } from "../components/sources/RazorpayDemoPanel";
import {
  EmptyState,
  EngineStatus,
  ErrorState,
  InteractiveRow,
  LoadingState,
  PageHeader,
  PrimaryCTA,
  SectionLabel,
} from "../components/ui/primitives";
import { useConsoleReport } from "../context/ConsoleReportContext";
import { useHealth } from "../hooks/useApi";
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

  return (
    <>
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
                onClick={() => onNavigateExceptions()}
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
