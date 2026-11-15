/**
 * The end-of-call card.
 *
 * The fields come from the backend (#4): `who` is the first caller line
 * shortened to ~60 characters, `agreed` the last caller line, `next` the last
 * reply we spoke. The card is the demo's payoff frame, so it stays inside one
 * 4:5 screen: the title clamps to three lines and the two rows to three each.
 */
import { useI18n } from "../i18n";
import type { Summary } from "../types";

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${String(seconds % 60).padStart(2, "0")}s`;
}

export function SummaryCard({ summary }: { summary: Summary }) {
  const { m } = useI18n();

  return (
    <section
      className="summary-card"
      aria-labelledby="summary-title"
      aria-live="polite"
    >
      <p className="summary-eyebrow">{m.summary.eyebrow}</p>
      <h2 id="summary-title" className="summary-title">
        {summary.who}
      </h2>

      <div className="summary-rule" role="presentation" />

      <dl>
        <div className="summary-row">
          <dt className="summary-label">{m.summary.agreed}</dt>
          <dd className="summary-value">{summary.agreed}</dd>
        </div>
        <div className="summary-row">
          <dt className="summary-label">{m.summary.next}</dt>
          <dd className="summary-value">{summary.next}</dd>
        </div>
      </dl>

      <p className="summary-meta">
        {m.summary.turns(summary.turns)} · {formatDuration(summary.duration_s)}
      </p>
    </section>
  );
}
