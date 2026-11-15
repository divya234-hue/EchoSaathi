import {
  PEACOCK_ARCS,
  PEACOCK_BADGE,
  PEACOCK_BADGE_DOT,
  PEACOCK_BADGE_MARK,
  PEACOCK_BEAK_CLOSED,
  PEACOCK_BEAK_LOWER,
  PEACOCK_BEAK_UPPER,
  PEACOCK_HEAD,
  PEACOCK_PUPIL,
  PEACOCK_SHOULDER,
  type MascotState,
} from "./peacock";

/**
 * The dot screen renderer.
 *
 * Sakhi is not redrawn here: `peacock.ts` keeps the traced geometry, and this
 * module rasterises it — fill the paths into a tiny offscreen canvas, read the
 * alpha, and stamp one round dot per cell whose radius carries the coverage.
 * The result is a halftone of the shipped mark, so the mascot can be rendered
 * at 30 px in the header and 124 px in the empty state from the same source.
 *
 * Two screens are deliberate: the mark uses a fine one (~1.8 px dots) because
 * the crest and the eye ring vanish at the field's 6 px pitch, and the field
 * keeps the coarse one. See DECISIONS.md D-015.
 */

type Ctx = CanvasRenderingContext2D;

const coverageCache = new Map<string, Float32Array>();

function coverage(key: string, n: number, draw: (ctx: Ctx) => void): Float32Array {
  const cacheKey = `${key}@${n}`;
  const cached = coverageCache.get(cacheKey);
  if (cached) return cached;

  const canvas = document.createElement("canvas");
  canvas.width = n;
  canvas.height = n;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("2D canvas is unavailable");
  ctx.setTransform(n / 100, 0, 0, n / 100, 0, 0);
  ctx.fillStyle = "#fff";
  ctx.strokeStyle = "#fff";
  draw(ctx);

  const data = ctx.getImageData(0, 0, n, n).data;
  const cells = new Float32Array(n * n);
  for (let i = 0; i < n * n; i += 1) cells[i] = data[i * 4 + 3] / 255;
  coverageCache.set(cacheKey, cells);
  return cells;
}

function bodyCoverage(state: MascotState, n: number): Float32Array {
  return coverage(`body:${state}`, n, (ctx) => {
    ctx.fill(new Path2D(PEACOCK_SHOULDER));
    ctx.fill(new Path2D(PEACOCK_HEAD));
    ctx.fill(new Path2D(PEACOCK_PUPIL));
    if (state === "speaking") {
      ctx.fill(new Path2D(PEACOCK_BEAK_UPPER));
      ctx.fill(new Path2D(PEACOCK_BEAK_LOWER));
    } else {
      ctx.fill(new Path2D(PEACOCK_BEAK_CLOSED), "evenodd");
    }
  });
}

const arcsCoverage = (n: number): Float32Array =>
  coverage("arcs", n, (ctx) => {
    for (const d of PEACOCK_ARCS) ctx.fill(new Path2D(d));
  });

/* At header size the traced ? disc is ~3 dots wide and the mark disappears.
   Below a 32-cell raster the whole badge is drawn 1.5x around its own centre,
   so the state still reads; at 96 px+ the traced proportions are untouched. */
function scaleBadge(ctx: Ctx, n: number): number {
  const k = n < 32 ? 1.5 : 1;
  if (k === 1) return k;
  ctx.translate(PEACOCK_BADGE.cx, PEACOCK_BADGE.cy);
  ctx.scale(k, k);
  ctx.translate(-PEACOCK_BADGE.cx, -PEACOCK_BADGE.cy);
  return k;
}

const badgeCoverage = (n: number): Float32Array =>
  coverage("badge", n, (ctx) => {
    scaleBadge(ctx, n);
    ctx.beginPath();
    ctx.arc(PEACOCK_BADGE.cx, PEACOCK_BADGE.cy, PEACOCK_BADGE.r, 0, Math.PI * 2);
    ctx.fill();
  });


/**
 * One dot per cell. `time` (ms) makes the listening arcs breathe; every dot
 * shares the same phase base so the row reads as sound, not noise.
 */
