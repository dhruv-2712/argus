"""WebSocket live-feed — pushes contact/scan events to connected operators.

A single module-level ``manager`` fans out JSON events to every connected
client. The scan pipeline calls ``broadcast`` when fused contacts land, so
the UI updates the instant a scan resolves instead of waiting for a poll.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])


class ConnectionManager:
    """Tracks active WebSocket connections and broadcasts events to all."""

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
        """Send an event to every connected client; drop any that fail."""
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


async def broadcast(event: dict) -> None:
    """Module-level helper so non-route code can emit events safely."""
    try:
        await manager.broadcast(event)
    except Exception as exc:  # never let telemetry break a scan
        logger.warning("WS broadcast failed: %s", exc)


@router.websocket("/ws/contacts")
async def contacts_feed(ws: WebSocket) -> None:
    """Live event stream. Sends a hello, then relays broadcast events."""
    await manager.connect(ws)
    await ws.send_json({"type": "connected", "feed": "argus-live"})
    try:
        while True:
            # We don't expect inbound messages; this keeps the socket open
            # and detects disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)
