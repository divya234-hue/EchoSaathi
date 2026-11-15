import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * Three grounds, one design language: a dot screen with panels punched into it.
 *
 * Peacock is the dark acid-lime field, Lime Wash the daylight one, Slate the
 * teal-and-gold one. They are not "light/dark" flips of one palette — each has
 * its own ink, signal and accent — so the choice lives in a menu, not a toggle.
 * Contrast per theme is measured in DECISIONS.md D-015; body text clears 7:1
 * on every ground.
 */
export const THEMES = ["peacock", "limewash", "slate"] as const;

export type Theme = (typeof THEMES)[number];

/** Theme names are product nouns, like the wordmark: they stay Latin. */
export const THEME_NAMES: Record<Theme, string> = {
  peacock: "Peacock",
  limewash: "Lime wash",
  slate: "Slate",
};

/** The browser chrome colour, kept in step with `--paper` per theme. */
const THEME_COLOURS: Record<Theme, string> = {
  peacock: "#0b110a",
  limewash: "#f1eddd",
  slate: "#08201e",
};

const KEY = "pashyanti.theme";

function isTheme(value: string | null): value is Theme {
  return value !== null && (THEMES as readonly string[]).includes(value);
}

/** `?theme=` wins over the saved choice so a screenshot or link is deterministic. */
function readInitialTheme(): Theme {
  if (typeof window === "undefined") return "peacock";
  const forced = new URLSearchParams(window.location.search).get("theme");
  if (isTheme(forced)) return forced;
  try {
    const saved = window.localStorage.getItem(KEY);
    if (isTheme(saved)) return saved;
  } catch {
    /* storage can be unavailable; the default still works */
  }
  return "peacock";
}

function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", THEME_COLOURS[theme]);
}

/* Applied before the first render, so the mascot and the field never paint in
   the wrong ground for a frame. */
const BOOT_THEME = readInitialTheme();
applyTheme(BOOT_THEME);

type ThemeContextValue = { theme: Theme; setTheme: (theme: Theme) => void };

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(BOOT_THEME);

  const setTheme = useCallback((next: Theme) => {
    applyTheme(next);
    setThemeState(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* storage can be unavailable; the choice just does not persist */
    }
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}
