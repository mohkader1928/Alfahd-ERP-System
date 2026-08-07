from fastapi import FastAPI

from src.modules.notifications.api.routes import router as notifications_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(notifications_router, prefix="/api/v1", tags=["notifications"])
