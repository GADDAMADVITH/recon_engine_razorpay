import { motion, useMotionValue, useSpring } from "motion/react";
import { Link } from "react-router-dom";
import { cn } from "../../utils/format";
import { CountUp, Reveal, useDesktopPointer, usePrefersReducedMotion } from "./motion";

export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p
      className={cn(
        "text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--marketing-muted)]",
        className,
      )}
    >
      {children}
    </p>
  );
}

export function DisplayHeadline({
  as: Tag = "h2",
  children,
  className,
}: {
  as?: "h1" | "h2";
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Tag
      className={cn(
        "font-sans font-medium tracking-[-0.045em] text-[var(--marketing-fg)]",
        Tag === "h1"
          ? "text-[2.75rem] leading-[1.05] sm:text-[3.75rem] lg:text-[4.75rem] lg:leading-[1.02]"
          : "text-[2rem] leading-[1.12] sm:text-[2.75rem] lg:text-[3.25rem] lg:leading-[1.08]",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function SectionShell({
  id,
  eyebrow,
  headline,
  subhead,
  children,
  align = "left",
  className,
}: {
  id?: string;
  eyebrow?: React.ReactNode;
  headline: React.ReactNode;
  subhead?: React.ReactNode;
  children?: React.ReactNode;
  align?: "center" | "left";
  className?: string;
}) {
  return (
    <section id={id} className={cn("scroll-mt-24 px-6 py-24 md:py-32", className)}>
      <div className={cn("mx-auto max-w-[1120px]", align === "center" && "text-center")}>
        {eyebrow ? (
          <Reveal className={cn(align === "center" && "flex justify-center")}>{eyebrow}</Reveal>
        ) : null}
        <Reveal delay={0.06}>
          <DisplayHeadline className={cn("mt-4", align === "center" && "mx-auto max-w-[820px]")}>
            {headline}
          </DisplayHeadline>
        </Reveal>
        {subhead ? (
          <Reveal delay={0.12}>
            <p
              className={cn(
                "mt-5 text-[17px] leading-relaxed text-[var(--marketing-muted)] sm:text-lg",
                align === "center" ? "mx-auto max-w-[640px]" : "max-w-[560px]",
              )}
            >
              {subhead}
            </p>
          </Reveal>
        ) : null}
        {children}
      </div>
    </section>
  );
}

const ctaClass = {
  accent:
    "bg-gradient-to-r from-[#2563EB] to-[#0891B2] text-white shadow-[0_8px_20px_rgba(37,99,235,0.28)] md:hover:-translate-y-px hover:shadow-[0_14px_32px_rgba(37,99,235,0.38)] hover:brightness-105",
  dark: "bg-[var(--marketing-fg)] text-white shadow-[0_6px_16px_rgba(11,27,43,0.16)] md:hover:-translate-y-px hover:shadow-[0_12px_28px_rgba(11,27,43,0.22)]",
  ghost:
    "border border-[var(--marketing-border)] bg-white/70 text-[var(--marketing-fg)] backdrop-blur-sm hover:border-[#2563EB]/30 hover:bg-white",
} as const;

export function LandingCta({
  to,
  href,
  children,
  variant = "accent",
  size = "md",
  external = false,
}: {
  to?: string;
  href?: string;
  children: React.ReactNode;
  variant?: "accent" | "dark" | "ghost";
  size?: "sm" | "md";
  external?: boolean;
}) {
  const reduced = usePrefersReducedMotion();
  const magnetic = useDesktopPointer();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 280, damping: 24, mass: 0.35 });
  const springY = useSpring(y, { stiffness: 280, damping: 24, mass: 0.35 });

  const onMove = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!magnetic || reduced) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const dx = event.clientX - (rect.left + rect.width / 2);
    const dy = event.clientY - (rect.top + rect.height / 2);
    x.set(Math.max(-8, Math.min(8, dx * 0.2)));
    y.set(Math.max(-6, Math.min(6, dy * 0.2)));
  };

  const onLeave = () => {
    x.set(0);
    y.set(0);
  };

  const className = cn(
    "inline-flex items-center justify-center rounded-full font-medium transition duration-150",
    !reduced && "md:hover:scale-[1.02] md:active:scale-[0.99]",
    size === "md" ? "h-11 px-5 text-[15px]" : "h-9 px-4 text-[14px]",
    ctaClass[variant],
  );

  const action = to ? (
    <Link to={to} className={className}>
      {children}
    </Link>
  ) : (
    <a
      href={href}
      className={className}
      {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
    >
      {children}
    </a>
  );

  return (
    <motion.div
      className={cn("inline-flex", size === "md" && magnetic && !reduced && "p-10 -m-10")}
      style={magnetic && !reduced ? { x: springX, y: springY } : undefined}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      {action}
    </motion.div>
  );
}

export function LiveMetric({
  value,
  loading,
  format,
  className,
}: {
  value: number | null;
  loading?: boolean;
  format: (n: number) => string;
  className?: string;
}) {
  if (loading) {
    return (
      <span
        className={cn("inline-block h-[0.72em] w-[3.2rem] animate-pulse rounded-md bg-black/[0.06]", className)}
        aria-hidden
      />
    );
  }

  if (value == null) {
    return <span className={className}>—</span>;
  }

  return (
    <span className={className}>
      <CountUp value={value} format={format} />
    </span>
  );
}

export function LiveDot({ live }: { live: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--marketing-muted)]">
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          live ? "marketing-live-pulse bg-[var(--marketing-success)]" : "bg-[var(--marketing-muted)]",
        )}
        aria-hidden
      />
      {live ? "Live reconciliation engine" : "Engine unreachable"}
    </span>
  );
}

