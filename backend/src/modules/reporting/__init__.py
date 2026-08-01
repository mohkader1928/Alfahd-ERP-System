from fastapi import FastAPI

from src.modules.reporting.api.routes import router as reporting_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(reporting_router, prefix="/api/v1/reporting", tags=["reporting"])
