import { useEvaluation, useHealth, useReconciliationReport, useReconciliationSummary } from "../hooks/useApi";
import { CONSOLE_PATHS } from "../utils/format";
import { CtaAtmosphere, HeroAtmosphere, ProductAura } from "../components/landing/atmosphere";
import { ExplainableTrail } from "../components/landing/ExplainableTrail";
import { LandingExperience } from "../components/landing/LandingExperience";
import { API_DOCS_URL, MarketingFooter, MarketingHeader } from "../components/landing/MarketingChrome";
import { PipelineDiagram } from "../components/landing/PipelineDiagram";
import { ApiSample, HeroPreview, ProductDemonstration } from "../components/landing/ProductStage";
import { Reveal } from "../components/landing/motion";
import {
  DisplayHeadline,
  Eyebrow,
  LandingCta,
  LiveDot,
  LiveMetric,
  SectionShell,
} from "../components/landing/primitives";

const EXCEPTION_ITEMS: { label: string; description: string; key: string }[] = [
  { label: "Missing settlement", description: "No settlement record linked to the order.", key: "missing_settlements" },
  { label: "Missing bank transaction", description: "Settlement with no matching bank movement.", key: "missing_bank_transactions" },
  { label: "Settlement amount mismatch", description: "Settlement gross does not match the order.", key: "settlement_amount_mismatches" },
  { label: "Bank amount mismatch", description: "Bank amount does not match settlement net.", key: "bank_amount_mismatches" },
  { label: "Timestamp violation", description: "Settlement and bank times outside tolerance.", key: "timestamp_violations" },
  { label: "Refund mismatch", description: "Refund without a matching settlement adjustment.", key: "refund_mismatches" },
  { label: "Duplicate settlement", description: "More than one settlement for a single order.", key: "duplicate_settlements" },
  { label: "Duplicate bank transaction", description: "Repeated bank entries for one order.", key: "duplicate_bank_transactions" },
  { label: "Reference variation", description: "Linked through a normalized, non-exact reference.", key: "reference_variations" },
];

const ENGINE_POINTS = [
  { title: "Reference-based matching", body: "Orders, settlements, and bank records are joined on normalized references — not heuristics." },
  { title: "Normalization", body: "Identifiers are canonicalized before matching so formatting differences do not create false breaks." },
  { title: "Timestamp tolerance", body: "Settlement and bank times are compared against an explicit tolerance, then recorded." },
  { title: "Amount comparison", body: "Order, settlement, and bank amounts are compared in minor units, including refunds." },
  { title: "Status precedence", body: "A fixed vocabulary decides the outcome. The same inputs always produce the same status." },
  { title: "Confidence scoring", body: "Each order receives a numeric score from the rules that fired — inspectable, not inferred." },
  { title: "Exception generation", body: "Failures are classified into a closed set of reasons operations can act on." },
  { title: "Deterministic evaluation", body: "Engine quality is measured against labeled ground truth. Evaluation never participates in matching." },
];

function liveCount(counts: Record<string, number> | undefined, key: string): number | null {
  if (!counts) return null;
  return counts[key] ?? 0;
}

