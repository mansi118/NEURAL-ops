#!/usr/bin/env python3
"""Bar 1a box runner — start the nc-channels AS transport (hardcoded reflect) OR emit its registration.

ONE process reads ONE env file so the as_token/hs_token pair is minted once and used in BOTH places
(the Synapse registration YAML and the serving bridge) — a mismatch is the "403 for no obvious reason"
failure, so we make it structurally impossible: same env → same tokens.

Two modes (env-driven, no flags to memorize):
  python3 tools/run_nc_channels_bar1a.py --emit-registration   # → registration YAML on stdout (needs PyYAML)
  python3 tools/run_nc_channels_bar1a.py                        # → serve() reflect=True (stdlib only)

serve() is stdlib-only (http.server + urllib); PyYAML is needed ONLY for --emit-registration.
This is Bar 1a: reflect=True hardcodes `echo ⟳ <text>` — NO runtime, NO palace (core.py raises on live;
see docs/deployment/bar1-open-questions.md). It proves the Element↔Synapse↔nc-channels TRANSPORT only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nc_channels.service import ASRegistration, ASService


def _req(name: str) -> str:
    v = os.environ.get(name, "")
    if not v.strip():
        sys.stderr.write(f"FATAL: env {name} is required and blank — refusing to start (fail-closed)\n")
        raise SystemExit(2)
    return v


def _registration() -> ASRegistration:
    return ASRegistration(
        id=os.environ.get("AS_ID", "neos-nc-channels-neuraledge"),
        url=_req("AS_URL"),                       # HS-reachable endpoint (localhost:8010 for co-located Bar 1a)
        tenant=os.environ.get("AS_TENANT", "neuraledge"),
        sender_localpart=os.environ.get("AS_SENDER", "neos-bot"),
        user_namespace_regex=_req("AS_USER_REGEX"),   # @neop_.*:neuraledge\.in  (delegated server_name, #85)
        as_token=_req("AS_TOKEN"),                # AS → HS  (bridge authenticates TO Synapse)
        hs_token=_req("HS_TOKEN"),                # HS → AS  (Synapse authenticates TO the bridge)
        adapter_hmac_key=os.environ.get("AS_HMAC_KEY", "bar1a-reflect-unused"),  # unused by reflect
        server_name=os.environ.get("AS_SERVER_NAME", "neuraledge.in"),
    )


def main() -> None:
    reg = _registration()

    if "--emit-registration" in sys.argv:
        from nc_channels.registration import registration_yaml
        sys.stdout.write(registration_yaml(reg))
        return

    # reflect=True never calls handle(); pass a fail-closed stub so Bar 1b can't sneak in silently.
    def _no_runtime(*_a, **_k):
        raise NotImplementedError("Bar 1a is reflect-only; live runtime (Hermes/M1b) is not wired here")

    svc = ASService(
        reg, handle=_no_runtime, classifier=None,
        hs_base_url=os.environ.get("HS_BASE_URL", "http://localhost:8008"))
    host = os.environ.get("LISTEN_HOST", "127.0.0.1")   # bind loopback: co-located, Synapse reaches localhost
    port = int(os.environ.get("LISTEN_PORT", "8010"))
    svc.serve(host, port, reflect=True)


if __name__ == "__main__":
    main()