export function stampDots(
  ctx: Ctx,
  cells: Float32Array,
  n: number,
  pitch: number,
  colour: string,
  time = 0,
  gain = 0.94,
): void {
  ctx.fillStyle = colour;
  for (let y = 0; y < n; y += 1) {
    for (let x = 0; x < n; x += 1) {
      const alpha = cells[y * n + x];
      if (alpha < 0.1) continue;
      let radius = (pitch / 2) * gain * Math.sqrt(alpha);
      if (time > 0) {
        radius *= 1 + 0.3 * Math.sin(time * 0.0046 + x * 0.55 + y * 0.28);
      }
      radius = Math.min(radius, pitch * 0.54);
      ctx.beginPath();
      ctx.arc((x + 0.5) * pitch, (y + 0.5) * pitch, Math.max(0.35, radius), 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

export type PeacockColours = { ink: string; accent: string; paper: string };

/** Draws Sakhi into a canvas at `size` CSS px, in dot-matrix form. */
export function drawMascot(
  canvas: HTMLCanvasElement,
  size: number,
  state: MascotState,
  colours: PeacockColours,
  time = 0,
): void {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const px = Math.round(size * dpr);
  if (canvas.width !== px || canvas.height !== px) {
    canvas.width = px;
    canvas.height = px;
  }
  canvas.style.width = `${size}px`;
  canvas.style.height = `${size}px`;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, px, px);

  const n = Math.max(12, Math.min(72, Math.round(size / 1.8)));
  const pitch = px / n;

  if (state !== "unsure") {
    stampDots(ctx, arcsCoverage(n), n, pitch, colours.accent, time);
  }
  stampDots(ctx, bodyCoverage(state, n), n, pitch, colours.ink);
  if (state === "unsure") {
    stampDots(ctx, badgeCoverage(n), n, pitch, colours.accent);
    /* The disc is part of the dot screen; the `?` inside it is a state symbol
       and is stroked crisply — a sub-dot stroke at 40 px read as a smudge,
       and this is the one state whose cue must never be lost. */
    const k = n < 32 ? 1.5 : 1;
    ctx.save();
    ctx.setTransform(px / 100, 0, 0, px / 100, 0, 0);
    if (k !== 1) {
      ctx.translate(PEACOCK_BADGE.cx, PEACOCK_BADGE.cy);
      ctx.scale(k, k);
      ctx.translate(-PEACOCK_BADGE.cx, -PEACOCK_BADGE.cy);
    }
    ctx.strokeStyle = colours.paper;
    ctx.fillStyle = colours.paper;
    ctx.lineWidth = 180 / (px * k);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.stroke(new Path2D(PEACOCK_BADGE_MARK));
    ctx.beginPath();
    ctx.arc(
      PEACOCK_BADGE_DOT.cx,
      PEACOCK_BADGE_DOT.cy,
      230 / (px * k),
      0,
      Math.PI * 2,
    );
    ctx.fill();
    ctx.restore();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }
}

/**
 * The field mark: the same head, stamped on the page's own lattice so the
 * silhouette is built by recolouring dots rather than layering a second
 * screen over them. Static by rule — nothing moves when nothing is talking.
 */
export function drawField(
  canvas: HTMLCanvasElement,
  width: number,
  height: number,
  pitch: number,
  tone: string,
): void {
  if (width < 1 || height < 1) return;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const pxWidth = Math.round(width * dpr);
  const pxHeight = Math.round(height * dpr);
  if (canvas.width !== pxWidth || canvas.height !== pxHeight) {
    canvas.width = pxWidth;
    canvas.height = pxHeight;
  }

  const n = Math.max(24, Math.round(width / pitch));
  const cells = bodyCoverage("idle", n);
  const top = Math.round((height * 0.42) / pitch) * pitch;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = tone;
  for (let y = 0; y < n; y += 1) {
    const cy = top + (y + 0.5) * pitch;
    if (cy - pitch > height) break;
    for (let x = 0; x < n; x += 1) {
      const alpha = cells[y * n + x];
      if (alpha < 0.1) continue;
      const radius = Math.min((pitch / 2) * 0.58 * Math.sqrt(alpha), pitch * 0.42);
      const cx = (x + 0.5) * pitch;
      if (cx - pitch > width) break;
      ctx.beginPath();
      ctx.arc(cx, cy, Math.max(0.35, radius), 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

/** Blend two #rrggbb values; canvas cannot parse `color-mix()`. */
export function mixHex(a: string, b: string, t: number): string {
  const parse = (value: string): [number, number, number] => {
    const clean = value.trim().replace("#", "");
    if (clean.length !== 6) return [0, 0, 0];
    return [0, 2, 4].map((i) => parseInt(clean.slice(i, i + 2), 16)) as [
      number,
      number,
      number,
    ];
  };
  const [r1, g1, b1] = parse(a);
  const [r2, g2, b2] = parse(b);
  const mix = (x: number, y: number): number => Math.round(x * (1 - t) + y * t);
  return `rgb(${mix(r1, r2)}, ${mix(g1, g2)}, ${mix(b1, b2)})`;
}

/** Reads the live theme tokens, so every canvas repaints in the active ground. */
export function readColours(): {
  ink: string;
  accent: string;
  paper: string;
  lattice: string;
  pitch: number;
} {
  const style = getComputedStyle(document.documentElement);
  return {
    ink: style.getPropertyValue("--ink").trim(),
    accent: style.getPropertyValue("--accent").trim(),
    paper: style.getPropertyValue("--paper").trim(),
    lattice: style.getPropertyValue("--lattice").trim(),
    pitch: Number.parseFloat(style.getPropertyValue("--pitch")) || 6,
  };
}
