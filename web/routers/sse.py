"""SSE (Server-Sent Events) router for real-time progress updates."""

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Optional
from queue import Queue
from threading import Lock

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from web.auth import get_current_user
from web.database.models import User

router = APIRouter(prefix="/api/sse", tags=["sse"])

# Global event queues per user for broadcasting messages
_event_queues: dict[int, list[Queue]] = {}
_queue_lock = Lock()


def broadcast_event(user_id: int, event_type: str, data: dict):
    """Broadcast an event to all connected SSE clients for one user."""
    event_data = {
        "type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        **data
    }
    with _queue_lock:
        for queue in _event_queues.get(user_id, []):
            try:
                queue.put_nowait(event_data)
            except:
                pass


def send_progress(user_id: int, operation: str, current: int, total: int, message: str = ""):
    """Send a progress update."""
    broadcast_event(user_id, "progress", {
        "operation": operation,
        "current": current,
        "total": total,
        "message": message,
        "percent": int((current / total) * 100) if total > 0 else 0,
    })


def send_info(user_id: int, message: str, operation: str = ""):
    """Send an info message."""
    broadcast_event(user_id, "info", {
        "operation": operation,
        "message": message,
    })


def send_error(user_id: int, message: str, operation: str = ""):
    """Send an error message."""
    broadcast_event(user_id, "error", {
        "operation": operation,
        "message": message,
    })


def send_success(user_id: int, message: str, operation: str = ""):
    """Send a success message."""
    broadcast_event(user_id, "success", {
        "operation": operation,
        "message": message,
    })


async def event_generator(user_id: int) -> AsyncGenerator[str, None]:
    """Generate SSE events for a single client."""
    queue = Queue()

    with _queue_lock:
        _event_queues.setdefault(user_id, []).append(queue)

    try:
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        while True:
            try:
                # Check for events every 100ms
                await asyncio.sleep(0.1)

                while not queue.empty():
                    event = queue.get_nowait()
                    yield f"data: {json.dumps(event)}\n\n"

            except asyncio.CancelledError:
                break
    finally:
        with _queue_lock:
            queues = _event_queues.get(user_id, [])
            if queue in queues:
                queues.remove(queue)
            if not queues and user_id in _event_queues:
                del _event_queues[user_id]


@router.get("/events")
async def sse_events(user: User = Depends(get_current_user)):
    """SSE endpoint for real-time events."""
    return StreamingResponse(
        event_generator(user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
