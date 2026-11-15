import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { en } from "./en";
import { hi } from "./hi";
import { bn } from "./bn";
import { mr } from "./mr";
import { LOCALES, type Locale } from "./locales";
import type { Messages } from "./types";

const DICTS: Record<Locale, Messages> = { en, hi, bn, mr };
const STORAGE_KEY = "divya.lang";

function isLocale(value: string | null): value is Locale {
  return value !== null && LOCALES.some((l) => l.code === value);
}

/**
 * English is the default. A `?lang=` override wins over the saved choice so a
 * screenshot or a shared link opens in a known language.
 */
function initialLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const forced = new URLSearchParams(window.location.search).get("lang");
  if (isLocale(forced)) return forced;
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(saved)) return saved;
  } catch {
    /* storage can be unavailable; the default still works */
  }
  return "en";
}

type I18nValue = {
  locale: Locale;
  m: Messages;
  setLocale: (locale: Locale) => void;
};

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dataset.locale = locale;
    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      /* the choice just will not survive a reload */
    }
  }, [locale]);

  const setLocale = useCallback((next: Locale) => setLocaleState(next), []);

  const value = useMemo(
    () => ({ locale, m: DICTS[locale], setLocale }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (value === null) {
    throw new Error("useI18n must be used inside I18nProvider");
  }
  return value;
}

export { LOCALES, type Locale };
