"""FastAPI application entrypoint.

Module wiring follows the registration pattern from Phase 9 §2.1: each
enabled module exposes `register(app, event_bus)`; adding a future module
means importing it here and adding one line to ENABLED_MODULES — no existing
module file changes.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import src.modules.accounting as accounting_module
import src.modules.identity as identity_module
import src.modules.inventory as inventory_module
import src.modules.purchasing as purchasing_module
import src.modules.reporting as reporting_module
import src.modules.sales as sales_module
from src.api.middleware.error_handler import register_error_handlers
from src.shared.config.settings import get_settings
from src.shared.infrastructure.db.seed import seed_core_data
from src.shared.infrastructure.db.session import AsyncSessionLocal, engine
from src.shared.infrastructure.messaging.event_bus import event_bus

settings = get_settings()

ENABLED_MODULES = [
    identity_module,
    accounting_module,
    inventory_module,
    sales_module,
    purchasing_module,
    reporting_module,
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as session:
        await seed_core_data(session)
    yield


app = FastAPI(
    title="Saudi ERP System — Core Nucleus API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

for module in ENABLED_MODULES:
    module.register(app, event_bus)


@app.get("/health")
async def health() -> dict:
    """NFR-OBS-003 health check: reports DB connectivity."""
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}
