"""S0.2 — unified secret access. Offline, stdlib only. Run: python3 tests/test_secrets.py"""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runtime import secrets as S  # noqa: E402


class FakeKeyring:
    def __init__(self, store): self.store = store
    def get_password(self, service, key): return self.store.get(key)


class BackendlessKeyring:
    def get_password(self, service, key): raise RuntimeError("No keyring backend (WSL)")


def _clean(*keys):
    for k in keys: os.environ.pop(k, None)
    S.reset_keyring()


def test_env_hit_takes_precedence():
    os.environ["NEOS_T1"] = "from-env"
    S.set_keyring(FakeKeyring({"NEOS_T1": "from-keyring"}))
    assert S.get("NEOS_T1") == "from-env"   # env wins
    _clean("NEOS_T1")
    print("PASS test_env_hit_takes_precedence")


def test_keyring_fallback_when_env_absent():
    _clean("NEOS_T2")
    S.set_keyring(FakeKeyring({"NEOS_T2": "from-keyring"}))
    assert S.get("NEOS_T2") == "from-keyring"
    _clean("NEOS_T2")
    print("PASS test_keyring_fallback_when_env_absent")


def test_required_missing_raises_loud():
    _clean("NEOS_MISSING")
    S.set_keyring(None)   # no keyring (WSL/CI)
    try:
        S.get("NEOS_MISSING")
        assert False, "expected SecretError"
    except S.SecretError as e:
        assert "NEOS_MISSING" in str(e)
    print("PASS test_required_missing_raises_loud")


def test_not_required_returns_none():
    _clean("NEOS_OPT"); S.set_keyring(None)
    assert S.get("NEOS_OPT", required=False) is None
    assert S.get("NEOS_OPT", required=False, default="d") == "d"
    print("PASS test_not_required_returns_none")


def test_blank_value_is_absent():
    os.environ["NEOS_BLANK"] = "   "
    S.set_keyring(FakeKeyring({"NEOS_BLANK": "real"}))
    assert S.get("NEOS_BLANK") == "real"   # whitespace env ⇒ absent ⇒ keyring
    _clean("NEOS_BLANK")
    print("PASS test_blank_value_is_absent")


def test_backendless_keyring_falls_through():
    _clean("NEOS_NOBACKEND")
    S.set_keyring(BackendlessKeyring())   # WSL: import ok, get_password raises
    assert S.get("NEOS_NOBACKEND", required=False) is None   # caught, no crash
    _clean("NEOS_NOBACKEND")
    print("PASS test_backendless_keyring_falls_through")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL SECRETS TESTS PASS")
