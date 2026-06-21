"""Unified secret access (S0.2) — `secrets.get(KEY)` over three contexts behind ONE abstraction.

Precedence: injected ENV (Docker secrets / AWS Secrets Manager / plain env in dev/CI) → OS keyring
(dev box where a backend exists) → REFUSE (raise; never a silent default — the "fail loud" invariant).
This lets `.env` be emptied: deployed = injection, dev = keyring (or env on WSL), CI = env.
See docs/decisions/secrets-posture.md.

Offline-gradeable: the OS keyring is OPTIONAL + lazy (WSL has no Secret Service backend, so it must
never be a hard dependency); tests inject a fake via `set_keyring()`. No network. core.py untouched.
Only CREDENTIALS move here — non-secret config (CLASSIFIER_PROVIDER, URLs) stays on plain env.
"""
from __future__ import annotations
import os

_SERVICE = "neos"          # keyring service namespace
_keyring = None            # lazily resolved OS keyring (or a test fake)
_keyring_resolved = False


class SecretError(RuntimeError):
    """A required secret was not found in any source. Loud by design."""


def set_keyring(kr) -> None:
    """Test/seam hook: inject a keyring (object with get_password(service, key)) or None."""
    global _keyring, _keyring_resolved
    _keyring, _keyring_resolved = kr, True


def reset_keyring() -> None:
    """Forget the resolved keyring (tests)."""
    global _keyring, _keyring_resolved
    _keyring, _keyring_resolved = None, False


def _resolve_keyring():
    global _keyring, _keyring_resolved
    if _keyring_resolved:
        return _keyring
    _keyring_resolved = True
    try:
        import keyring as _kr  # optional dep; absent/backendless on WSL
        _keyring = _kr
    except Exception:
        _keyring = None
    return _keyring


def _present(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def get(key: str, *, required: bool = True, default=None):
    """Resolve a secret: env → keyring → (default | refuse). Blank/whitespace counts as absent."""
    v = os.environ.get(key)
    if _present(v):
        return v

    kr = _resolve_keyring()
    if kr is not None:
        try:
            v = kr.get_password(_SERVICE, key)
            if _present(v):
                return v
        except Exception:
            pass  # backendless keyring (e.g. WSL) → fall through to default/refuse

    if default is not None:
        return default
    if required:
        raise SecretError(
            f"secret '{key}' not found — set it via env (injection / Docker secrets / Secrets Manager) "
            f"or the OS keyring (service '{_SERVICE}'); never hard-code it"
        )
    return None
