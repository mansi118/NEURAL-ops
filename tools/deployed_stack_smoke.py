#!/usr/bin/env python3
"""Deployed-stack smoke — the SAME spine proofs that pass on the self-host, parameterized to run against
ANY deployment (AWS, self-host, or cloud). Phase C step 6 of docs/deploy/aws-deployment-plan.md:
"the spine behaves on AWS exactly as on self-host" — if this is green against the deployed endpoints,
the deployment is real.

TARGET — all from env (no self-host assumptions baked):
  NEOS_SMOKE_API_URL    Convex API base (admin queries via `npx convex run`)   e.g. http://convex.neos-dogfood.local:3210
  NEOS_SMOKE_SITE_URL   Convex .convex.site (the broker's /mcp endpoint)         e.g. http://convex.neos-dogfood.local:3211
  NEOS_SMOKE_ADMIN_KEY  admin/operator key for the verification queries
  NEOS_SMOKE_CLIENT     tenant clientId (default "neuraledge")
Run:  NEOS_SMOKE_API_URL=… NEOS_SMOKE_SITE_URL=… NEOS_SMOKE_ADMIN_KEY=… python3 tools/deployed_stack_smoke.py
Exit 0 ⇔ every check passed.

Checks (the live spine): tenant→palaceId · broker write/retrieve · broker denial (denied_at_layer=broker)
· paused_runs round-trip (Decision Queue) · denialsByLayer (the audit instrument) · twin per-user keying.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys

API = os.environ.get("NEOS_SMOKE_API_URL") or ""
SITE = os.environ.get("NEOS_SMOKE_SITE_URL") or ""
ADMIN = os.environ.get("NEOS_SMOKE_ADMIN_KEY") or ""
CLIENT = os.environ.get("NEOS_SMOKE_CLIENT", "neuraledge")
MEMPALACE = os.environ.get("MEMPALACE_DIR", "/mnt/c/Users/LENOVO/Downloads/Mempalace_NEOS")

if not (API and SITE and ADMIN):
    sys.exit("set NEOS_SMOKE_API_URL, NEOS_SMOKE_SITE_URL, NEOS_SMOKE_ADMIN_KEY to the deployment")

os.environ["CONVEX_SITE_URL"] = SITE  # the broker (runtime.memory) reads this for /mcp
sys.path.insert(0, os.environ.get("NEURALOPS_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from runtime import memory as broker  # noqa: E402

_CRUN_ENV = {**os.environ, "CONVEX_SELF_HOSTED_URL": API, "CONVEX_SELF_HOSTED_ADMIN_KEY": ADMIN}
PASS, FAIL = [], []


def crun(ref, args):
    out = subprocess.run(["npx", "convex", "run", ref, json.dumps(args)],
                         cwd=MEMPALACE, env=_CRUN_ENV, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200])
    return json.loads(out.stdout) if out.stdout.strip() else None


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  · ' + detail if detail else ''}")


def main():
    print(f"== deployed-stack smoke → API={API} SITE={SITE} client={CLIENT} ==")
    pid = None
    try:
        pal = crun("palace/queries:getPalaceByClient", {"clientId": CLIENT})
        pid = pal.get("_id") if isinstance(pal, dict) else None
        check("tenant → palaceId", bool(pid), f"palaceId={pid}")
    except Exception as e:
        check("tenant → palaceId", False, str(e))
    if not pid:
        return _summary()

    try:
        w = broker.write(pid, "aria", {"content": "smoke: deployed-stack check.", "title": "smoke"})
        check("broker.write (palace_remember)", w.get("status") in ("ok", "partial", "quarantined", "noop"))
    except Exception as e:
        check("broker.write (palace_remember)", False, str(e))
    try:
        r = broker.retrieve(pid, "aria", "deployed stack check", k=3)
        check("broker.retrieve (graceful)", isinstance(r, dict) and "chunks" in r)
    except Exception as e:
        check("broker.retrieve (graceful)", False, str(e))

    try:
        broker.write(pid, "   ", {"content": "x"}); check("broker denial (blank seat)", False)
    except broker.MemPalaceError as e:
        check("broker denial (denied_at_layer=broker)", "denied_at_layer=broker" in str(e))

    try:
        crun("palace/pausedRuns:putPausedRun", {"palaceId": pid, "neopId": "smoke", "runId": "smoke-1",
                                                "state": {"seat": "smoke"}})
        pend = crun("palace/pausedRuns:pendingPausedRuns", {"palaceId": pid})
        listed = any(p.get("runId") == "smoke-1" for p in (pend or {}).get("pending", []))
        crun("palace/pausedRuns:markPausedRun", {"palaceId": pid, "runId": "smoke-1", "status": "resolved"})
        pend2 = crun("palace/pausedRuns:pendingPausedRuns", {"palaceId": pid})
        gone = all(p.get("runId") != "smoke-1" for p in (pend2 or {}).get("pending", []))
        check("paused_runs round-trip (Decision Queue)", listed and gone)
    except Exception as e:
        check("paused_runs round-trip (Decision Queue)", False, str(e))

    try:
        d = crun("access/queries:denialsByLayer", {"palaceId": pid})
        check("denialsByLayer (audit instrument live)", isinstance(d, dict) and "byLayer" in d,
              json.dumps(d.get("byLayer")) if isinstance(d, dict) else "")
    except Exception as e:
        check("denialsByLayer (audit instrument live)", False, str(e))

    try:  # twin keyed by the USER (requester) — broker get/put under the per-user identity
        broker.put_twin(pid, "user-smoke", {"twin_id": f"{pid}:user-smoke", "maturity": "seed",
                                            "version": 1, "identity": "U", "communication": "c", "decision_style": "d"})
        t = broker.get_twin(pid, "user-smoke")
        check("twin per-user keying", isinstance(t, dict) and t.get("identity") == "U")
    except Exception as e:
        check("twin per-user keying", False, str(e))
    return _summary()


def _summary():
    print(f"== {len(PASS)} passed, {len(FAIL)} failed ==")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
