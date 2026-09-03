import {
  ConfusionMatrix,
  EvaluationMetricsGrid,
  ScenarioPerformanceChart,
} from "../components/charts/ReconCharts";
import {
  DisplayMetric,
  ErrorState,
  LoadingState,
  PageHeader,
  SectionLabel,
} from "../components/ui/primitives";
import { useEvaluation } from "../hooks/useApi";
import { formatPercent } from "../utils/format";

export function EvaluationPage() {
  const { data, loading, error, refetch } = useEvaluation();

  if (loading && !data) return <LoadingState label="Loading evaluation metrics..." />;
  if (error || !data) return <ErrorState message={error ?? "No data"} onRetry={() => void refetch()} />;

  const binary = data.binary_classification;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Engine Evaluation"
        subtitle="Evaluation uses ground truth to measure engine correctness. Ground truth never participates in production reconciliation."
      />

      <div className="mb-10 rounded-xl border border-[var(--color-border)] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(11,27,43,0.04)]">
        <p className="text-sm leading-relaxed text-[var(--color-muted)]">
          This page measures reconciliation engine quality against labeled scenarios.
          It reflects research and validation metrics — not live production transaction data.
          {data.summary.orders_evaluated} orders evaluated across{" "}
          {Object.keys(data.scenario_evaluation).length} scenarios.
        </p>
      </div>

      <section className="mb-14">
        <EvaluationMetricsGrid
          f1={binary.f1_score}
          precision={binary.precision}
          recall={binary.recall}
          accuracy={binary.accuracy}
        />
      </section>

      <section className="mb-14">
        <SectionLabel title="Classification Matrix" />
        <ConfusionMatrix
          tp={binary.true_positives}
          tn={binary.true_negatives}
          fp={binary.false_positives}
          fn={binary.false_negatives}
        />
      </section>

      <section className="mb-14 grid gap-10 border-b border-[var(--color-border)] pb-14 sm:grid-cols-2">
        <DisplayMetric
          value={formatPercent(data.status_evaluation.strict.accuracy)}
          label="Strict Status Accuracy"
          hint={`${data.status_evaluation.strict.correct} of ${data.summary.orders_evaluated} exact status matches`}
          size="md"
        />
        <DisplayMetric
          value={formatPercent(data.status_evaluation.relaxed.accuracy)}
          label="Relaxed Status Accuracy"
          hint={`${data.status_evaluation.relaxed.correct} of ${data.summary.orders_evaluated} equivalent success matches`}
          size="md"
        />
      </section>

      <section>
        <ScenarioPerformanceChart scenarios={data.scenario_evaluation} />
      </section>
    </div>
  );
}
