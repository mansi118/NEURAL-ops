// Theme — light/dark with a manual toggle over the system preference. Pure + injectable (storage +
// document are passed in), so it's unit-tested without a real DOM. The app stamps `data-theme` on
// <html>; index.css keys off both the attribute and prefers-color-scheme.
export type Theme = "light" | "dark";

export const THEME_KEY = "nc-theme";

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface DocLike {
  documentElement: { setAttribute(name: string, value: string): void };
}

/** Stored choice wins; else the system preference. */
export function resolveInitialTheme(storage: StorageLike | null, prefersDark: boolean): Theme {
  const stored = storage?.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return prefersDark ? "dark" : "light";
}

export function toggleTheme(t: Theme): Theme {
  return t === "dark" ? "light" : "dark";
}

export function persistTheme(storage: StorageLike | null, t: Theme): void {
  storage?.setItem(THEME_KEY, t);
}

export function applyTheme(doc: DocLike, t: Theme): void {
  doc.documentElement.setAttribute("data-theme", t);
}
