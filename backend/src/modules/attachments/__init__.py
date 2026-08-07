from fastapi import FastAPI

from src.modules.attachments.api.routes import router as attachments_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(attachments_router, prefix="/api/v1", tags=["attachments"])
