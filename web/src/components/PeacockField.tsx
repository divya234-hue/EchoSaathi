import { useEffect, useRef } from "react";
import { useTheme } from "../theme";
import { drawField, mixHex, readColours } from "./dotPeacock";

/**
 * The field's character: Sakhi's head, ghosted into the lower half of the
 * screen — the same lattice as the page, one tone lighter, so the silhouette
 * is built out of the dots rather than laid over them.
 *
 * It is static by rule. The mascot is the state indicator; a second peacock
 * that moved would read as a second state. It is also hidden behind the empty
 * state, where the real mascot owns the screen.
 */
export function PeacockField({ className = "" }: { className?: string }) {
  const { theme } = useTheme();
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const host = element?.parentElement;
    if (!element || !host) return;

    const paint = () => {
      const colours = readColours();
      /* Light grounds carry the same tone at a lower mix: dark-on-light reads
         heavier than light-on-dark at equal ratio. */
      const tone = mixHex(colours.lattice, colours.ink, theme === "limewash" ? 0.15 : 0.2);
      drawField(element, host.clientWidth, host.clientHeight, colours.pitch, tone);
    };

    paint();
    const observer = new ResizeObserver(paint);
    observer.observe(host);
    return () => observer.disconnect();
  }, [theme]);

  return <canvas ref={canvas} className={className} aria-hidden="true" />;
}
