"""events.py — In-memory ring buffer + SSE pub/sub for the daemon.

Events get a monotonic id, are stored in a bounded deque, and fan out to
subscriber queues. SSE writers replay from `since=<id>` then tail live events.
On overflow (cursor older than the oldest retained id) a `gap` event is
emitted so the client knows to resync.

This is the spike implementation. Foundation PR will swap the in-mem buffer
for the SQLite `daemon_events` table; the publish/subscribe surface stays
the same.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from typing import Any, Iterable, Optional

# Cap chosen low for the spike — exercises overflow path in tests.
RING_CAP = 1000
HEARTBEAT_INTERVAL_S = 15.0


class EventBus:
    def __init__(self, ring_cap: int = RING_CAP) -> None:
        self._ring: deque[dict] = deque(maxlen=ring_cap)
        self._next_id = 1
        self._oldest_id = 1  # tracks lowest id still in the ring
        self._subscribers: set[queue.Queue] = set()
        self._lock = threading.Lock()

    def publish(
        self,
        ev_type: str,
        data: dict,
        *,
        originator: Optional[dict] = None,
    ) -> int:
        with self._lock:
            ev_id = self._next_id
            self._next_id += 1
            evt = {
                "id": ev_id,
                "ts": time.time(),
                "type": ev_type,
                "data": data,
            }
            if originator is not None:
                evt["originator"] = originator
            # If full, the deque drops the head; bump _oldest_id accordingly.
            if len(self._ring) == self._ring.maxlen:
                self._oldest_id = self._ring[0]["id"] + 1
            self._ring.append(evt)
            for q in list(self._subscribers):
                try:
                    q.put_nowait(evt)
                except queue.Full:
                    pass
            return ev_id

    def replay_since(self, since: int) -> Iterable[dict]:
        """Yield events with id > since. If since is older than the oldest
        retained event, yield a synthetic `gap` first."""
        with self._lock:
            oldest = self._oldest_id
            snapshot = list(self._ring)
        if since > 0 and since < oldest - 1:
            yield {
                "id": oldest - 1,
                "ts": time.time(),
                "type": "gap",
                "data": {
                    "missed_from": since + 1,
                    "missed_to": oldest - 1,
                    "reason": "ring_overflow",
                },
            }
        for evt in snapshot:
            if evt["id"] > since:
                yield evt

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=4096)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


_BUS: Optional[EventBus] = None
_BUS_LOCK = threading.Lock()


def get_bus() -> EventBus:
    global _BUS
    with _BUS_LOCK:
        if _BUS is None:
            _BUS = EventBus()
        return _BUS


def reset_bus_for_tests() -> None:
    """Drop and recreate the global bus. Tests only."""
    global _BUS
    with _BUS_LOCK:
        _BUS = EventBus()


def format_sse(evt: dict) -> bytes:
    """Render an event as one SSE message frame."""
    return (
        f"id: {evt['id']}\n"
        f"event: {evt['type']}\n"
        f"data: {json.dumps(evt, separators=(',', ':'))}\n\n"
    ).encode("utf-8")


def heartbeat_frame() -> bytes:
    return b":\n\n"
