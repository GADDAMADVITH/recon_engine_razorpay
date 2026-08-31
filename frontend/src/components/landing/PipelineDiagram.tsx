import { useRef } from "react";
import { motion, useInView } from "motion/react";
import { EASE_OUT, usePrefersReducedMotion } from "./motion";

const STAGES = [
  { id: "orders", label: "Orders", caption: "Ingested records enter the engine." },
  { id: "validation", label: "Validation", caption: "Schema and integrity checks." },
  { id: "normalization", label: "Normalization", caption: "References become canonical." },
  { id: "matching", label: "Matching", caption: "Deterministic links across sources." },
  { id: "reconciliation", label: "Reconciliation", caption: "Amount and time rules applied." },
  { id: "decision", label: "Decision", caption: "Status, score, and exceptions." },
] as const;

const LAST = STAGES.length - 1;

function Node({
  index,
  active,
  reduced,
}: {
  index: number;
  active: boolean;
  reduced: boolean;
}) {
  return (
    <motion.span
      className="relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-[12px] font-semibold tabular-nums"
      initial={false}
      animate={
        active
          ? { backgroundColor: "#0B1B2B", borderColor: "#0B1B2B", color: "#FFFFFF" }
          : { backgroundColor: "#FFFFFF", borderColor: "#E7E5DF", color: "#0B1B2B" }
      }
      transition={reduced ? { duration: 0 } : { duration: 0.4, ease: EASE_OUT }}
    >
      {index + 1}
    </motion.span>
  );
}

function VerticalStep({
  stage,
  index,
  reduced,
}: {
  stage: (typeof STAGES)[number];
  index: number;
  reduced: boolean;
}) {
  const ref = useRef<HTMLLIElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const active = reduced || inView;
  const isLast = index === LAST;

  return (
    <li
      ref={ref}
      className="grid grid-cols-[72px_minmax(0,1fr)] items-stretch gap-x-3"
    >
      <div className="flex flex-col items-center">
        <Node index={index} active={active} reduced={reduced} />
        {isLast ? null : (
          <div className="relative mt-2 w-px min-h-12 flex-1" aria-hidden>
            <div className="absolute inset-0 overflow-hidden">
              <motion.span
                className="block h-full w-px origin-top bg-gradient-to-b from-[#2563EB] to-[#06B6D4]"
                initial={false}
                animate={{ scaleY: active ? 1 : 0 }}
                transition={reduced ? { duration: 0 } : { duration: 0.45, delay: 0.05, ease: EASE_OUT }}
                style={{ originY: 0 }}
              />
            </div>
            {active && !reduced ? <span className="marketing-signal-y" /> : null}
          </div>
        )}
      </div>
      <motion.div
        className={isLast ? "pb-0 pt-1.5" : "pb-10 pt-1.5"}
        initial={false}
        animate={active ? { opacity: 1, y: 0 } : { opacity: reduced ? 1 : 0, y: reduced ? 0 : 10 }}
        transition={reduced ? { duration: 0 } : { duration: 0.45, delay: 0.06, ease: EASE_OUT }}
      >
        <p className="text-[15px] font-semibold text-[var(--marketing-fg)]">{stage.label}</p>
        <p className="mt-1 text-sm leading-relaxed text-[var(--marketing-muted)]">{stage.caption}</p>
      </motion.div>
    </li>
  );
}

function HorizontalPipeline({ reduced }: { reduced: boolean }) {
  const ref = useRef<HTMLOListElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.35 });

  return (
    <ol
      ref={ref}
      className="hidden grid-cols-6 lg:grid"
      aria-label="Reconciliation pipeline from orders to decision"
    >
      {STAGES.map((stage, index) => {
        const active = reduced || inView;
        const delay = index * 0.08;
        return (
          <li key={stage.id} className="relative px-3 text-left">
            {index < LAST ? (
              <div
                className="absolute top-[14px] left-[calc(50%+22px)] right-[-12px] h-2"
                aria-hidden
              >
                <div className="absolute top-[3px] right-0 left-0 h-px overflow-hidden">
                  <motion.span
                    className="block h-px w-full origin-left bg-gradient-to-r from-[#2563EB] to-[#06B6D4]"
                    initial={false}
                    animate={{ scaleX: active ? 1 : 0 }}
                    transition={reduced ? { duration: 0 } : { duration: 0.45, delay, ease: EASE_OUT }}
                  />
                </div>
                {active && !reduced ? (
                  <span className="marketing-signal-x" style={{ animationDelay: `${0.6 + delay}s` }} />
                ) : null}
              </div>
            ) : null}
            <div className="relative z-10 flex justify-center">
              <motion.div
                initial={false}
                animate={active ? { opacity: 1 } : { opacity: reduced ? 1 : 0.4 }}
                transition={reduced ? { duration: 0 } : { duration: 0.4, delay, ease: EASE_OUT }}
              >
                <Node index={index} active={active} reduced={reduced} />
              </motion.div>
            </div>
            <motion.div
              className="mt-5"
              initial={false}
              animate={active ? { opacity: 1, y: 0 } : { opacity: reduced ? 1 : 0, y: reduced ? 0 : 8 }}
              transition={reduced ? { duration: 0 } : { duration: 0.45, delay: delay + 0.05, ease: EASE_OUT }}
            >
              <p className="text-[15px] font-semibold text-[var(--marketing-fg)]">{stage.label}</p>
              <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--marketing-muted)]">{stage.caption}</p>
            </motion.div>
          </li>
        );
      })}
    </ol>
  );
}

export function PipelineDiagram() {
  const reduced = usePrefersReducedMotion();

  return (
    <div className="mt-16">
      <HorizontalPipeline reduced={reduced} />
      <ol className="mx-auto max-w-lg text-left lg:hidden" aria-label="Reconciliation pipeline from orders to decision">
        {STAGES.map((stage, index) => (
          <VerticalStep key={stage.id} stage={stage} index={index} reduced={reduced} />
        ))}
      </ol>
    </div>
  );
}