export function LandingPage() {
  const summaryState = useReconciliationSummary();
  const reportState = useReconciliationReport();
  const evaluationState = useEvaluation();
  const healthState = useHealth();

  const summary = summaryState.data;
  const report = reportState.data;
  const evaluation = evaluationState.data;
  const live = healthState.data?.status === "ok";

  const binary = evaluation?.binary_classification;

  return (
    <LandingExperience>
      <div className="marketing min-h-screen overflow-x-clip font-sans">
        <MarketingHeader />
        <div className="h-14" aria-hidden />

        <section className="relative px-6 pt-16 pb-10 sm:pt-24 sm:pb-16 md:pt-28">
          <HeroAtmosphere />
          <div className="relative mx-auto max-w-[1120px]">
            <div className="max-w-[40rem]">
              <Reveal>
                <Eyebrow>Financial reconciliation infrastructure</Eyebrow>
              </Reveal>
              <Reveal delay={0.06} className="mt-5">
                <DisplayHeadline as="h1">
                  Reconcile on facts,
                  <span className="block">not guesswork.</span>
                </DisplayHeadline>
              </Reveal>
              <Reveal delay={0.12}>
                <p className="mt-6 max-w-[34rem] text-[17px] leading-relaxed text-[var(--marketing-muted)] sm:text-lg">
                  Deterministic reconciliation for orders, settlements, refunds, and bank transactions.
                </p>
              </Reveal>
              <Reveal delay={0.18} className="mt-8 flex flex-wrap items-center gap-3">
                <LandingCta to={CONSOLE_PATHS.home}>Open ReconEngine</LandingCta>
                <LandingCta href="#how-it-works" variant="ghost">
                  See how it works
                </LandingCta>
              </Reveal>
              <Reveal delay={0.26} className="mt-6">
                <LiveDot live={live} />
              </Reveal>
            </div>

            <Reveal delay={0.12} className="mt-14 md:mt-16" y={20}>
              <ProductAura float>
                <HeroPreview
                  summary={summary}
                  report={report}
                  loading={summaryState.loading || reportState.loading}
                  error={summaryState.error || reportState.error}
                  live={live}
                />
              </ProductAura>
            </Reveal>
          </div>
        </section>

        <section className="px-6 py-24 md:py-32">
          <div className="mx-auto grid max-w-[1120px] items-center gap-12 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.72fr)] lg:gap-16">
            <div>
              <Reveal>
                <DisplayHeadline className="max-w-[18ch]">
                  Financial reconciliation should be explainable.
                </DisplayHeadline>
              </Reveal>
              <Reveal delay={0.08}>
                <p className="mt-8 max-w-[36rem] text-[17px] leading-[1.7] text-[var(--marketing-muted)] sm:text-lg">
                  Every result is produced by explicit rules — matching, amounts, timestamps, and refunds — and written into an audit trail. If an order is unreconciled, the engine can say why.
                </p>
              </Reveal>
            </div>
            <ExplainableTrail />
          </div>
        </section>

        <SectionShell
          id="how-it-works"
          className="marketing-section-blue"
          eyebrow={<Eyebrow>How it works</Eyebrow>}
          headline="How reconciliation works"
          subhead="Six deterministic stages from raw records to an inspectable decision."
          align="center"
        >
          <PipelineDiagram />
        </SectionShell>

        <SectionShell
          id="product"
          className="marketing-section-tint"
          eyebrow={<Eyebrow>Product</Eyebrow>}
          headline="The ledger operations can inspect."
          subhead="Reconciliation status, confidence, amounts, timestamps, and the audit trail — from the live engine, not a mock."
        >
          <div className="mt-14">
            <ProductAura>
              <ProductDemonstration
                report={report}
                loading={reportState.loading}
                error={reportState.error}
              />
            </ProductAura>
          </div>
        </SectionShell>

        <section className="px-6 py-24 md:py-32">
          <div className="mx-auto max-w-[1120px]">
            <Reveal>
              <Eyebrow>Exceptions</Eyebrow>
            </Reveal>
            <Reveal delay={0.06}>
              <DisplayHeadline className="mt-4 max-w-[18ch]">Every exception has a reason.</DisplayHeadline>
            </Reveal>
            <Reveal delay={0.1}>
              <p className="mt-5 max-w-[34rem] text-[17px] leading-relaxed text-[var(--marketing-muted)]">
                Failures are classified into a closed vocabulary. Counts below are from the current live run.
              </p>
            </Reveal>
            {summaryState.error && !summary ? (
              <p className="mt-10 text-sm text-[var(--marketing-muted)]">Live exception counts unavailable.</p>
            ) : (
              <div className="mt-12 divide-y divide-[var(--marketing-border)] border-y border-[var(--marketing-border)]">
                {EXCEPTION_ITEMS.map((item, index) => (
                  <Reveal key={item.key} delay={index * 0.03} y={8}>
                    <div className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-baseline gap-6 py-5 transition hover:bg-[#2563EB]/[0.03] sm:grid-cols-[5.5rem_minmax(0,1fr)]">
                      <p className="text-[1.35rem] font-medium tabular-nums tracking-tight text-[#2563EB]">
                        <LiveMetric
                          value={liveCount(summary?.exception_counts, item.key)}
                          loading={summaryState.loading && !summary}
                          format={(n) => String(Math.round(n))}
                        />
                      </p>
                      <div>
                        <p className="text-[15px] font-medium text-[var(--marketing-fg)]">{item.label}</p>
                        <p className="mt-1 text-sm leading-relaxed text-[var(--marketing-muted)]">{item.description}</p>
                      </div>
                    </div>
                  </Reveal>
                ))}
              </div>
            )}
          </div>
        </section>

        <section id="engine" className="marketing-section-blue scroll-mt-24 px-6 py-24 md:py-32">
          <div className="mx-auto max-w-[1120px]">
            <Reveal>
              <Eyebrow>Engine</Eyebrow>
            </Reveal>
            <Reveal delay={0.06}>
              <DisplayHeadline className="mt-4">Deterministic by design.</DisplayHeadline>
            </Reveal>
            <Reveal delay={0.1}>
              <p className="mt-5 max-w-[36rem] text-[17px] leading-relaxed text-[var(--marketing-muted)]">
                Same inputs and the same rules produce the same result. The engine does not guess, and it does not improvise.
              </p>
            </Reveal>
            <div className="mt-14 grid gap-x-16 gap-y-10 sm:grid-cols-2">
              {ENGINE_POINTS.map((point, index) => (
                <Reveal key={point.title} delay={index * 0.04} y={10}>
                  <div className="border-l border-[var(--marketing-border)] pl-4 transition hover:border-[#2563EB]">
                    <p className="text-[11px] font-medium tabular-nums text-[var(--marketing-muted)]">
                      {String(index + 1).padStart(2, "0")}
                    </p>
                    <p className="mt-2 text-[15px] font-semibold text-[var(--marketing-fg)]">{point.title}</p>
                    <p className="mt-2 text-sm leading-relaxed text-[var(--marketing-muted)]">{point.body}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section id="evaluation" className="marketing-section-eval scroll-mt-24 px-6 py-24 md:py-32">
          <div className="mx-auto max-w-[1120px]">
            <Reveal>
              <Eyebrow>Engine evaluation</Eyebrow>
            </Reveal>
            <Reveal delay={0.06}>
              <DisplayHeadline className="mt-4">Measured against ground truth.</DisplayHeadline>
            </Reveal>
            <Reveal delay={0.1}>
              <p className="mt-5 max-w-[36rem] text-[17px] leading-relaxed text-[var(--marketing-muted)]">
                These figures assess engine correctness. Ground truth is an evaluation input only — it never participates in production matching.
              </p>
            </Reveal>

            {evaluationState.error && !evaluation ? (
              <p className="mt-12 text-sm text-[var(--marketing-muted)]">Live evaluation metrics unavailable.</p>
            ) : (
              <div className="mt-14 grid gap-10 border-t border-[var(--marketing-border)] pt-10 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  { label: "Precision", value: binary ? binary.precision * 100 : null, hint: "Share of reconciled calls that were correct" },
                  { label: "Recall", value: binary ? binary.recall * 100 : null, hint: "Share of truly reconciled orders found" },
                  { label: "F1", value: binary ? binary.f1_score * 100 : null, hint: "Harmonic mean of precision and recall" },
                  { label: "Accuracy", value: binary ? binary.accuracy * 100 : null, hint: "Binary classification accuracy" },
                ].map((metric) => (
                  <div key={metric.label}>
                    <p className="text-[2.25rem] font-medium tabular-nums tracking-[-0.04em] text-[var(--marketing-fg)] sm:text-[2.75rem]">
                      <LiveMetric
                        value={metric.value}
                        loading={evaluationState.loading && !evaluation}
                        format={(n) => `${n.toFixed(1)}%`}
                      />
                    </p>
                    <div className="mt-3 h-1 overflow-hidden rounded-full bg-black/[0.06]" aria-hidden>
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-[#2563EB] to-[#06B6D4]"
                        style={{ width: metric.value == null ? "0%" : `${Math.max(0, Math.min(100, metric.value))}%` }}
                      />
                    </div>
                    <p className="mt-2 text-[13px] font-medium uppercase tracking-[0.12em] text-[var(--marketing-muted)]">
                      {metric.label}
                    </p>
                    <p className="mt-1 text-[13px] text-[var(--marketing-muted)]">{metric.hint}</p>
                  </div>
                ))}
              </div>
            )}
            {evaluation ? (
              <p className="mt-10 text-[13px] text-[var(--marketing-muted)]">
                {evaluation.summary.orders_evaluated} orders evaluated against labeled ground truth.
              </p>
            ) : null}
          </div>
        </section>

        <section id="developers" className="marketing-section-tint scroll-mt-24 px-6 py-24 md:py-32">
          <div className="mx-auto grid max-w-[1120px] items-start gap-12 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-16">
            <div>
              <Reveal>
                <Eyebrow>Developers</Eyebrow>
              </Reveal>
              <Reveal delay={0.06}>
                <DisplayHeadline className="mt-4">Integrate over HTTP.</DisplayHeadline>
              </Reveal>
              <Reveal delay={0.1}>
                <p className="mt-5 max-w-[32rem] text-[17px] leading-relaxed text-[var(--marketing-muted)]">
                  ReconEngine exposes a documented API for summary, report, and evaluation. The response below is from the live engine.
                </p>
              </Reveal>
              <Reveal delay={0.16} className="mt-8">
                <LandingCta href={API_DOCS_URL} variant="dark" external>
                  View API Documentation
                </LandingCta>
              </Reveal>
            </div>
            <Reveal delay={0.1} y={16}>
              <ProductAura>
                <ApiSample
                  summary={summary}
                  loading={summaryState.loading}
                  error={summaryState.error}
                />
              </ProductAura>
            </Reveal>
          </div>
        </section>

        <section className="marketing-section-cta relative px-6 py-24 md:py-32">
          <CtaAtmosphere />
          <div className="relative mx-auto max-w-[720px] text-center">
            <Reveal>
              <DisplayHeadline>Reconcile with confidence.</DisplayHeadline>
            </Reveal>
            <Reveal delay={0.08}>
              <p className="mx-auto mt-5 max-w-[32rem] text-[17px] leading-relaxed text-[var(--marketing-muted)]">
                Turn financial transaction data into decisions you can explain.
              </p>
            </Reveal>
            <Reveal delay={0.14} className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <LandingCta to={CONSOLE_PATHS.home}>Open ReconEngine</LandingCta>
              <LandingCta href={API_DOCS_URL} variant="ghost" external>
                View API Docs
              </LandingCta>
            </Reveal>
          </div>
        </section>

        <MarketingFooter />
      </div>
    </LandingExperience>
  );
}

export default LandingPage;
