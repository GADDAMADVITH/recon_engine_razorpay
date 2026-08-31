import { useCallback } from "react";
import type { LenisOptions } from "lenis";
import { ReactLenis, useLenis } from "lenis/react";
import { motion, useMotionValue } from "motion/react";
import { createPortal } from "react-dom";
import { usePrefersReducedMotion } from "./motion";

const LENIS_OPTIONS: LenisOptions = {
  duration: 1.1,
  easing: (t) => 1 - (1 - t) ** 3,
  autoRaf: true,
  smoothWheel: true,
  syncTouch: false,
  anchors: { offset: -80, duration: 1.1 },
  respectReducedMotion: true,
};

function ScrollProgress() {
  const progress = useMotionValue(0);
  const onScroll = useCallback((lenis: { progress: number }) => {
    progress.set(lenis.progress);
  }, [progress]);

  useLenis(onScroll);

  if (typeof document === "undefined") return null;

  return createPortal(
    <motion.div
      aria-hidden
      className="pointer-events-none fixed top-0 left-0 z-[60] h-[2px] w-full origin-left bg-gradient-to-r from-[#2563EB] to-[#06B6D4]"
      style={{ scaleX: progress }}
    />,
    document.body,
  );
}

export function LandingExperience({ children }: { children: React.ReactNode }) {
  const reduced = usePrefersReducedMotion();

  if (reduced) {
    return <>{children}</>;
  }

  return (
    <ReactLenis root options={LENIS_OPTIONS}>
      <ScrollProgress />
      {children}
    </ReactLenis>
  );
}
