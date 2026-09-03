import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import { useReconciliationReport } from "../hooks/useApi";
import { useDataSource, type DataSource } from "../hooks/useDataSource";
import { useRazorpaySync, type RazorpaySyncState } from "../hooks/useRazorpaySync";
import type { ReconciliationReport, RazorpaySyncResponse } from "../types/api";

export interface ConsoleReportContextValue {
  source: DataSource;
  setSource: (source: DataSource) => void;
  isCsv: boolean;
  isRazorpay: boolean;
  /** Active report for the selected source (CSV GET or last Razorpay sync). */
  report: ReconciliationReport | null;
  /** CSV GET loading/error (only relevant when source is csv). */
  csvLoading: boolean;
  csvError: string | null;
  csvRefreshing: boolean;
  refetchCsv: (options?: { silent?: boolean }) => Promise<void>;
  /** Razorpay sync state (explicit sync only; never auto-runs). */
  razorpay: RazorpaySyncState;
  razorpayEnvelope: RazorpaySyncResponse | null;
}

const ConsoleReportContext = createContext<ConsoleReportContextValue | null>(null);

/**
 * Console-scoped source + report state.
 * CSV continues to use GET /reconciliation/report.
 * Razorpay sync runs only when razorpay.sync() is invoked.
 */
export function ConsoleReportProvider({ children }: { children: ReactNode }) {
  const dataSource = useDataSource("csv");
  const csv = useReconciliationReport();
  const razorpay = useRazorpaySync();

  const setSource = useCallback(
    (next: DataSource) => {
      dataSource.setSource(next);
    },
    [dataSource],
  );

  const report = dataSource.isCsv ? csv.data : razorpay.report;

  const value = useMemo<ConsoleReportContextValue>(
    () => ({
      source: dataSource.source,
      setSource,
      isCsv: dataSource.isCsv,
      isRazorpay: dataSource.isRazorpay,
      report,
      csvLoading: csv.loading,
      csvError: csv.error,
      csvRefreshing: csv.refreshing,
      refetchCsv: csv.refetch,
      razorpay,
      razorpayEnvelope: razorpay.response,
    }),
    [
      dataSource.source,
      dataSource.isCsv,
      dataSource.isRazorpay,
      setSource,
      report,
      csv.loading,
      csv.error,
      csv.refreshing,
      csv.refetch,
      razorpay,
    ],
  );

  return (
    <ConsoleReportContext.Provider value={value}>{children}</ConsoleReportContext.Provider>
  );
}

export function useConsoleReport(): ConsoleReportContextValue {
  const ctx = useContext(ConsoleReportContext);
  if (!ctx) {
    throw new Error("useConsoleReport must be used within ConsoleReportProvider");
  }
  return ctx;
}
