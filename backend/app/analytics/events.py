"""In-process change notifications for dashboards (Server-Sent Events).

Events are published after the database commit that changed a polling unit's
aggregation, so a dashboard never hears about a change that was rolled back. They carry
identifiers only: clients refetch the affected summaries through the normal API.

The broker lives in one API process. With several workers or hosts, each process only
sees its own commits; dashboards also refetch on a timer, and a shared channel such as
Postgres LISTEN/NOTIFY should replace this class at that scale."""

import asyncio
import json
import logging
import threading
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrokerEvent:
    id: int
    payload: dict[str, Any]


@dataclass(eq=False)
class Subscription:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[BrokerEvent] = field(default_factory=lambda: asyncio.Queue(maxsize=500))
    overflowed: bool = False


class TooManySubscribersError(RuntimeError):
    pass


class AnalyticsBroker:
    def __init__(self, history: int = 500, max_subscribers: int = 500) -> None:
        self._lock = threading.Lock()
        self._sequence = 0
        self._history: deque[BrokerEvent] = deque(maxlen=history)
        self._subscribers: set[Subscription] = set()
        self.max_subscribers = max_subscribers

    @property
    def last_id(self) -> int:
        return self._sequence

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, payload: dict[str, Any]) -> BrokerEvent:
        """Safe to call from any thread."""
        with self._lock:
            self._sequence += 1
            event = BrokerEvent(self._sequence, payload)
            self._history.append(event)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(_deliver, subscriber, event)
            except RuntimeError:
                # The subscriber's loop has closed; it will be removed on disconnect.
                pass
        return event

    def since(self, last_id: int) -> list[BrokerEvent]:
        with self._lock:
            return [e for e in self._history if e.id > last_id]

    def subscribe(self) -> Subscription:
        with self._lock:
            if len(self._subscribers) >= self.max_subscribers:
                raise TooManySubscribersError()
            subscription = Subscription(loop=asyncio.get_running_loop())
            self._subscribers.add(subscription)
            return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            self._subscribers.discard(subscription)


def _deliver(subscription: Subscription, event: BrokerEvent) -> None:
    try:
        subscription.queue.put_nowait(event)
    except asyncio.QueueFull:
        subscription.overflowed = True


broker = AnalyticsBroker()


def format_event(event: BrokerEvent, name: str = "aggregation") -> str:
    data = json.dumps(event.payload, separators=(",", ":"), default=str)
    return f"id: {event.id}\nevent: {name}\ndata: {data}\n\n"


async def stream_events(
    source: AnalyticsBroker,
    subscription: Subscription,
    is_disconnected: Callable[[], Awaitable[bool]],
    *,
    election_id: str | None,
    last_event_id: int | None,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    """SSE body. Replays buffered events after Last-Event-ID, then streams live ones.
    If this client fell too far behind, it is told to refetch everything."""

    def wanted(event: BrokerEvent) -> bool:
        return election_id is None or event.payload.get("election_id") == election_id

    try:
        yield f"retry: 5000\nid: {source.last_id}\nevent: ready\ndata: {{}}\n\n"
        if last_event_id is not None:
            for event in source.since(last_event_id):
                if wanted(event):
                    yield format_event(event)
        while not await is_disconnected():
            if subscription.overflowed:
                subscription.overflowed = False
                yield f"id: {source.last_id}\nevent: resync\ndata: {{}}\n\n"
            try:
                event = await asyncio.wait_for(subscription.queue.get(), heartbeat_seconds)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if wanted(event):
                yield format_event(event)
    finally:
        source.unsubscribe(subscription)
