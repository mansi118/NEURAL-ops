"""nc-channels AS service — the wire layer that binds the pure adapter core to a live Synapse.

Split, exactly like the jcode adapter's isolation.py: the POLICY/PLUMBING that can be verified offline
lives here and is tested (transaction dedup, hs_token auth check, the inbound→raw→handle→outbound plan,
the CS-API request descriptors). The two BOX-GATED steps — the actual HTTP server that receives
`PUT /_matrix/app/v1/transactions/{txnId}` and the actual CS-API `PUT .../send/...` — raise until run on
a box with a reachable Synapse (RISK-2/3, infra step 7 in nc-channels-trace.md). DO NOT call a live
homeserver from here without that wiring; the offline parts let the contract be proven first.
"""
from __future__ import annotations

import hmac as _hmac
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from nc_channels import matrix_adapter as ma


@dataclass(frozen=True)
class ASRegistration:
    """The registration the homeserver loads (spec §Registration). One AS per tenant (CA-5).
    Secrets (`as_token`/`hs_token`) live in env/Secrets Manager — passed in, never written to disk here."""
    id: str
    url: str
    tenant: str
    sender_localpart: str                 # @<sender_localpart>:server — the AS's own identity
    user_namespace_regex: str             # e.g. r"@neop_.*:server" (exclusive)
    as_token: str = ""                    # AS → HS (outbound CS calls)
    hs_token: str = ""                    # HS → AS (inbound txn auth) — AS MUST verify
    adapter_hmac_key: str = ""            # CA-4 gateway HMAC key
    server_name: str = "localhost"

    def as_localparts(self) -> List[str]:
        """Localparts the AS owns (for the loop/echo filter) — its sender + the puppet prefix."""
        return [self.sender_localpart]


@dataclass
class OutboundSend:
    """A described CS-API send (built offline; executed box-gated). `as_token` rides in the Bearer header."""
    method: str
    path: str
    query: Dict[str, str]
    body: dict


@dataclass
class TransactionResult:
    processed: List[dict] = field(default_factory=list)   # raws handed to handle()
    skipped: int = 0
    deduped: bool = False


