import { useRef } from "react";
import { motion, useInView } from "motion/react";
import { EASE_OUT, usePrefersReducedMotion } from "./motion";

const CHECKS = ["Amount matched", "Timestamp within tolerance", "Reference matched"] as const;

function Connector({ reduced }: { reduced: boolean }) {
  return (
    <div className="relative my-2.5 ml-[7px] h-7 w-px bg-gradient-to-b from-[#2563EB] to-[#06B6D4]" aria-hidden>
      {reduced ? null : <span className="marketing-signal-y" />}
    </div>
  );
}

function StepLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--marketing-muted)]">
      {children}
    </p>
  );
}

export function ExplainableTrail() {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const shown = reduced || inView;

  return (
    <div className="relative mx-auto w-full max-w-[22rem] lg:mx-0 lg:justify-self-end">
      <div
        className="pointer-events-none absolute -inset-6 rounded-[28px] bg-[radial-gradient(ellipse_at_center,rgba(37,99,235,0.16),rgba(6,182,212,0.08)_45%,transparent_70%)] blur-2xl"
        aria-hidden
      />
      <div
        ref={ref}
        className={`relative rounded-2xl border border-[var(--marketing-border)] bg-white/90 p-5 shadow-[0_1px_0_rgba(11,27,43,0.04),0_18px_48px_rgba(11,27,43,0.08)] backdrop-blur-sm sm:p-6 ${reduced ? "" : "explainable-float"}`}
      >
        <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--marketing-muted)]">
          Reconciliation audit trail
        </p>

        <div className="mt-5">
          <StepLabel>Order</StepLabel>
          <p className="mt-1 text-[15px] font-semibold tracking-tight text-[var(--marketing-fg)]">ORD-1042</p>
        </div>
        <Connector reduced={reduced} />

        <div>
          <StepLabel>Settlement</StepLabel>
          <p className="mt-1 text-[15px] font-semibold tabular-nums tracking-tight text-[var(--marketing-fg)]">
            ₹12,480.00
          </p>
        </div>
        <Connector reduced={reduced} />

        <div>
          <StepLabel>Bank transaction</StepLabel>
          <p className="mt-1 text-[15px] font-semibold tabular-nums tracking-tight text-[var(--marketing-fg)]">
            ₹12,480.00
          </p>
        </div>
        <Connector reduced={reduced} />

        <div>
          <StepLabel>Validation</StepLabel>
          <ul className="mt-2 space-y-1.5">
            {CHECKS.map((item, index) => (
              <motion.li
                key={item}
                className="text-[13px] text-[var(--marketing-success)]"
                initial={false}
                animate={shown ? { opacity: 1, y: 0 } : { opacity: 0, y: 6 }}
                transition={reduced ? { duration: 0 } : { duration: 0.4, delay: 0.12 + index * 0.1, ease: EASE_OUT }}
              >
                ✓ {item}
              </motion.li>
            ))}
          </ul>
        </div>
        <Connector reduced={reduced} />

        <div>
          <StepLabel>Final decision</StepLabel>
          <motion.p
            className="mt-1.5 text-[13px] font-semibold tracking-tight text-[var(--marketing-success)]"
            initial={false}
            animate={shown ? { opacity: 1 } : { opacity: reduced ? 1 : 0 }}
            transition={reduced ? { duration: 0 } : { duration: 0.4, delay: 0.42, ease: EASE_OUT }}
          >
            ✓ Reconciled
          </motion.p>
        </div>
      </div>
    </div>
  );
}
