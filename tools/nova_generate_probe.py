#!/usr/bin/env python3
"""Proof A (in-VPC) — does Nova RESOLVE and GENERATE over the sealed spine?

The Python twin of pi-neop-runtime's `nrt probe-model`, so Proof A runs inside the EXISTING VPC-attached
CodeBuild harness (spine-verify) — which bundles NeuralOPS Python, not the Node runtime. Same CLAIM: a real
completion from `bedrock-runtime.<region>/model/<apac profile>/invoke` with the bearer token. stdlib-only
(urllib) so it runs in the harness with no deps.

WHY THIS IS THE REAL PROOF A (not the public check): it is meant to run on a VPC-ATTACHED runner (CodeBuild in
the spine private subnets), where `bedrock-runtime.ap-south-1.amazonaws.com` resolves to the PrivateLink
endpoint. Run from a laptop it would hit the PUBLIC endpoint and prove nothing about the sealed spine — so run
it in-VPC (see infra/build/buildspec-nova-probe.yml). resolves != generates: a non-empty completion is the bar.

Request shape mirrors Mempalace_NEOS/convex/lib/bedrockLlm.ts (Nova: system[] + messages[] + inferenceConfig).
Failures surface as NAMED causes (AUTH/REGION · MODEL-NOT-GRANTED · EGRESS/DNS), never a generic stack trace.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request

REGION = os.environ.get("NRT_BEDROCK_REGION") or os.environ.get("AWS_REGION") or "ap-south-1"
MODEL = os.environ.get("NRT_MODEL") or "apac.amazon.nova-lite-v1:0"  # APAC profile; bare amazon.nova-* rejects on-demand
BEARER = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
SENTINEL = "NOVA-PROBE-OK"


def classify(msg: str, status: int | None) -> str:
    m = msg.lower()
    if status == 403 or "forbidden" in m or "security token" in m or "not authorized" in m and "invoke" not in m:
        return ("AUTH/REGION (403): bearer invalid or region-mismatched — a us-east-1 token 403s in ap-south-1. "
                "Confirm AWS_BEARER_TOKEN_BEDROCK is ap-south-1-scoped and its identity has bedrock:InvokeModel.")
    if "not authorized to invoke" in m or "on-demand throughput" in m or "inference profile" in m or "access to model" in m:
        return ("MODEL-NOT-GRANTED / PROFILE: use the apac.* inference profile (bare amazon.nova-* rejects "
                "on-demand). NB Nova access itself is AUTHORIZED on the account, so this is the profile id / invoke perm.")
    if any(s in m for s in ("getaddrinfo", "name or service", "timed out", "connection refused", "no route", "temporary failure")):
        return ("EGRESS/DNS: could not reach bedrock-runtime.%s.amazonaws.com — are you IN-VPC? The PrivateLink "
                "endpoint (endpoints.tf) resolves only in-VPC; a laptop hits the public endpoint. Check SG/route." % REGION)
    if status is not None and 500 <= status < 600:
        return "BEDROCK-5xx (%d): transient/service-side — retry." % status
    return "UNCLASSIFIED: %s" % msg[:300]


def main() -> int:
    print("== nova_generate_probe (Proof A) → region=%s model=%s ==" % (REGION, MODEL))
    if not BEARER.strip():
        print("FAIL  AWS_BEARER_TOKEN_BEDROCK is blank — fail-closed (no token, no invoke).")
        return 2
    url = "https://bedrock-runtime.%s.amazonaws.com/model/%s/invoke" % (REGION, MODEL)
    body = json.dumps({
        "system": [{"text": "You are a health probe. Reply with EXACTLY this token and nothing else: %s" % SENTINEL}],
        "messages": [{"role": "user", "content": [{"text": "Respond now."}]}],
        "inferenceConfig": {"maxTokens": 16, "temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer %s" % BEARER,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300] if hasattr(e, "read") else str(e)
        print("FAIL  invoke — %s" % classify(detail or str(e), e.code))
        return 1
    except Exception as e:  # URLError (DNS/egress), timeouts, etc.
        print("FAIL  invoke — %s" % classify(str(e), None))
        return 1

    # Nova envelope: output.message.content[].text (mirror bedrockLlm.ts extraction)
    try:
        parts = data["output"]["message"]["content"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        print("FAIL  GENERATED but response shape unexpected (not Nova output.message.content): %s" % json.dumps(data)[:200])
        return 1
    if not text:
        print("FAIL  GENERATED nothing — empty completion (resolves != generates).")
        return 1
    followed = SENTINEL.upper() in text.upper()
    print("  ok   GENERATED %d chars: %r" % (len(text), text[:120]))
    print("PASS  Proof A — Nova RESOLVES and GENERATES in-VPC (%s)." % (
        "and followed the instruction" if followed else "non-empty; did not echo the sentinel — eyeball coherence"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
