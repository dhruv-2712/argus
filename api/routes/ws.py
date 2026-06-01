"""WebSocket live-feed with optional Redis pub/sub for multi-worker fan-out.

Single-worker deployments (Railway default): in-process ConnectionManager
handles everything — no Redis needed.

Multi-worker / Redis deployments: set REDIS_URL env var.  Each worker
publishes broadcasts to the Redis channel; the per-worker subscriber task
relays events from other workers to local WebSocket clients.  A worker-ID
tag prevents double-delivery to the originating worker's own clients.
"""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

_REDIS_URL = os.getenv("REDIS_URL", "").strip()
_REDIS_CHANNEL = "argus:events"
_WORKER_ID = f"w-{os.getpid()}"

try:
    import redis.asyncio as aioredis  # type: ignore
    _HAS_REDIS = bool(_REDIS_URL)
except ImportError:
    _HAS_REDIS = False


class ConnectionManager:
    """Tracks active WebSocket connections and fan-outs events to all."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info("WS connect — %d client(s)", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        logger.info("WS disconnect — %d client(s)", len(self._connections))

    async def broadcast(self, event: dict) -> None:
        async with self._lock:
            targets = list(self._connections)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)


manager = ConnectionManager()


async def _redis_publish(event: dict) -> None:
    """Publish an event to Redis (fire-and-forget, never raises)."""
    try:
        async with aioredis.from_url(_REDIS_URL) as r:
            await r.publish(_REDIS_CHANNEL, json.dumps(event))
    except Exception as exc:
        logger.debug("Redis publish failed: %s", exc)


async def start_redis_subscriber() -> None:
    """Background task: forward events from OTHER workers to local clients.

    Call once at startup when REDIS_URL is configured.
    """
    if not _HAS_REDIS:
        return
    try:
        async with aioredis.from_url(_REDIS_URL) as r:
            async with r.pubsub() as pubsub:
                await pubsub.subscribe(_REDIS_CHANNEL)
                logger.info("Redis subscriber active on channel %s", _REDIS_CHANNEL)
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue
                    try:
                        event = json.loads(msg["data"])
                        # Skip events we published ourselves (already broadcast locally)
                        if event.pop("_wid", None) == _WORKER_ID:
                            continue
                        await manager.broadcast(event)
                    except Exception:
                        pass
    except Exception as exc:
        logger.warning("Redis subscriber error: %s", exc)


async def broadcast(event: dict) -> None:
    """Broadcast an event to all local WS clients.

    Also publishes to Redis (tagged with worker ID) so other workers can
    relay to their own clients.  Never raises — scan pipeline calls this.
    """
    try:
        await manager.broadcast(event)
    except Exception as exc:
        logger.warning("WS in-process broadcast failed: %s", exc)

    if _HAS_REDIS:
        asyncio.create_task(_redis_publish({**event, "_wid": _WORKER_ID}))


@router.websocket("/ws/contacts")
async def contacts_feed(ws: WebSocket) -> None:
    """Live event stream.  Sends a hello, then relays broadcast events."""
    await manager.connect(ws)
    await ws.send_json({"type": "connected", "feed": "argus-live"})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)
