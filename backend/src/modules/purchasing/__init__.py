from fastapi import FastAPI

from src.modules.purchasing.api.routes import router as purchasing_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(purchasing_router, prefix="/api/v1/purchasing", tags=["purchasing"])
