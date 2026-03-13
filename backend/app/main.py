from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.assets import router as assets_router
from app.api.body3d import router as body3d_router
from app.api.faces import router as faces_router
from app.api.files import router as files_router
from app.api.jobs import router as jobs_router
from app.api.object3d import router as object3d_router
from app.api.people import router as people_router
from app.core.config import get_settings
from app.core.database import Base, engine
from app.core.job_recovery import recover_interrupted_jobs
from app.core.migrations import run_startup_migrations
from app.models import asset as asset_models  # noqa: F401
from app.models import body3d as body3d_models  # noqa: F401
from app.models import job as job_models  # noqa: F401
from app.models import object3d as object3d_models  # noqa: F401
from app.models import people as people_models  # noqa: F401
from app.services.library_watcher import LibraryAutoScanWatcher


settings = get_settings()
library_auto_scan_watcher = LibraryAutoScanWatcher()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
        run_startup_migrations()
    recover_interrupted_jobs()
    library_auto_scan_watcher.start()
    yield
    library_auto_scan_watcher.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets_router, prefix=settings.api_prefix)
app.include_router(body3d_router, prefix=settings.api_prefix)
app.include_router(faces_router, prefix=settings.api_prefix)
app.include_router(files_router, prefix=settings.api_prefix)
app.include_router(jobs_router, prefix=settings.api_prefix)
app.include_router(object3d_router, prefix=settings.api_prefix)
app.include_router(people_router, prefix=settings.api_prefix)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
