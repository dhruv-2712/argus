"""Lightweight in-memory rate limiting + scan concurrency control.

Single-worker friendly (Render free tier). For multi-worker deployments a
shared store (Redis) would be needed, but per-worker limiting is sufficient
to stop a single client from swamping the instance or burning LLM quota.
"""

import asyncio
import time

from fastapi import HTTPException, Request

# Per-IP timestamp of last accepted request, keyed by "scope:ip".
_last_call: dict[str, float] = {}

# Hard cap on concurrent scans across the whole worker. Scans are expensive
# (5 external APIs + SPECTER + LLM); more than a couple at once will thrash
# the free instance.
SCAN_SEMAPHORE = asyncio.Semaphore(2)


def _client_ip(request: Request) -> str:
    """Best-effort client IP, honoring Render/Cloudflare proxy headers."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, min_interval: float):
    """FastAPI dependency: reject a client that calls faster than min_interval."""
    async def _dep(request: Request) -> None:
        ip = _client_ip(request)
        key = f"{scope}:{ip}"
        now = time.time()
        last = _last_call.get(key, 0.0)
        wait = min_interval - (now - last)
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit — wait {int(wait) + 1}s before trying again.",
            )
        _last_call[key] = now
        # Opportunistic cleanup so the dict can't grow without bound.
        if len(_last_call) > 5000:
            cutoff = now - 3600
            for k, t in list(_last_call.items()):
                if t < cutoff:
                    _last_call.pop(k, None)

    return _dep
