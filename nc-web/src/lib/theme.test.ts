import { describe, it, expect } from "vitest";
import {
  resolveInitialTheme,
  toggleTheme,
  persistTheme,
  applyTheme,
  THEME_KEY,
  type StorageLike,
  type DocLike,
} from "./theme";

function fakeStorage(seed: Record<string, string> = {}): StorageLike & { data: Record<string, string> } {
  const data = { ...seed };
  return { data, getItem: (k) => data[k] ?? null, setItem: (k, v) => void (data[k] = v) };
}

describe("theme", () => {
  it("prefers a stored choice, else the system preference", () => {
    expect(resolveInitialTheme(fakeStorage({ [THEME_KEY]: "light" }), true)).toBe("light");
    expect(resolveInitialTheme(fakeStorage(), true)).toBe("dark");
    expect(resolveInitialTheme(fakeStorage(), false)).toBe("light");
    expect(resolveInitialTheme(null, true)).toBe("dark");
  });

  it("toggles and persists", () => {
    expect(toggleTheme("dark")).toBe("light");
    expect(toggleTheme("light")).toBe("dark");
    const s = fakeStorage();
    persistTheme(s, "dark");
    expect(s.data[THEME_KEY]).toBe("dark");
  });

  it("stamps data-theme on the document element", () => {
    let attr: [string, string] | null = null;
    const doc: DocLike = { documentElement: { setAttribute: (n, v) => void (attr = [n, v]) } };
    applyTheme(doc, "dark");
    expect(attr).toEqual(["data-theme", "dark"]);
  });
});
