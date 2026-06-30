"""Synapse Application-Service registration — the AS-contract spike (offline lever, no box needed).

`nc-channels` is a Matrix Application Service. Before a homeserver will route a tenant's rooms to it, the
HS must LOAD a registration file (`app_service_config_files`) in the Matrix AS-API spec shape. This module
GENERATES that file from an `ASRegistration` and VALIDATES it against the spec contract — both offline and
tested. The HS actually loading it (and the live transaction round-trip) is box-gated (`service.serve` /
`_cs_api_call`); generating + validating the contract is not.

Secret hygiene: `as_token`/`hs_token` are passed in at generation time and the generated file IS a secret
(mount it / Secrets Manager) — never commit it, never embed the tokens anywhere but their own fields.
"""
from __future__ import annotations

from typing import Any, Dict

from .service import ASRegistration

# Spec-required top-level fields of an AS registration (Matrix AS-API §Registration).
REQUIRED_FIELDS = ("id", "url", "as_token", "hs_token", "sender_localpart", "namespaces")


def registration_dict(
    reg: ASRegistration,
    *,
    id: str | None = None,
    rate_limited: bool = False,
) -> Dict[str, Any]:
    """Build the registration the homeserver loads, from the ASRegistration (which carries `id` + `url` —
    the HS-reachable endpoint where transactions are PUT). The NEop puppet user namespace is EXCLUSIVE so
    the HS reserves it for this AS (M_EXCLUSIVE protects other services from minting `@neop_*` users)."""
    if not reg.url or not reg.url.strip():
        raise ValueError("registration needs reg.url — the HS-reachable URL where transactions are delivered")
    if not reg.as_token or not reg.hs_token:
        raise ValueError("registration needs both as_token (AS→HS) and hs_token (HS→AS)")
    if not reg.user_namespace_regex:
        raise ValueError("registration needs a user_namespace_regex (the NEop puppet space)")
    return {
        "id": id or reg.id or f"neos-nc-channels-{reg.tenant}",
        "url": reg.url.rstrip("/"),
        "as_token": reg.as_token,
        "hs_token": reg.hs_token,
        "sender_localpart": reg.sender_localpart,
        "rate_limited": rate_limited,
        "namespaces": {
            # The AS's own user + the NEop puppets — exclusive so only nc-channels mints them.
            "users": [{"exclusive": True, "regex": reg.user_namespace_regex}],
            "aliases": [],
            "rooms": [],
        },
    }


def validate_registration_dict(d: Dict[str, Any]) -> None:
    """Fail-closed contract check against the AS spec. Raises ValueError on any violation."""
    for k in REQUIRED_FIELDS:
        if k not in d or d[k] in (None, ""):
            raise ValueError(f"registration missing required field: {k!r}")
    users = (d.get("namespaces") or {}).get("users") or []
    if not users:
        raise ValueError("registration must declare a users namespace (the NEop puppet space)")
    for ns in users:
        if not ns.get("regex"):
            raise ValueError("each users-namespace entry needs a non-empty regex")
        if not ns.get("exclusive"):
            raise ValueError("the NEop users namespace MUST be exclusive (M_EXCLUSIVE protection)")
    # Secret hygiene: tokens must live ONLY in their own fields, never embedded in the human-set id/url.
    for leaky in ("id", "url", "sender_localpart"):
        v = str(d.get(leaky, ""))
        if d["as_token"] and d["as_token"] in v:
            raise ValueError(f"as_token must not be embedded in {leaky!r}")
        if d["hs_token"] and d["hs_token"] in v:
            raise ValueError(f"hs_token must not be embedded in {leaky!r}")


def registration_yaml(reg: ASRegistration, **kw: Any) -> str:
    """The validated registration as YAML (what `app_service_config_files` points at). PyYAML is a project
    dependency (`requirements.txt`); a clear error beats a hand-rolled emitter that mis-quotes the regex."""
    import yaml  # PyYAML is a hard dep here; quoting the namespace regex correctly is its job, not ours.

    d = registration_dict(reg, **kw)
    validate_registration_dict(d)
    return yaml.safe_dump(d, sort_keys=False)
