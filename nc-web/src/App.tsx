import { useEffect, useState } from "react";
import { MatrixService } from "./lib/matrixService";
import { realFactory } from "./lib/realClient";
import { MATRIX_BASE_URL, APP_NAME } from "./config";
import ChatView from "./components/ChatView";
import DecisionQueue from "./components/DecisionQueue";
import FidelityDashboard from "./components/FidelityDashboard";
import { findDecisionRoom } from "./lib/proposals";
import { findFidelityRoom } from "./lib/fidelity";
import { humanizeAuthError } from "./lib/errors";
import { resolveInitialTheme, toggleTheme, persistTheme, applyTheme, type Theme } from "./lib/theme";

type View = "chat" | "queue" | "fidelity";

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
  const [view, setView] = useState<View>("chat");
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
      setError(humanizeAuthError(err));
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
          <nav className="nc-nav">
            <button className={view === "chat" ? "active" : ""} onClick={() => setView("chat")}>
              Chat
            </button>
            <button className={view === "queue" ? "active" : ""} onClick={() => setView("queue")}>
              Queue
            </button>
            <button className={view === "fidelity" ? "active" : ""} onClick={() => setView("fidelity")}>
              Fidelity
            </button>
          </nav>
          <span className="nc-who">{svc.currentUserId()}</span>
          {themeToggle}
        </header>
        {view === "chat" && <ChatView svc={svc} />}
        {view === "queue" && (
          <div className="nc-panel">
            <h2>Decision Queue</h2>
            <DecisionQueue svc={svc} roomId={findDecisionRoom(svc.rooms())?.roomId ?? null} />
          </div>
        )}
        {view === "fidelity" && (
          <div className="nc-panel">
            <h2>Fidelity</h2>
            <FidelityDashboard svc={svc} roomId={findFidelityRoom(svc.rooms())?.roomId ?? null} />
          </div>
        )}
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
      {error && <p className="nc-error" role="alert">{error}</p>}
      <p className="nc-hint">Sign in with your NeuralEdge account, then message a NEop like Aria or Recon.</p>
    </main>
  );
}
