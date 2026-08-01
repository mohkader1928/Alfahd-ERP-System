"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import en from "./en.json";
import ar from "./ar.json";

export type Locale = "en" | "ar";

const DICTIONARIES: Record<Locale, Record<string, string>> = { en, ar };
const STORAGE_KEY = "erp.locale";

interface I18nContextValue {
  locale: Locale;
  dir: "ltr" | "rtl";
  t: (key: string) => string;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
}

const I18nContext = createContext<I18nContextValue | null>(null);

// FR-CORE-031: RTL for Arabic, LTR for English — flips the entire document
// direction, not just text alignment, so layout (sidebars, icons) mirrors too.
function applyDocumentDirection(locale: Locale) {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("ar");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY) as Locale | null;
    const initial = stored === "en" || stored === "ar" ? stored : "ar";
    // Reading localStorage in the initializer would desync SSR output from
    // the client's first render and trigger a hydration mismatch — the
    // default "ar" render is intentional; this effect corrects it right
    // after mount instead.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocaleState(initial);
    applyDocumentDirection(initial);
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
    applyDocumentDirection(next);
  }, []);

  const toggleLocale = useCallback(() => {
    setLocale(locale === "ar" ? "en" : "ar");
  }, [locale, setLocale]);

  const t = useCallback(
    (key: string) => DICTIONARIES[locale][key] ?? DICTIONARIES.en[key] ?? key,
    [locale]
  );

  const value = useMemo(
    () => ({ locale, dir: (locale === "ar" ? "rtl" : "ltr") as "ltr" | "rtl", t, setLocale, toggleLocale }),
    [locale, t, setLocale, toggleLocale]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
