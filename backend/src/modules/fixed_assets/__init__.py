from fastapi import FastAPI

from src.modules.fixed_assets.api.routes import router as fixed_assets_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(fixed_assets_router, prefix="/api/v1/fixed-assets", tags=["fixed_assets"])
