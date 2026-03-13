from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.asset import FileType, PhysicalFile
from app.services.preview import PreviewService


router = APIRouter(prefix="/files", tags=["files"])
preview_service = PreviewService()


def _load_physical_file(file_id: int, db: Session) -> PhysicalFile:
    physical_file = db.execute(select(PhysicalFile).where(PhysicalFile.id == file_id)).scalar_one_or_none()
    if physical_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return physical_file


@router.get("/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db)) -> dict:
    physical_file = _load_physical_file(file_id, db)
    return {
        "id": physical_file.id,
        "file_path": physical_file.file_path,
        "file_type": physical_file.file_type,
        "metadata_json": physical_file.metadata_json,
    }


@router.get("/{file_id}/metadata")
def get_file_metadata(file_id: int, db: Session = Depends(get_db)) -> dict:
    physical_file = _load_physical_file(file_id, db)
    return physical_file.metadata_json or {}


@router.get("/{file_id}/display")
def display_file(file_id: int, db: Session = Depends(get_db)) -> FileResponse:
    physical_file = _load_physical_file(file_id, db)
    source_path = Path(physical_file.file_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="File is missing on disk")

    if physical_file.file_type == FileType.JPG:
        return FileResponse(source_path, media_type="image/jpeg")

    try:
        preview_path = preview_service.get_or_create_preview(physical_file)
        return FileResponse(preview_path, media_type="image/jpeg")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Display image generation failed: {exc}") from exc


@router.get("/{file_id}/preview")
def preview_file(file_id: int, db: Session = Depends(get_db)) -> FileResponse:
    physical_file = _load_physical_file(file_id, db)

    source_path = Path(physical_file.file_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="File is missing on disk")

    try:
        preview_path = preview_service.get_or_create_preview(physical_file)
        return FileResponse(preview_path, media_type="image/jpeg")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {exc}") from exc
