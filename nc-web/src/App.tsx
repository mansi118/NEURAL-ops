import { useState } from "react";
import { MatrixService, type RoomSummary } from "./lib/matrixService";
import { realFactory } from "./lib/realClient";
import { MATRIX_BASE_URL, APP_NAME } from "./config";

// PR-A scaffold surface: a login screen that authenticates against the live Synapse and lists the
// user's rooms. Core chat (timeline/composer/NEop rendering) lands in PR-B; this proves the seam.
export default function App() {
  const [svc] = useState(() => new MatrixService(MATRIX_BASE_URL, realFactory));
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [rooms, setRooms] = useState<RoomSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await svc.login(user, password);
      await svc.start();
      setRooms(svc.rooms());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (svc.isLoggedIn()) {
    return (
      <main className="nc-app">
        <h1>{APP_NAME}</h1>
        <p className="nc-who">Signed in as {svc.currentUserId()}</p>
        <h2>Rooms</h2>
        <ul className="nc-rooms">
          {rooms.map((r) => (
            <li key={r.roomId}>{r.name || r.roomId}</li>
          ))}
        </ul>
      </main>
    );
  }

  return (
    <main className="nc-app nc-login">
      <h1>{APP_NAME}</h1>
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
