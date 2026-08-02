from fastapi import FastAPI

from src.modules.payments.api.routes import router as payments_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(payments_router, prefix="/api/v1/payments", tags=["payments"])
