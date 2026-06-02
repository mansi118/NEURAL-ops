"""Capability registry — {capability_name: neop_id} from frontmatter `acp.publishes`.

The doc names a separate capabilities.json; we fold the capability list into the
existing `acp.publishes` frontmatter for now (one source of truth, less surface).
First publisher wins.
"""
from __future__ import annotations
import pathlib
import yaml


def build_registry(agents_root="agents"):
    reg = {}
    for neop_md in sorted(pathlib.Path(agents_root).glob("*/neop.md")):
        txt = neop_md.read_text()
        if not txt.startswith("---"):
            continue
        fm = yaml.safe_load(txt.split("---", 2)[1]) or {}
        nid = fm.get("neop_id")
        for cap in ((fm.get("acp") or {}).get("publishes") or []):
            reg.setdefault(cap, nid)
    return reg
