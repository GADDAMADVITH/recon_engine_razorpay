import type { DataSource } from "../../hooks/useDataSource";
import { cn } from "../../utils/format";

export function DataSourceSelector({
  source,
  onChange,
}: {
  source: DataSource;
  onChange: (source: DataSource) => void;
}) {
  return (
    <div
      className="inline-flex rounded-lg border border-[var(--color-border)] bg-white p-0.5"
      role="group"
      aria-label="Data source"
    >
      {(
        [
          { id: "csv", label: "CSV" },
          { id: "razorpay", label: "Razorpay" },
        ] as const
      ).map((option) => {
        const selected = source === option.id;
        return (
          <button
            key={option.id}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(option.id)}
            className={cn(
              "cursor-pointer rounded-md px-3 py-1.5 text-xs font-semibold transition",
              selected
                ? "bg-[var(--color-ink)] text-white"
                : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Honest live-Razorpay bank limitation notice.
 * Must not imply Razorpay supplies bank transactions.
 */
export function RazorpayBankLimitationBanner() {
  return (
    <aside
      className="mb-8 rounded-xl border border-[var(--color-warning)]/35 bg-amber-50 px-4 py-3 text-sm text-[var(--color-ink)]"
      role="note"
      aria-label="Razorpay bank data limitation"
    >
      <p className="font-semibold text-[var(--color-warning)]">Bank data not available from Razorpay</p>
      <p className="mt-1 text-[var(--color-muted)]">
        Razorpay provides payment-side records (orders, settlements, refunds). Live Razorpay sync does
        not include bank transactions, so settlement-to-bank matching cannot be proven until an
        independent bank-side source is supplied.
      </p>
      <dl className="mt-3 grid gap-1 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-[var(--color-muted)]">Data source</dt>
          <dd className="font-medium">Razorpay</dd>
        </div>
        <div>
          <dt className="text-[var(--color-muted)]">Bank data</dt>
          <dd className="font-medium">Not available from Razorpay</dd>
        </div>
      </dl>
    </aside>
  );
}
