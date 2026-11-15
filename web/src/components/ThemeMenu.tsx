import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { THEME_NAMES, THEMES, useTheme, type Theme } from "../theme";

/**
 * The theme picker: a 44 px dot cluster in the header, opening a three-row
 * panel. Same interaction contract as the language menu — ordinary buttons,
 * aria-pressed, Escape returns focus — so it works without a custom listbox.
 *
 * The swatches are drawn by CSS from the theme tokens, so a new theme only
 * needs a token block and one row here.
 */
export function ThemeMenu() {
  const { m } = useI18n();
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

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

  const choose = (next: Theme) => {
    setTheme(next);
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
        aria-controls="theme-menu"
        aria-label={`${m.header.theme}: ${THEME_NAMES[theme]}`}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="theme-glyph" aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
        </span>
      </button>

      {open && (
        <div
          id="theme-menu"
          className="lang-menu theme-menu"
          role="group"
          aria-label={m.header.theme}
        >
          {THEMES.map((option) => (
            <button
              key={option}
              type="button"
              className="lang-option theme-option"
              aria-pressed={theme === option}
              onClick={() => choose(option)}
            >
              <span
                className="theme-swatch"
                data-theme-swatch={option}
                aria-hidden="true"
              >
                <i />
                <i />
                <i />
                <i />
              </span>
              <span className="theme-name">{THEME_NAMES[option]}</span>
              {theme === option && (
                <span className="lang-check" aria-hidden="true">
                  ✓
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
