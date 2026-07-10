import { useEffect, useState } from "react";
import { MatrixService } from "./lib/matrixService";
import { realFactory } from "./lib/realClient";
import { MATRIX_BASE_URL, APP_NAME } from "./config";
import ChatView from "./components/ChatView";
import { resolveInitialTheme, toggleTheme, persistTheme, applyTheme, type Theme } from "./lib/theme";

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() =>
    resolveInitialTheme(
      typeof localStorage !== "undefined" ? localStorage : null,
      typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches,
    ),
  );
  useEffect(() => {
    if (typeof document !== "undefined") applyTheme(document, theme);
  }, [theme]);
  return [
    theme,
    () =>
      setTheme((t) => {
        const next = toggleTheme(t);
        if (typeof localStorage !== "undefined") persistTheme(localStorage, next);
        return next;
      }),
  ];
}

function BrandMark() {
  return <span className="nc-brand-mark" aria-hidden>◈</span>;
}

// PR-A scaffold surface: a login screen that authenticates against the live Synapse and lists the
// user's rooms. Core chat (timeline/composer/NEop rendering) lands in PR-B; this proves the seam.
export default function App() {
  const [svc] = useState(() => new MatrixService(MATRIX_BASE_URL, realFactory));
  const [theme, flipTheme] = useTheme();
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const themeToggle = (
    <button className="nc-theme-toggle" onClick={flipTheme} title="Toggle theme">
      {theme === "dark" ? "☾" : "☀"}
    </button>
  );

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await svc.login(user, password);
      await svc.start();
      setReady(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (ready && svc.isLoggedIn()) {
    return (
      <main className="nc-app nc-app-chat">
        <header className="nc-topbar">
          <h1>
            <BrandMark /> {APP_NAME}
          </h1>
          <span className="nc-who">{svc.currentUserId()}</span>
          {themeToggle}
        </header>
        <ChatView svc={svc} />
      </main>
    );
  }

  return (
    <main className="nc-app nc-login">
      <div className="nc-login-top">{themeToggle}</div>
      <h1>
        <BrandMark /> {APP_NAME}
      </h1>
      <form onSubmit={onLogin}>
        <label>
          Username
          <input value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        <button type="submit" disabled={busy || !user || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      {error && <p className="nc-error">{error}</p>}
    </main>
  );
}
