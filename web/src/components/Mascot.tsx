import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { useTheme } from "../theme";
import { drawMascot, readColours } from "./dotPeacock";
import type { MascotState } from "./peacock";

export type { MascotState } from "./peacock";

/**
 * Sakhi — the state indicator, never decoration.
 *
 * The geometry is the traced peacock in `peacock.ts`; `dotPeacock.ts` stamps it
 * as a dot-matrix sprite. Arcs pulse only while listening, the beak opens only
 * while speaking, and the `?` disc replaces the arcs when a segment was
 * missed — the same rules the SVG version carried, in the same state language.
 */
export function Mascot({
  state = "idle",
  size = 40,
  className = "",
}: {
  state?: MascotState;
  size?: number;
  className?: string;
}) {
  const { m } = useI18n();
  const { theme } = useTheme();
  const canvas = useRef<HTMLCanvasElement>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;

    const paint = (time = 0) => {
      drawMascot(element, size, state, readColours(), time);
    };
    paint();

    if (state !== "listening" || reduced) return;
    let frame = 0;
    let last = 0;
    const loop = (now: number) => {
      if (now - last > 55) {
        last = now;
        paint(now);
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [state, size, theme, reduced]);

  return (
    <canvas
      ref={canvas}
      className={className}
      role="img"
      aria-label={`${m.mascot.name}, ${m.mascot[state]}`}
      width={size}
      height={size}
    />
  );
}

/** One listener per component is cheap and keeps the animation rule local. */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
