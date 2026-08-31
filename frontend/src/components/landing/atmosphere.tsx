import { cn } from "../../utils/format";
import { usePrefersReducedMotion } from "./motion";

export function HeroAtmosphere() {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 h-[760px] overflow-hidden md:h-[880px]" aria-hidden>
      <div className="marketing-hero-grid absolute inset-0" />
      <div
        className="marketing-glow-breathe absolute top-[18%] left-[8%] h-56 w-56 rounded-full bg-[#2563EB]/20 blur-3xl md:h-72 md:w-72"
      />
      <div
        className="marketing-glow-breathe absolute top-[8%] right-[6%] h-64 w-64 rounded-full bg-[#06B6D4]/18 blur-3xl md:h-80 md:w-80"
        style={{ animationDelay: "-3s" }}
      />
      <div
        className="marketing-glow-breathe absolute top-[42%] left-1/2 h-[420px] w-[85%] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,#2563EB_0%,#06B6D4_38%,transparent_70%)] opacity-50 blur-3xl md:h-[520px]"
        style={{ animationDelay: "-1.5s" }}
      />
    </div>
  );
}

export function ProductAura({
  children,
  float = false,
  className,
}: {
  children: React.ReactNode;
  float?: boolean;
  className?: string;
}) {
  const reduced = usePrefersReducedMotion();

  return (
    <div className={cn("relative", className)}>
      <div
        className="pointer-events-none absolute -inset-6 rounded-[28px] bg-[radial-gradient(ellipse_at_center,rgba(37,99,235,0.22),rgba(6,182,212,0.12)_42%,transparent_70%)] blur-2xl md:-inset-10 md:blur-3xl"
        aria-hidden
      />
      <div className={cn("relative", float && !reduced && "md:screenshot-float")}>{children}</div>
    </div>
  );
}

export function CtaAtmosphere() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <div className="marketing-glow-breathe absolute top-1/2 left-1/2 h-64 w-[min(80%,36rem)] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,#2563EB_0%,#06B6D4_40%,transparent_70%)] blur-3xl" />
    </div>
  );
}
