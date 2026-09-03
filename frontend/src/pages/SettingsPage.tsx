import { ExternalLink } from "lucide-react";
import { api } from "../api/client";
import {
  Button,
  ErrorState,
  LoadingState,
  PageHeader,
  SectionLabel,
  SettingRow,
} from "../components/ui/primitives";
import { useHealth, useReconciliationReport } from "../hooks/useApi";

export function SettingsPage() {
  const health = useHealth();
  const report = useReconciliationReport();

  if (health.loading || report.loading) return <LoadingState label="Checking API connection..." />;
  if (health.error) return <ErrorState message={health.error} onRetry={health.refetch} />;

  const isOnline = health.data?.status === "ok";

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Settings"
        subtitle="System configuration and connection details. All values are read-only."
      />

      <section className="mb-10">
        <SectionLabel title="API Connection" />
        <dl className="rounded-xl border border-[var(--color-border)] bg-white px-5 shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
          <SettingRow
            label="Endpoint"
            value={<span className="font-mono text-xs">{api.baseUrl}</span>}
          />
          <SettingRow
            label="Connection status"
            value={isOnline ? "Connected" : "Unavailable"}
            status={isOnline ? "ok" : "error"}
          />
          <SettingRow label="Service" value={health.data?.service ?? "—"} />
          <SettingRow label="API version" value={health.data?.version ?? "—"} />
        </dl>
      </section>

      <section className="mb-10">
        <SectionLabel title="Reconciliation Engine" />
        {report.error || !report.data ? (
          <p className="text-sm text-[var(--color-muted)]">Engine configuration unavailable.</p>
        ) : (
          <dl className="rounded-xl border border-[var(--color-border)] bg-white px-5 shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
            <SettingRow label="Engine" value={report.data.metadata.engine} />
            <SettingRow label="Mode" value="Deterministic" status="ok" />
            <SettingRow
              label="Dataset"
              value={`${report.data.summary.total_orders} orders`}
            />
            <SettingRow
              label="Timestamp tolerance"
              value={`${report.data.configuration.timestamp_tolerance_hours} hours`}
            />
            <SettingRow label="Currency" value={report.data.metadata.currency} />
            <SettingRow label="Minor unit" value={report.data.metadata.minor_unit} />
            <SettingRow
              label="Last report"
              value={report.data.metadata.generated_at}
            />
          </dl>
        )}
      </section>

      <section className="mb-10">
        <SectionLabel title="Evaluation" />
        <dl className="rounded-xl border border-[var(--color-border)] bg-white px-5 shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
          <SettingRow
            label="Ground truth boundary"
            value="Evaluation layer only"
            status="ok"
          />
          <SettingRow
            label="Production access"
            value="Not exposed to frontend"
            status="ok"
          />
          <SettingRow
            label="Evaluation grain"
            value={report.data?.metadata.evaluation_grain ?? "—"}
          />
        </dl>
      </section>

      <section>
        <SectionLabel title="Developer" />
        <div className="rounded-xl border border-[var(--color-border)] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
          <p className="mb-4 text-sm text-[var(--color-muted)]">
            ReconEngine frontend v1.0.0 · API documentation available at the backend OpenAPI endpoint.
          </p>
          <Button
            variant="secondary"
            size="sm"
            icon={<ExternalLink className="h-3.5 w-3.5" />}
            onClick={() => window.open(`${api.baseUrl}/docs`, "_blank", "noopener")}
          >
            Open API documentation
          </Button>
        </div>
      </section>
    </div>
  );
}
