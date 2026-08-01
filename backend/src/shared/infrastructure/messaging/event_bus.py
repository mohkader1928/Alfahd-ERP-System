"""In-process domain event dispatcher (Phase 8 §1.1 / §7 — Observer pattern).

Cross-module side effects go through here instead of direct calls into
another module's internals, so modules stay extractable into separate
services later (BO-7) without a rewrite — see Phase 8 §10.
"""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

Handler = Callable[[Any], Awaitable[None]]


@dataclass(frozen=True)
class DomainEvent:
    """Base marker for domain events published on the bus."""


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers[type(event)]:
            await handler(event)


event_bus = EventBus()
