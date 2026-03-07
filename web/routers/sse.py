"""SSE (Server-Sent Events) router for real-time progress updates."""

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Optional
from queue import Queue
from threading import Lock

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/sse", tags=["sse"])

# Global event queue for broadcasting messages
_event_queues: list[Queue] = []
_queue_lock = Lock()


def broadcast_event(event_type: str, data: dict):
    """Broadcast an event to all connected SSE clients."""
    event_data = {
        "type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        **data
    }
    with _queue_lock:
        for queue in _event_queues:
            try:
                queue.put_nowait(event_data)
            except:
                pass


def send_progress(operation: str, current: int, total: int, message: str = ""):
    """Send a progress update."""
    broadcast_event("progress", {
        "operation": operation,
        "current": current,
        "total": total,
        "message": message,
        "percent": int((current / total) * 100) if total > 0 else 0,
    })


def send_info(message: str, operation: str = ""):
    """Send an info message."""
    broadcast_event("info", {
        "operation": operation,
        "message": message,
    })


def send_error(message: str, operation: str = ""):
    """Send an error message."""
    broadcast_event("error", {
        "operation": operation,
        "message": message,
    })


def send_success(message: str, operation: str = ""):
    """Send a success message."""
    broadcast_event("success", {
        "operation": operation,
        "message": message,
    })


async def event_generator() -> AsyncGenerator[str, None]:
    """Generate SSE events for a single client."""
    queue = Queue()

    with _queue_lock:
        _event_queues.append(queue)

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
            if queue in _event_queues:
                _event_queues.remove(queue)


@router.get("/events")
async def sse_events():
    """SSE endpoint for real-time events."""
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
