"""ACP — Agent Communication Protocol (Flow 7). NEop-to-NEop composition.

A seam BESIDE the runtime, like frontdoor/: the router verifies signed Ed25519
envelopes (ACP-1..4) and routes to the existing dispatch(). core.py / dispatch() /
the plan->execute->verify loop are untouched. Single-tenant; cross-tenant is V2.
"""
