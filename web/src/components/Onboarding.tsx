import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { Mascot } from "./Mascot";

export function Onboarding({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { m } = useI18n();
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!open) return;
    setStep(0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const steps = m.tour.steps;
  const s = steps[step];
  const last = step === steps.length - 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-paper/85 p-4 backdrop-blur-sm sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tour-title"
    >
      <div className="anim-in tour-sheet">
        <div className="mb-4 flex justify-center">
          <Mascot state={s.state} size={96} />
        </div>

        <h2
          id="tour-title"
          className="text-center display text-2xl leading-snug text-ink"
        >
          {s.title}
        </h2>
        <p className="mt-1 text-center font-indic text-[12px] tracking-[0.02em] text-muted">
          {s.caption}
        </p>
        <p className="mt-4 text-center font-indic text-lg leading-relaxed text-muted">
          {s.body}
        </p>

        <div className="mt-6 flex items-center justify-between">
          <button
            type="button"
            onClick={onClose}
            className="min-h-11 px-2 text-sm text-muted underline underline-offset-4 hover:text-ink"
          >
            {m.tour.skip}
          </button>

          <div className="flex items-center gap-1.5" aria-hidden="true">
            {steps.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 rounded-full transition-all ${
                  i === step ? "w-5 bg-accent-text" : "w-1.5 bg-line"
                }`}
              />
            ))}
          </div>

          <button
            type="button"
            onClick={() => (last ? onClose() : setStep(step + 1))}
            className="btn-primary"
          >
            {last ? m.tour.start : m.tour.next}
          </button>
        </div>
      </div>
    </div>
  );
}
