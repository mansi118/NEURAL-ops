"""nc front door — the layer ABOVE dispatch(): gateway, loader, orchestrator.

P5. Adapter -> gateway (normalize/auth/identity/rate-limit) -> orchestrator
(classify/COC-1..5/resolve) -> the EXISTING dispatch() -> streamed response.
Nothing here changes the agent loop or dispatch()'s signature; identity
(tenant, seat) is resolved once at the gateway and threaded through unchanged.
"""
