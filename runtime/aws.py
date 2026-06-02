"""NEOS live AWS tool registry (integration-mode tools).

Read-only boto3-backed tools that sit behind the ToolBroker seam. Lazy and
credential-gated: nothing imports boto3 or opens a session until a tool actually
runs. unit-mode NEop tests never touch this file — they use fixtures/mocks.
Mirrors the model-provider seam: the tool *name* is the contract; mock vs live is
the mode.

Profile/region resolve from the standard AWS environment (AWS_PROFILE /
AWS_REGION / AWS_DEFAULT_REGION) or the default profile. Every tool here is
READ-ONLY by design — no mutations from the runtime without an explicit, reviewed
addition.
"""
from __future__ import annotations
import os

__all__ = ["AwsToolError", "TOOLS", "get_tool", "run"]


class AwsToolError(RuntimeError):
    pass


_session = None


def _sess():
    """Cached boto3 Session from the standard AWS env (lazy import)."""
    global _session
    if _session is None:
        try:
            import boto3
        except ImportError as e:  # pragma: no cover
            raise AwsToolError("boto3 not installed (pip install boto3)") from e
        _session = boto3.Session(
            profile_name=os.environ.get("AWS_PROFILE") or None,
            region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or None,
        )
    return _session


# ----------------------------------------------------------------- read-only tools
def sts_whoami(args=None):
    """Who am I — account / arn / user_id for the resolved credentials."""
    r = _sess().client("sts").get_caller_identity()
    return {"account": r["Account"], "arn": r["Arn"], "user_id": r["UserId"]}


def s3_list_buckets(args=None):
    r = _sess().client("s3").list_buckets()
    return {"buckets": [b["Name"] for b in r.get("Buckets", [])]}


def dynamodb_list_tables(args=None):
    region = (args or {}).get("region")
    client = _sess().client("dynamodb", region_name=region) if region else _sess().client("dynamodb")
    return {"tables": client.list_tables().get("TableNames", [])}


TOOLS = {
    "sts_whoami": sts_whoami,
    "s3_list_buckets": s3_list_buckets,
    "dynamodb_list_tables": dynamodb_list_tables,
}


def get_tool(name):
    if name not in TOOLS:
        raise AwsToolError(f"no AWS tool '{name}' (have {sorted(TOOLS)})")
    return TOOLS[name]


def run(name, args=None):
    """Integration-mode entrypoint the ToolBroker will call for live AWS tools."""
    return get_tool(name)(args or {})
