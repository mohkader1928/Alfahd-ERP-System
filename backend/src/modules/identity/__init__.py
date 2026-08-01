from fastapi import FastAPI

from src.modules.identity.api.routes import router as identity_router
from src.shared.infrastructure.messaging.event_bus import EventBus


def register(app: FastAPI, event_bus: EventBus) -> None:
    """Module registration entry point, per Phase 9 §2.1.

    Adding a future module means writing its own `register()` and adding one
    line in `src/api/main.py` — no existing module file changes.
    """
    app.include_router(identity_router, prefix="/api/v1/identity", tags=["identity"])
