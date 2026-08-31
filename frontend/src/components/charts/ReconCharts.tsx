import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatPercent } from "../../utils/format";
import { SectionLabel } from "../ui/primitives";

const CHART_FONT = "Inter, sans-serif";
const GRID_COLOR = "rgba(0,0,0,0.06)";
const AXIS_COLOR = "#6B6B6B";

function ChartTooltip({
  active,
  payload,
  label,
  suffix = "",
}: {
  active?: boolean;
  payload?: { value: number; name: string }[];
  label?: string;
  suffix?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 shadow-[0_4px_12px_rgba(0,0,0,0.08)]">
      <p className="text-[11px] text-[var(--color-muted)]">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums">
        {payload[0].value}
        {suffix}
      </p>
    </div>
  );
}

export function ReconciliationHealthRing({
  rate,
  reconciled,
  unreconciled,
  total,
}: {
  rate: number;
  reconciled: number;
  unreconciled: number;
  total: number;
}) {
  const circumference = 2 * Math.PI * 70;
  const offset = circumference - (rate * circumference);

  return (
    <div className="flex flex-col items-center gap-8 sm:flex-row sm:items-center sm:gap-12">
      <div className="relative h-44 w-44 shrink-0">
        <svg viewBox="0 0 160 160" className="h-full w-full -rotate-90">
          <circle
            cx="80"
            cy="80"
            r="70"
            fill="none"
            stroke="rgba(0,0,0,0.06)"
            strokeWidth="8"
          />
          <circle
            cx="80"
            cy="80"
            r="70"
            fill="none"
            stroke="var(--color-success)"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="health-arc"
            style={{ "--target-offset": offset } as React.CSSProperties}
          />
          <circle
            cx="80"
            cy="80"
            r="70"
            fill="none"
            stroke="var(--color-danger)"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${(unreconciled / total) * circumference} ${circumference}`}
            strokeDashoffset={-(rate * circumference)}
            opacity={unreconciled > 0 ? 0.7 : 0}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[2.5rem] font-semibold tabular-nums tracking-[-0.04em]">
            {formatPercent(rate)}
          </span>
          <span className="text-xs text-[var(--color-muted)]">reconciled</span>
        </div>
      </div>
      <div className="flex gap-10">
        <div>
          <p className="text-2xl font-semibold tabular-nums text-[var(--color-success)]">
            {reconciled}
          </p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">Reconciled</p>
        </div>
        <div>
          <p className="text-2xl font-semibold tabular-nums text-[var(--color-danger)]">
            {unreconciled}
          </p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">Exceptions</p>
        </div>
        <div>
          <p className="text-2xl font-semibold tabular-nums">{total}</p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">Total orders</p>
        </div>
      </div>
    </div>
  );
}

export function StatusDistributionViz({
  statusCounts,
}: {
  statusCounts: Record<string, number>;
}) {
  const data = useMemo(
    () =>
      Object.entries(statusCounts)
        .map(([status, count]) => ({
          status: status.replace(/_/g, " "),
          count,
        }))
        .sort((a, b) => b.count - a.count),
    [statusCounts],
  );

  const max = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="space-y-3">
      {data.map((item, i) => (
        <div key={item.status} className="bar-grow" style={{ animationDelay: `${i * 60}ms` }}>
          <div className="mb-1.5 flex items-center justify-between gap-4">
            <span className="truncate text-sm text-[var(--color-ink)]">{item.status}</span>
            <span className="shrink-0 text-sm font-semibold tabular-nums">{item.count}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-black/[0.05]">
            <div
              className="h-full rounded-full bg-[var(--color-ink)] transition-all duration-700 ease-[var(--ease-out)]"
              style={{ width: `${(item.count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ScenarioPerformanceChart({
  scenarios,
}: {
  scenarios: Record<string, { binary_accuracy: number; total_orders: number }>;
}) {
  const data = Object.entries(scenarios).map(([name, value]) => ({
    name: name.replace(/_/g, " "),
    accuracy: Number((value.binary_accuracy * 100).toFixed(1)),
    orders: value.total_orders,
  }));

  return (
    <div>
      <SectionLabel title="Scenario Performance" description="Binary accuracy by evaluation scenario" />
      <div className="h-72 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barSize={28} margin={{ top: 8, right: 8, left: -16, bottom: 48 }}>
            <CartesianGrid stroke={GRID_COLOR} vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fill: AXIS_COLOR, fontSize: 11, fontFamily: CHART_FONT }}
              axisLine={false}
              tickLine={false}
              interval={0}
              angle={-25}
              textAnchor="end"
              height={60}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: AXIS_COLOR, fontSize: 11, fontFamily: CHART_FONT }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip content={<ChartTooltip suffix="%" />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
            <Bar dataKey="accuracy" fill="var(--color-accent)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function EvaluationMetricsGrid({
  f1,
  precision,
  recall,
  accuracy,
}: {
  f1: number;
  precision: number;
  recall: number;
  accuracy: number;
}) {
  const metrics = [
    { label: "F1 Score", value: formatPercent(f1), primary: true },
    { label: "Precision", value: formatPercent(precision) },
    { label: "Recall", value: formatPercent(recall) },
    { label: "Accuracy", value: formatPercent(accuracy) },
  ];

  return (
    <div className="grid gap-8 border-b border-[var(--color-border)] pb-10 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map((m) => (
        <div key={m.label}>
          <p
            className={
              m.primary
                ? "text-[3rem] font-semibold tabular-nums tracking-[-0.04em]"
                : "text-[2rem] font-semibold tabular-nums tracking-[-0.03em]"
            }
          >
            {m.value}
          </p>
          <p className="mt-1 text-sm text-[var(--color-muted)]">{m.label}</p>
        </div>
      ))}
    </div>
  );
}

export function ConfusionMatrix({
  tp,
  tn,
  fp,
  fn,
}: {
  tp: number;
  tn: number;
  fp: number;
  fn: number;
}) {
  const cells = [
    { label: "True Positives", value: tp, tone: "success" },
    { label: "True Negatives", value: tn, tone: "success" },
    { label: "False Positives", value: fp, tone: "danger" },
    { label: "False Negatives", value: fn, tone: "danger" },
  ];

  return (
    <div className="grid gap-px overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-border)] sm:grid-cols-2 lg:grid-cols-4">
      {cells.map((cell) => (
        <div key={cell.label} className="bg-white px-5 py-5">
          <p className="text-2xl font-semibold tabular-nums">{cell.value}</p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">{cell.label}</p>
        </div>
      ))}
    </div>
  );
}
