import { useCallback, useState } from "react";
import { Button, StatusBadge } from "../ui/primitives";
import { api, ApiClientError } from "../../api/client";
import type { RazorpayReconcileDemoResponse } from "../../types/api";

/**
 * Compact Phase 4A demo panel.
 * Kept separate from live Razorpay sync so demo synthetic banks are never confused with live data.
 */
export function RazorpayDemoPanel() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<RazorpayReconcileDemoResponse | null>(null);

  const runDemo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.razorpayReconcileDemo();
      setDemo(result);
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : "Unable to run the reconciliation demo.";
      setError(message);
      setDemo(null);
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <section
      className="mb-10 rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] p-5"
      aria-label="Phase 4A reconciliation demo"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-warning)]">
            Demo — Synthetic Bank Data
          </p>
          <h2 className="mt-1 text-base font-semibold text-[var(--color-ink)]">
            Phase 4A reconciliation demo
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-[var(--color-muted)]">
            Bank transactions are synthetic fixtures for demonstration only. They are not provided by
            Razorpay and are not derived from settlement UTR. This does not replace live Razorpay sync.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => void runDemo()}
          disabled={loading}
          aria-label="Run Phase 4A Demo"
        >
          {loading ? "Running demo…" : "Run Phase 4A Demo"}
        </Button>
      </div>

      {loading ? (
        <p className="mt-4 text-sm text-[var(--color-muted)]" role="status">
          Running Phase 4A demo scenarios…
        </p>
      ) : null}

      {error ? (
        <div className="mt-4 rounded-lg border border-[var(--color-danger)]/30 bg-red-50 px-3 py-2 text-sm text-[var(--color-danger)]">
          <p className="font-medium">Demo failed</p>
          <p className="mt-1">{error}</p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="mt-3"
            onClick={() => void runDemo()}
          >
            Retry demo
          </Button>
        </div>
      ) : null}

      {demo ? (
        <div className="mt-5 space-y-4">
          <aside
            className="rounded-lg border border-[var(--color-warning)]/35 bg-amber-50 px-3 py-2 text-xs text-[var(--color-ink)]"
            role="note"
          >
            <p className="font-semibold text-[var(--color-warning)]">
              Demo — Synthetic Bank Data ({demo.bank_source})
            </p>
            <p className="mt-1 text-[var(--color-muted)]">{demo.bank_source_note}</p>
          </aside>

          <ul className="space-y-2">
            {demo.scenarios.map((scenario) => (
              <li
                key={scenario.scenario_id}
                className="rounded-lg border border-[var(--color-border)] bg-white px-4 py-3 text-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-[var(--color-ink)]">
                      {scenario.scenario_id.replace(/_/g, " ")}
                    </p>
                    <p className="mt-0.5 text-xs text-[var(--color-muted)]">{scenario.description}</p>
                    <p className="mt-1 font-mono text-[11px] text-[var(--color-muted)]">
                      {scenario.order_id}
                    </p>
                  </div>
                  <span
                    className={
                      scenario.matched_expectation
                        ? "rounded-md bg-[var(--color-success)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--color-success)]"
                        : "rounded-md bg-[var(--color-danger)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--color-danger)]"
                    }
                  >
                    {scenario.matched_expectation ? "Expectation matched" : "Expectation mismatch"}
                  </span>
                </div>
                <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                  <div>
                    <dt className="text-[11px] uppercase tracking-wide text-[var(--color-muted)]">
                      Expected
                    </dt>
                    <dd className="mt-1 flex flex-wrap items-center gap-2">
                      <StatusBadge
                        status={scenario.expected_status}
                        reconciled={scenario.expected_reconciled}
                      />
                      <span className="text-xs text-[var(--color-muted)]">
                        {scenario.expected_reconciled ? "reconciled" : "not reconciled"}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] uppercase tracking-wide text-[var(--color-muted)]">
                      Actual
                    </dt>
                    <dd className="mt-1 flex flex-wrap items-center gap-2">
                      <StatusBadge
                        status={scenario.actual_status}
                        reconciled={scenario.actual_reconciled}
                      />
                      <span className="text-xs text-[var(--color-muted)]">
                        {scenario.actual_reconciled ? "reconciled" : "not reconciled"}
                      </span>
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
