"""Boot self-check for the NEOS runtime container (S0.1).

Credential-gated: the container REFUSES to start (non-zero exit, clear message) if a
REQUIRED secret/config is absent — never a silent no-op. Pure env inspection; makes NO
network calls. Backends are reached lazily + credential-gated at call time (see
runtime/memory.py, runtime/aws.py); this surfaces a missing-credential failure at BOOT
rather than mid-run.

Required (the runtime cannot function without these):
  CONVEX_SITE_URL | CONVEX_DEPLOYMENT_URL   — MemPalace SoT endpoint (broker target)
  ANTHROPIC_API_KEY                          — classifier/model primary (direct Anthropic)
Recommended (degraded-but-runnable if absent — warn only):
  OPENROUTER_API_KEY                         — classifier fallback
  GRAPHITI_BRIDGE_URL | FALKORDB_HOST        — advisory entity graph (may be down)
"""
from __future__ import annotations
import os, sys

# (label, alternative-env-keys) — any one key present satisfies the group.
REQUIRED = [
    ("MemPalace SoT endpoint", ("CONVEX_SITE_URL", "CONVEX_DEPLOYMENT_URL")),
    ("classifier/model primary (direct Anthropic)", ("ANTHROPIC_API_KEY",)),
]
RECOMMENDED = [
    ("classifier fallback (OpenRouter)", ("OPENROUTER_API_KEY",)),
    ("advisory entity graph", ("GRAPHITI_BRIDGE_URL", "FALKORDB_HOST")),
]


def _present(env, keys) -> bool:
    return any((env.get(k) or "").strip() for k in keys)


def check(env=None):
    """Pure: returns (ok, errors, warnings). No network, no process exit."""
    env = os.environ if env is None else env
    errors, warnings = [], []
    for label, keys in REQUIRED:
        if not _present(env, keys):
            errors.append(f"missing REQUIRED {label}: set one of {', '.join(keys)}")
    for label, keys in RECOMMENDED:
        if not _present(env, keys):
            warnings.append(f"missing recommended {label}: set one of {', '.join(keys)} (running degraded)")
    return (not errors, errors, warnings)


def main(argv=None) -> int:
    ok, errors, warnings = check()
    for w in warnings:
        print(f"[selfcheck] WARN  {w}", file=sys.stderr)
    if not ok:
        for e in errors:
            print(f"[selfcheck] FATAL {e}", file=sys.stderr)
        print("[selfcheck] refusing to start — required credentials/config absent.", file=sys.stderr)
        return 1
    print(f"[selfcheck] ok — required config present"
          + (f"; {len(warnings)} warning(s)" if warnings else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
