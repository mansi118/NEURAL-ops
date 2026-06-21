# Decision: Secrets posture (S0.2)

**Status:** settled 2026-06-21 · **Owner:** ML · scope: NEURAL-ops runtime + nc-* services + Convex.

## The question
S3/§3.2.2 says "all secrets → keyring" (OS keychain). S0.1's container design injected secrets via
Docker secrets / AWS Secrets Manager. Conflict?

## Decision — NOT a conflict: three CONTEXTS behind ONE `secrets.get(KEY)` abstraction
A secret is resolved by a single precedence chain — **injected env → OS keyring → REFUSE** — and the
*source* differs per context, transparently to callers:

1. **Dev box** → OS `keyring` (S3 §3.2.2): macOS Keychain / Windows Credential Manager / Linux Secret
   Service. **WSL has no Secret Service backend** → keyring is absent there, so dev-on-WSL/CI falls back
   to plain env. (Do NOT make `keyring` a hard dependency — it must be optional/lazy or CI breaks on WSL.)
2. **Deployed container** → there is no OS keychain in a container: **Docker secrets** (`/run/secrets/*`,
   the S0.1 entrypoint already loads them into env) or **AWS Secrets Manager** (injected as env). Both
   land as env vars → the same `secrets.get` reads them.
3. **Convex deployment** → a third mechanism: Convex env vars (`npx convex env set`) for the server-side
   embedder/LLM keys that Convex functions read via `process.env`. Out of `secrets.get`'s scope (Convex
   functions can't import Python); managed separately.

## Consequence
- `runtime/secrets.py` implements `get(key, required=True)` with precedence env → keyring → refuse.
- Every `os.environ.get(<SECRET>)` read-site migrates to `secrets.get(...)`.
- `.env` ends empty: deployed = injection; dev = keyring (or env on WSL); CI = env.
- Refuse is loud (raises `SecretError`) — never a silent default (the "fail loud" invariant).
- Non-secret config (e.g. `CLASSIFIER_PROVIDER`, URLs) stays on plain env — only credentials move.

Supersedes the open keyring-vs-Secrets-Manager question. See also memory `s0.2-secrets-reconciliation`.
