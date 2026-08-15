from fastapi import FastAPI

from src.modules.company_profile.api.routes import router as company_profile_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(company_profile_router, prefix="/api/v1/company-profile", tags=["company_profile"])