class ASService:
    """Stateful per-tenant AS. Holds the registration + a seen-txn set (at-least-once delivery dedup)."""

    def __init__(self, reg: ASRegistration, *, handle: Callable, classifier,
                 hs_base_url: str = "http://localhost:8008", transport: Optional[Callable] = None):
        if not (reg.tenant and reg.tenant.strip()):
            raise ValueError("AS registration needs a tenant (one AS per tenant, CA-5)")
        if not reg.hs_token:
            raise ValueError("AS registration needs hs_token to authenticate inbound transactions")
        self.reg = reg
        self._handle = handle
        self._classifier = classifier
        self._seen_txns: set = set()
        # The homeserver CS-API base (localhost when nc-channels is co-located on the Synapse box — Bar 1a).
        self.hs_base_url = hs_base_url.rstrip("/")
        # Injectable transport (method,url,data,headers)->(status,dict). None ⇒ real urllib. Lets request
        # CONSTRUCTION be unit-tested without faking the Synapse handshake (that stays box-proven, D1).
        self._transport = transport

    # ---- inbound auth (offline-verifiable) ----
    def verify_hs_token(self, presented: Optional[str]) -> bool:
        """Constant-time check of the homeserver's bearer token against hs_token (spec: reject if absent/wrong)."""
        if not presented:
            return False
        return _hmac.compare_digest(presented, self.reg.hs_token)

    @staticmethod
    def bearer_from_headers(headers: Dict[str, str], query: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Extract the HS token: prefer `Authorization: Bearer <t>` (current spec), fall back to the
        legacy `?access_token=` query param (Synapse historically sent it). Header wins."""
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        if auth.startswith("Bearer "):
            return auth[len("Bearer "):]
        if query:
            return query.get("access_token")
        return None

    # ---- inbound transaction processing (offline-verifiable: dedup + map; handle() is the real seam) ----
    def process_transaction(self, txn_id: str, transaction: dict) -> TransactionResult:
        """Map an AS transaction → raws → handle(). Idempotent on txn_id (at-least-once delivery): a
        repeated txn_id is a no-op returning deduped=True (caller still returns 200 {})."""
        if txn_id in self._seen_txns:
            return TransactionResult(deduped=True)
        res = TransactionResult()
        for event in transaction.get("events", []):
            if not ma.is_routable_message(event, as_localparts=self.reg.as_localparts()):
                res.skipped += 1
                continue
            raw = ma.matrix_message_to_raw(
                event, tenant=self.reg.tenant, token=self.reg.as_token,
                hmac_key=self.reg.adapter_hmac_key)
            res.processed.append(raw)
        self._seen_txns.add(txn_id)
        return res

    def reply_send(self, room_id: str, result: dict, txn_id: str, *, puppet_localpart: Optional[str] = None) -> OutboundSend:
        """Build the CS-API send for a handle() result (send-on-complete; RISK-1). Optionally puppet a
        namespaced NEop user — only if its mxid is covered by the AS users namespace (else HS M_EXCLUSIVE)."""
        body = ma.outbound_message(ma.stream_to_text(result))
        query: Dict[str, str] = {}
        if puppet_localpart:
            mxid = f"@{puppet_localpart}:{self.reg.server_name}"
            if not _matches_namespace(mxid, self.reg.user_namespace_regex):
                raise ValueError(f"puppet {mxid} outside AS users namespace — HS would reject (M_EXCLUSIVE)")
            query["user_id"] = mxid
        return OutboundSend(
            method="PUT",
            path=f"/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
            query=query, body=body)

    # ---- the live wire (IMPLEMENTED; correctness PROVEN AT THE BOX against real Synapse, never a mock) ----
    def serve(self, host: str, port: int, *, reflect: bool = True):
        """Start the AS HTTP server: PUT /_matrix/app/v1/transactions/{txnId}.

        reflect=True  → **Bar 1a**: a hardcoded echo, NO runtime. core.py raises on live (see
                        docs/deployment/bar1-open-questions.md), so this proves the TRANSPORT round-trip
                        (Element → Synapse → nc-channels → Synapse → Element) without a live NEop.
        reflect=False → the full handle→dispatch path (**Bar 1b/2**) — needs a live Hermes runtime (M1b);
                        on the current Python runtime this raises and the message is logged, not answered.

        Run at the box; the CS-API handshake is proven against real Synapse, never a mock (D1)."""
        import sys
        import uuid
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import urlparse, parse_qs
        svc = self

        class _Handler(BaseHTTPRequestHandler):
            def _reply(self, code, obj):
                data = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_PUT(self):
                pr = urlparse(self.path)
                parts = pr.path.rstrip("/").split("/")
                if len(parts) < 2 or parts[-2] != "transactions":   # /_matrix/app/v1/transactions/{txnId}
                    return self._reply(404, {"errcode": "M_UNRECOGNIZED"})
                txn_id = parts[-1]
                q = {k: v[0] for k, v in parse_qs(pr.query).items()}
                token = svc.bearer_from_headers(dict(self.headers.items()), q)
                if not svc.verify_hs_token(token):
                    return self._reply(403, {"errcode": "M_FORBIDDEN"})
                try:
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(length) or b"{}")
                except Exception:
                    return self._reply(400, {"errcode": "M_NOT_JSON"})
                res = svc.process_transaction(txn_id, body)
                if res.deduped:
                    return self._reply(200, {})            # at-least-once: repeated txn is a no-op
                for raw in res.processed:
                    try:
                        if reflect:
                            result = {"stream": ["echo ⟳ " + (raw.get("text") or "")]}
                        else:
                            result = svc._handle(raw, svc._classifier, mode="live")   # Bar 1b/2 (needs M1b)
                        send = svc.reply_send(raw.get("conversation_id"), result, "ncq-" + uuid.uuid4().hex)
                        svc._cs_api_call(send)
                    except Exception as e:                 # one bad message must not drop the whole txn
                        sys.stderr.write(f"nc-channels: reply failed for {raw.get('msg_id')}: {e}\n")
                return self._reply(200, {})

            def log_message(self, *a):
                pass

        httpd = ThreadingHTTPServer((host, port), _Handler)
        sys.stderr.write(f"nc-channels serving on {host}:{port} (reflect={reflect}) → HS {svc.hs_base_url}\n")
        httpd.serve_forever()

    def _cs_api_call(self, send: OutboundSend):
        """Execute the CS-API descriptor: PUT {hs_base_url}{path}?{query}, `Authorization: Bearer <as_token>`.
        Request construction is unit-tested via the injectable transport; the live handshake is box-proven."""
        import urllib.parse
        import urllib.request
        url = self.hs_base_url + send.path
        if send.query:
            url += "?" + urllib.parse.urlencode(send.query)
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {self.reg.as_token}"}
        data = json.dumps(send.body).encode("utf-8")
        if self._transport is not None:
            return self._transport(send.method, url, data, headers)
        req = urllib.request.Request(url, data=data, headers=headers, method=send.method)
        with urllib.request.urlopen(req, timeout=15) as r:     # pragma: no cover  (box-proven, not unit)
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw.strip() else {})


def _matches_namespace(mxid: str, regex: str) -> bool:
    import re
    return re.fullmatch(regex, mxid) is not None
