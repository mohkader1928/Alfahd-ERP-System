from fastapi import FastAPI

from src.modules.inventory.api.routes import router as inventory_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(inventory_router, prefix="/api/v1/inventory", tags=["inventory"])
