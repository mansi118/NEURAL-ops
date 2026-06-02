"""Loader resolution (S2 §2.4.5): tenant-override -> builtin (agents/) ->
operator-fallback (~/.hermes/agents/). First match wins; a tenant overrides any
builtin NEop without forking. Pure filesystem; no agent-loop import.
"""
from __future__ import annotations
import pathlib


def resolve(neop_id, tenant, *, builtin_root="agents", tenant_root=None, operator_root=None):
    """Return the NEop folder for `neop_id`, honoring override precedence, or None."""
    candidates = []
    if tenant_root:
        candidates.append(pathlib.Path(tenant_root) / tenant / "agents" / neop_id)
    candidates.append(pathlib.Path(builtin_root) / neop_id)
    if operator_root:
        candidates.append(pathlib.Path(operator_root).expanduser() / neop_id)
    for c in candidates:
        if (c / "neop.md").exists():
            return c
    return None
