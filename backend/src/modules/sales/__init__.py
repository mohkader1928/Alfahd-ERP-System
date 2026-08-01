from fastapi import FastAPI

from src.modules.sales.api.routes import router as sales_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(sales_router, prefix="/api/v1/sales", tags=["sales"])
