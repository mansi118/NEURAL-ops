"""Boot self-check for the NEOS runtime container (S0.1).

Credential-gated: the container REFUSES to start (non-zero exit, clear message) if a
REQUIRED secret/config is absent — never a silent no-op. Pure env inspection; makes NO
network calls. Backends are reached lazily + credential-gated at call time (see
runtime/memory.py, runtime/aws.py); this surfaces a missing-credential failure at BOOT
rather than mid-run.

Required (the runtime cannot function without these):
  CONVEX_SITE_URL | CONVEX_DEPLOYMENT_URL   — MemPalace SoT endpoint (broker target)
  the CONFIGURED primary provider's key      — CLASSIFIER_PROVIDER picks it (default anthropic →
                                               ANTHROPIC_API_KEY). The primary is required AT BOOT;
                                               a fallback is runtime-resilience, NOT a boot substitute.
Recommended (degraded-but-runnable if absent — warn only):
  the fallback provider's key                — classifier fallback (OpenRouter, or Anthropic if the
                                               primary IS OpenRouter)
  GRAPHITI_BRIDGE_URL | FALKORDB_HOST        — advisory entity graph (may be down)
"""
from __future__ import annotations
import os, sys

# Provider → its credential key(s). The CONFIGURED primary's key is required at boot.
PROVIDER_KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "gemini": ("GEMINI_API_KEY",),
    "bedrock": ("AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY"),
}
DEFAULT_PROVIDER = "anthropic"


def _present(env, keys) -> bool:
    return any((env.get(k) or "").strip() for k in keys)


def check(env=None):
    """Pure: returns (ok, errors, warnings). No network, no process exit.

    The required model credential follows CLASSIFIER_PROVIDER (the configured primary) — so
    the boot gate stays correct if the primary is ever switched, instead of hardcoding one."""
    env = os.environ if env is None else env
    provider = (env.get("CLASSIFIER_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    primary_keys = PROVIDER_KEYS.get(provider, PROVIDER_KEYS[DEFAULT_PROVIDER])
    # Fallback = the other standard provider; its absence is a resilience gap, not a boot stopper.
    fallback_keys = ("OPENROUTER_API_KEY",) if provider != "openrouter" else ("ANTHROPIC_API_KEY",)

    required = [
        ("MemPalace SoT endpoint", ("CONVEX_SITE_URL", "CONVEX_DEPLOYMENT_URL")),
        (f"classifier/model primary [{provider}]", primary_keys),
    ]
    recommended = [
        ("classifier fallback", fallback_keys),
        ("advisory entity graph", ("GRAPHITI_BRIDGE_URL", "FALKORDB_HOST")),
    ]

    errors, warnings = [], []
    for label, keys in required:
        if not _present(env, keys):
            errors.append(f"missing REQUIRED {label}: set one of {', '.join(keys)}")
    for label, keys in recommended:
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
