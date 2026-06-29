"""palace_mcp_shim — the tenant chokepoint (plan §3.1, task T1).

A small stdio MCP server that jcode launches via its command-based ``mcp.json``. It exposes ONLY the
allowlisted CORTEX-PALACE tools and forwards them to the live HTTP ``/mcp`` endpoint with the
``(palaceId, neopId)`` scope **baked in from the process environment — never accepted from the
model.** One shim process == one seat; scope is fixed for the life of the process.

WHY THIS IS THE ISOLATION BOUNDARY (verified 2026-06-18 — see repo-root CLAUDE.md):
  * ``/mcp`` does NOT verify any signature today. ``convex/access/enforce.ts:316`` marks signed
    ``X-NEop-Identity`` as DEFERRED (Gate D / S0.3+); ``convex/http.ts:75`` resolves identity as
    ``neopId = body.neopId ?? header "X-Palace-Neop" ?? "_admin"``. So the Ed25519 signing below is
    forward-looking defense-in-depth, NOT a live server-side trust boundary yet.
  * The guarantees that ARE enforced in v1:
      1. scope is injected here from env and the model is rejected if it tries to supply it;
      2. the shim REFUSES TO START on blank PALACE_ID / NEOP_ID (fail-closed) — because the palace
         defaults a missing neopId to ``_admin``, which BYPASSES all ACL. Blank scope must never
         silently escalate. This mirrors the broker's ``_require_scope`` (NEURAL-ops Gate C).
      3. the container egress jail (IsolationUnit, T2) restricts where this process can talk.

REAL ``/mcp`` REQUEST CONTRACT (verified via tools/dogfish_acl_smoke.py — NOT the plan's
``{**args, ...}`` pseudocode):
    POST {PALACE_MCP_URL}
    body   = {"tool": <name>, "palaceId": <pid>, "neopId": <seat>, "params": <tool args>}
    header = X-Palace-Neop: <seat>     (defense-in-depth duplicate of body.neopId)

Env injected per seat by ConfigRenderer (T2):
    PALACE_MCP_URL          full .convex.site/mcp endpoint (HTTP actions live on .site, NOT .cloud)
    PALACE_ID               tenant (palaceId)
    NEOP_ID                 seat (neopId)
    PALACE_SIGNING_KEY_REF  optional keyref → secret store, NEVER plaintext. forms: "env:NAME" |
                            "file:/path"; value = base64 of a 32-byte Ed25519 private seed.
    PALACE_ENABLE_GET_CLOSET  "1" to allow palace_get_closet (only after Mempalace T8 registers it).
    NEOP_AUDIT_DIR          optional dir for the jsonl audit fallback (plan §3.6 pre-S0).

The security core (build_request / __init__ guards) is pure and unit-tested without network or stdio.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Callable, Optional

from .audit_tap import (
    LAYER_ADAPTER_SHIM,
    LAYER_CONVEX_SOT,
    LAYER_PALACE_ERROR,
    RESULT_ALLOW,
    RESULT_DENY,
    make_event,
)

# ── tool allowlist (plan §3.1) ────────────────────────────────────────────────
ALLOWED_TOOLS_BASE = frozenset({"palace_search", "palace_remember"})
# server-side /mcp tool NOT registered until Mempalace T8 ships it; gated off by default.
GATED_TOOLS = frozenset({"palace_get_closet"})

# keys the model must never set: scope (palaceId/neopId) or the envelope fields (tool/params).
# Palace reads scope from the top-level body only, so a smuggled key under params is inert — but we
# reject loudly rather than silently drop, so spoof attempts are visible to the audit tap.
_FORBIDDEN_ARG_KEYS = frozenset({"palaceId", "neopId", "tool", "params"})

# Convex-internal privileged identities. `_admin` BYPASSES all ACL (CLAUDE.md invariant); `_system`
# is the system scope. A seat must NEVER be one of these — blank scope defaulting to `_admin` is
# already refused, but an EXPLICIT misconfig (NEOP_ID=_admin) would otherwise be baked AND signed,
# turning the shim into a signed ACL-bypass channel. Fail-closed on both the seat and the palace.
RESERVED_IDENTITIES = frozenset({"_admin", "_system"})


class ShimError(Exception):
    """Base class for shim refusals."""


class ScopeNotConfigured(ShimError):
    """Blank PALACE_ID/NEOP_ID/PALACE_MCP_URL — fail-closed (would otherwise default to _admin)."""


class ToolRejected(ShimError):
    """Tool not on the allowlist."""


class ScopeSpoofRejected(ShimError):
    """The model tried to supply scope/envelope keys in the tool arguments."""


# ── Ed25519 signer (forward-looking; not verified server-side yet) ────────────
def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


class Ed25519Signer:
    """Thin Ed25519 signer. cryptography is imported lazily so this module imports (and the
    scope/allowlist tests run) on a box without it."""

    def __init__(self, private_key):
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        self._sk = private_key
        self._pub_b64 = _b64(
            private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        )

    @classmethod
    def generate(cls) -> "Ed25519Signer":
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_seed(cls, raw32: bytes) -> "Ed25519Signer":
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        return cls(Ed25519PrivateKey.from_private_bytes(raw32))

    @property
    def public_key_b64(self) -> str:
        return self._pub_b64

    def sign(self, message: bytes) -> str:
        return _b64(self._sk.sign(message))


def load_signer(ref: Optional[str]) -> Optional[Ed25519Signer]:
    """Resolve PALACE_SIGNING_KEY_REF → signer. Never accepts a plaintext key inline."""
    if not ref or not ref.strip():
        return None
    scheme, _, loc = ref.partition(":")
    if scheme == "env":
        val = os.environ.get(loc)
        if not val:
            raise ShimError(f"PALACE_SIGNING_KEY_REF env:{loc} is unset")
        return Ed25519Signer.from_seed(_unb64(val.strip()))
    if scheme == "file":
        with open(loc, "rb") as fh:
            return Ed25519Signer.from_seed(_unb64(fh.read().decode("ascii").strip()))
    raise ShimError(f"unsupported PALACE_SIGNING_KEY_REF scheme: {scheme!r} (use env: or file:)")


def _canonical(body: dict) -> bytes:
    """Deterministic JSON for signing (stable key order, no incidental whitespace)."""
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ── default transport + audit (both injectable for tests) ─────────────────────
def _urllib_transport(url: str, body: dict, headers: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


_DEFAULT_TAP = None
_AUDIT_DISABLED_WARNED = False


def _default_audit(event: dict) -> None:
    """Zero-config audit fallback. Writes via an AuditTap to NEOP_AUDIT_DIR if set (canonical record,
    non-fatal, log-on-drop); otherwise warns ONCE that auditing is off — never a silent no-op
    (auditable or it doesn't ship, §6). Production wires an explicit AuditTap(...).emit instead."""
    global _DEFAULT_TAP, _AUDIT_DISABLED_WARNED
    d = os.environ.get("NEOP_AUDIT_DIR")
    if not d:
        if not _AUDIT_DISABLED_WARNED:
            sys.stderr.write("palace_mcp_shim: AUDIT DISABLED (set NEOP_AUDIT_DIR or wire AuditTap)\n")
            sys.stderr.flush()
            _AUDIT_DISABLED_WARNED = True
        return
    if _DEFAULT_TAP is None or _DEFAULT_TAP.audit_dir != d:
        from .audit_tap import AuditTap

        _DEFAULT_TAP = AuditTap(d)
    _DEFAULT_TAP.emit(event)


# ── the shim ──────────────────────────────────────────────────────────────────
class PalaceShim:
    def __init__(
        self,
        *,
        palace_url: str,
        palace_id: str,
        neop_id: str,
        signing_key_ref: Optional[str] = None,
        enable_get_closet: bool = False,
        transport: Optional[Callable[[str, dict, dict], tuple[int, dict]]] = None,
        audit: Optional[Callable[[dict], None]] = None,
    ):
        # Fail-closed: blank scope would default to _admin server-side and bypass all ACL.
        if not (palace_id and palace_id.strip()):
            raise ScopeNotConfigured("PALACE_ID is blank")
        if not (neop_id and neop_id.strip()):
            raise ScopeNotConfigured("NEOP_ID is blank")
        if not (palace_url and palace_url.strip()):
            raise ScopeNotConfigured("PALACE_MCP_URL is blank")
        # Defense-in-depth: refuse a seat (or palace) configured AS a privileged bypass identity.
        # Blank already fails closed above; this closes the EXPLICIT-misconfig path (NEOP_ID=_admin),
        # which would otherwise be baked + signed into every request as a signed ACL bypass.
        if neop_id.strip() in RESERVED_IDENTITIES:
            raise ScopeNotConfigured(f"NEOP_ID '{neop_id.strip()}' is a reserved privileged identity")
        if palace_id.strip() in RESERVED_IDENTITIES:
            raise ScopeNotConfigured(f"PALACE_ID '{palace_id.strip()}' is a reserved privileged identity")
        self.palace_url = palace_url.strip()
        self.palace_id = palace_id.strip()
        self.neop_id = neop_id.strip()
        self.allowed = ALLOWED_TOOLS_BASE | (GATED_TOOLS if enable_get_closet else frozenset())
        self._signer = load_signer(signing_key_ref)
        self._transport = transport or _urllib_transport
        self._audit = audit or _default_audit

    # --- pure security core (unit-tested without network) ---
    def build_request(self, name: str, args: Optional[dict]) -> tuple[dict, dict]:
        if name not in self.allowed:
            raise ToolRejected(name)
        args = dict(args or {})
        spoofed = _FORBIDDEN_ARG_KEYS.intersection(args)
        if spoofed:
            raise ScopeSpoofRejected(f"model supplied forbidden keys: {sorted(spoofed)}")
        # Real /mcp envelope (verified). Scope comes from env, NEVER from args.
        body = {
            "tool": name,
            "palaceId": self.palace_id,
            "neopId": self.neop_id,
            "params": args,
        }
        headers = {"Content-Type": "application/json", "X-Palace-Neop": self.neop_id}
        if self._signer is not None:
            headers["X-NEop-Signature"] = self._signer.sign(_canonical(body))
            headers["X-NEop-Pubkey"] = self._signer.public_key_b64
            # NB: not verified by /mcp yet (Gate D deferred) — load-bearing once Layer 2 lands.
        return body, headers

    def _permission(self) -> dict:
        # honest-caller posture: scope is env-baked here, signed but not yet server-verified (Gate D).
        return {"scope": "env-baked", "signed": self._signer is not None}

    def call(self, name: str, args: Optional[dict]) -> dict:
        arg_keys = sorted((args or {}).keys())
        # Audit DENIES as well as allows — the audit stream is the only leak-detector while the ACL is
        # honest-caller (a denial-only or allow-only log can't prove "zero isolation violations").
        try:
            body, headers = self.build_request(name, args)
        except ToolRejected:
            self._audit(make_event(
                palace_id=self.palace_id, neop_id=self.neop_id, action=name, result=RESULT_DENY,
                denied_at_layer=LAYER_ADAPTER_SHIM, reason="tool_not_allowlisted",
                permission=self._permission(), arg_keys=arg_keys))
            raise
        except ScopeSpoofRejected:
            attempted = sorted(_FORBIDDEN_ARG_KEYS.intersection(args or {}))  # KEYS only, never values
            self._audit(make_event(
                palace_id=self.palace_id, neop_id=self.neop_id, action=name, result=RESULT_DENY,
                denied_at_layer=LAYER_ADAPTER_SHIM, reason="scope_spoof",
                target={"attempted_keys": attempted}, permission=self._permission(), arg_keys=arg_keys))
            raise

        status, resp = self._transport(self.palace_url, body, headers)
        rstatus = resp.get("status") if isinstance(resp, dict) else None
        allowed = status == 200 and rstatus == "ok"
        self._audit(make_event(
            palace_id=self.palace_id, neop_id=self.neop_id, action=name,
            result=RESULT_ALLOW if allowed else RESULT_DENY,
            denied_at_layer=None if allowed else (LAYER_CONVEX_SOT if status == 403 else LAYER_PALACE_ERROR),
            permission=self._permission(), http_status=status, result_status=rstatus, arg_keys=arg_keys))
        return {"http_status": status, "response": resp}

    # --- MCP tool advertisement ---
    def tool_descriptors(self) -> list[dict]:
        schemas = {
            "palace_search": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
            "palace_remember": {
                "type": "object",
                "properties": {
                    "wingName": {"type": "string"},
                    "content": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": ["content"],
            },
            "palace_get_closet": {
                "type": "object",
                "properties": {"closetId": {"type": "string"}},
                "required": ["closetId"],
            },
        }
        return [
            {
                "name": t,
                "description": f"CORTEX-PALACE {t} for seat {self.neop_id} (scope is server-baked).",
                "inputSchema": schemas[t],
            }
            for t in sorted(self.allowed)
        ]


# ── minimal MCP stdio loop (JSON-RPC 2.0, newline-delimited) ──────────────────
def _result(id_, payload):
    return {"jsonrpc": "2.0", "id": id_, "result": payload}


def _error(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle_message(shim: PalaceShim, msg: dict):
    """Return a JSON-RPC response dict, or None for notifications (no reply)."""
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return _result(
            mid,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cortex-palace-shim", "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _result(mid, {"tools": shim.tool_descriptors()})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            out = shim.call(name, args)
            return _result(
                mid,
                {"content": [{"type": "text", "text": json.dumps(out["response"])}], "isError": False},
            )
        except ShimError as e:
            # Surface refusals to the model as a tool error — do NOT crash the shim.
            return _result(
                mid,
                {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True},
            )
    if mid is None:
        return None
    return _error(mid, -32601, f"method not found: {method}")


def run_stdio(shim: PalaceShim, stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_message(shim, msg)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


def shim_from_env() -> PalaceShim:
    return PalaceShim(
        palace_url=os.environ.get("PALACE_MCP_URL", ""),
        palace_id=os.environ.get("PALACE_ID", ""),
        neop_id=os.environ.get("NEOP_ID", ""),
        signing_key_ref=os.environ.get("PALACE_SIGNING_KEY_REF"),
        enable_get_closet=os.environ.get("PALACE_ENABLE_GET_CLOSET", "") in ("1", "true", "yes"),
    )


def main() -> int:
    try:
        shim = shim_from_env()
    except ShimError as e:
        # Fail-closed and loud: never start a shim that could default to _admin.
        sys.stderr.write(f"palace_mcp_shim refusing to start: {e}\n")
        return 2
    run_stdio(shim)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
