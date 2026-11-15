import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { LOCALES, type Locale } from "../i18n/locales";

/**
 * The language picker: a 44 px globe in the header, opening a four-row panel.
 * The whole panel is ordinary buttons with aria-pressed, so Tab and Enter work
 * without a custom listbox; Escape closes it and returns focus to the trigger.
 */
export function LanguageMenu() {
  const { locale, setLocale, m } = useI18n();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const current = LOCALES.find((l) => l.code === locale) ?? LOCALES[0];

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const choose = (code: Locale) => {
    setLocale(code);
    setOpen(false);
    trigger.current?.focus();
  };

  return (
    <div className="relative" ref={wrap}>
      <button
        ref={trigger}
        type="button"
        className="icon-btn"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="language-menu"
        aria-label={`${m.header.language}: ${current.native}`}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="lang-trigger" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            width="14"
            height="14"
            fill="none"
            aria-hidden="true"
          >
            <circle
              cx="12"
              cy="12"
              r="9"
              stroke="currentColor"
              strokeWidth="1.8"
            />
            <path
              d="M3 12h18M12 3c2.7 3 2.7 15 0 18M12 3c-2.7 3-2.7 15 0 18"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          <span className="lang-code">{current.short}</span>
        </span>
      </button>

      {open && (
        <div
          id="language-menu"
          className="lang-menu"
          role="group"
          aria-label={m.header.language}
        >
          {LOCALES.map((option) => {
            const active = option.code === locale;
            return (
              <button
                key={option.code}
                type="button"
                className="lang-option"
                aria-pressed={active}
                lang={option.code}
                autoFocus={active}
                onClick={() => choose(option.code)}
              >
                <span className="lang-text">
                  <span className="lang-native">{option.native}</span>
                  {option.label !== option.native && (
                    <span className="lang-label" lang="en">
                      {option.label}
                    </span>
                  )}
                </span>
                {active && (
                  <span className="lang-check" aria-hidden="true">
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
