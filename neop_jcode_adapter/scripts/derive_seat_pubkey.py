#!/usr/bin/env python3
"""Derive a seat's Ed25519 PUBLIC key (base64) from its signing-key ref — the value you register into the
palace `neop_keys` table for the Gate-D flip (see docs/deployment/execution-plan-track1-3-live-2026-07.md
Step 3b + scripts/seed_neop_keys — Mempalace_NEOS).

The PRIVATE seed never leaves the seat; this only prints the PUBLIC key (safe to hand to the seeder). Reuses
the shim's exact Ed25519Signer so the derived pubkey matches what the seat actually signs X-NEop-Identity with.

Usage (ref forms match PALACE_SIGNING_KEY_REF: "env:NAME" | "file:/path", value = base64 32-byte seed):
    PALACE_SIGNING_KEY_REF=env:ARIA_SIGNING_SEED python3 neop_jcode_adapter/scripts/derive_seat_pubkey.py
    python3 neop_jcode_adapter/scripts/derive_seat_pubkey.py --ref file:/run/secrets/aria_seed
Prints the base64 public key to stdout (nothing else), so it pipes cleanly into the seeder.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from neop_jcode_adapter.palace_mcp_shim import load_signer  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Print a seat's base64 Ed25519 public key from its key ref.")
    p.add_argument("--ref", default=os.environ.get("PALACE_SIGNING_KEY_REF"),
                   help="key ref (env:NAME | file:/path); defaults to $PALACE_SIGNING_KEY_REF")
    args = p.parse_args(argv)
    if not args.ref:
        print("no key ref (set PALACE_SIGNING_KEY_REF or pass --ref env:NAME|file:/path)", file=sys.stderr)
        return 2
    signer = load_signer(args.ref)
    if signer is None:
        print(f"could not resolve a signer from ref {args.ref!r}", file=sys.stderr)
        return 1
    print(signer.public_key_b64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
