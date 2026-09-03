import { useCallback, useState } from "react";

export type DataSource = "csv" | "razorpay";

export interface DataSourceState {
  source: DataSource;
  setSource: (source: DataSource) => void;
  isCsv: boolean;
  isRazorpay: boolean;
}

/**
 * Local data-source selection for the console.
 * Defaults to CSV. Does not fetch data or call Razorpay.
 */
export function useDataSource(initial: DataSource = "csv"): DataSourceState {
  const [source, setSourceState] = useState<DataSource>(initial);

  const setSource = useCallback((next: DataSource) => {
    setSourceState(next);
  }, []);

  return {
    source,
    setSource,
    isCsv: source === "csv",
    isRazorpay: source === "razorpay",
  };
}
