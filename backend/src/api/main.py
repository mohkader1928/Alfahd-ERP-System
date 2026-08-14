"""FastAPI application entrypoint.

Module wiring follows the registration pattern from Phase 9 §2.1: each
enabled module exposes `register(app, event_bus)`; adding a future module
means importing it here and adding one line to ENABLED_MODULES — no existing
module file changes.
"""

import asyncio
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

import src.modules.accounting as accounting_module
import src.modules.attachments as attachments_module
import src.modules.fixed_assets as fixed_assets_module
import src.modules.identity as identity_module
import src.modules.inventory as inventory_module
import src.modules.notifications as notifications_module
import src.modules.payments as payments_module
import src.modules.purchasing as purchasing_module
import src.modules.reporting as reporting_module
import src.modules.sales as sales_module
from src.api.middleware.error_handler import register_error_handlers
from src.shared.config.settings import get_settings
from src.shared.infrastructure.db.seed import seed_catalog_data, sync_admin_role_permissions
from src.shared.infrastructure.db.session import AsyncSessionLocal, engine
from src.shared.infrastructure.messaging.event_bus import event_bus

logger = logging.getLogger("erp.api")

# Owner-reported bug (live, in شركة المحمود): a WEBP customer photo uploaded
# and saved correctly (DB row + file on disk both fine, confirmed while
# debugging) but never displayed — a broken-image icon, with the upload's
# own success toast having already fired, so nothing looked wrong until the
# image quietly failed later. Root cause: StaticFiles serves each file's
# Content-Type via Python's stdlib `mimetypes.guess_type()`, which does not
# reliably have ".webp" registered on every OS/Python build (confirmed here:
# a .webp came back as `application/octet-stream`, while .png/.jpg on the
# same install correctly resolved to their real image/* type) — and most
# browsers refuse to render an <img> whose response Content-Type isn't
# image/*, silently, with no error surfaced anywhere in this app's code.
# Registering it explicitly removes the OS/Python-version dependency
# entirely rather than relying on it being present by chance.
mimetypes.add_type("image/webp", ".webp")

settings = get_settings()

ENABLED_MODULES = [
    identity_module,
    attachments_module,
    notifications_module,
    accounting_module,
    fixed_assets_module,
    inventory_module,
    sales_module,
    purchasing_module,
    payments_module,
    reporting_module,
]


async def _run_admin_role_permission_sync_in_background() -> None:
    """Runs seed.py's Admin-role permission sync out-of-band from startup.

    On the shared dev DB this can take minutes once tens of thousands of
    test-bootstrap companies/roles have accumulated (see
    src/shared/infrastructure/db/seed.py's sync_admin_role_permissions()
    for the full story). Previously this ran inline in lifespan(), so a
    slow run blocked every request until it finished, and an interrupted
    run (container restart, killed query) crashed the whole startup hook
    ("Application startup failed. Exiting."). Backgrounding it means the
    API starts serving requests immediately regardless of how long — or
    how many times — this takes to converge; a failure here is logged and
    retried on the next startup instead of taking the process down.
    """
    try:
        async with AsyncSessionLocal() as session:
            await sync_admin_role_permissions(session)
    except Exception:
        logger.exception("Admin-role permission sync failed; will retry on next startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as session:
        await seed_catalog_data(session)
    # Keep a reference on app.state so the task isn't garbage-collected
    # mid-run (asyncio only holds a weak reference to fire-and-forget tasks).
    app.state.admin_role_sync_task = asyncio.create_task(
        _run_admin_role_permission_sync_in_background()
    )
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
    # Content-Disposition isn't in the browser's default CORS-safelisted
    # response headers, so without this, JS on a cross-origin frontend
    # (e.g. localhost:3000 -> localhost:8000) can never read the real
    # filename off a file-download response (report exports, etc.) —
    # found live while verifying the Standard Reporting Framework.
    expose_headers=["Content-Disposition"],
)

register_error_handlers(app)

for module in ENABLED_MODULES:
    module.register(app, event_bus)

# Entity Media Foundation (UI/UX Evolution milestone): served unauthenticated
# and at an unguessable path (uuid4 filenames — see shared/media/storage.py)
# rather than behind a permission check, deliberately, because the Owner's
# requirement includes embedding these images in print headers/statements,
# which render as plain <img> tags with no way to attach an Authorization
# header. This mirrors how the existing ZATCA QR code is already embedded
# unauthenticated on the invoice page — low-sensitivity, print-facing
# images, not a new class of exposure for this system. Upload/replace/
# delete remain behind the normal authenticated + permission-checked
# endpoints; only the already-saved bytes are served this way.
Path(settings.media_root).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_root), name="media")


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
