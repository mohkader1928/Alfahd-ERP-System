"use client";

import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "erp.theme";

// Owner-requested: a color-theme picker alongside the existing light/dark
// toggle — three whole palettes (not just an accent swap), each already
// tuned for both light and dark mode in globals.css.
export type ColorTheme = "neutral" | "blue" | "green";
export const COLOR_THEMES: ColorTheme[] = ["neutral", "blue", "green"];
const COLOR_STORAGE_KEY = "erp.color-theme";

const ThemeContext = createContext<{
  theme: Theme;
  toggleTheme: () => void;
  colorTheme: ColorTheme;
  setColorTheme: (next: ColorTheme) => void;
} | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");
  const [colorTheme, setColorThemeState] = useState<ColorTheme>("neutral");

  useEffect(() => {
    const storedTheme = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
    const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const initialTheme = storedTheme ?? preferred;
    const storedColor = window.localStorage.getItem(COLOR_STORAGE_KEY) as ColorTheme | null;
    const initialColor = storedColor && COLOR_THEMES.includes(storedColor) ? storedColor : "neutral";
    // Same SSR/hydration-mismatch reasoning as I18nProvider — see that file.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(initialTheme);
    setColorThemeState(initialColor);
    document.documentElement.classList.toggle("dark", initialTheme === "dark");
    document.documentElement.setAttribute("data-color-theme", initialColor);
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      window.localStorage.setItem(STORAGE_KEY, next);
      document.documentElement.classList.toggle("dark", next === "dark");
      return next;
    });
  };

  const setColorTheme = (next: ColorTheme) => {
    window.localStorage.setItem(COLOR_STORAGE_KEY, next);
    document.documentElement.setAttribute("data-color-theme", next);
    setColorThemeState(next);
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, colorTheme, setColorTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
