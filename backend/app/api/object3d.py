from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.object3d import ObjectReconstruction
from app.schemas.object3d import (
    ObjectReconstructionPreviewRead,
    ObjectReconstructionPreviewRequest,
    ObjectReconstructionRead,
)
from app.services.object_reconstruction import ObjectReconstructionService


router = APIRouter(prefix="/object3d", tags=["object3d"])
object_service = ObjectReconstructionService()


def _get_reconstruction(db: Session, reconstruction_id: int) -> ObjectReconstruction:
    reconstruction = db.execute(
        select(ObjectReconstruction).where(ObjectReconstruction.id == reconstruction_id)
    ).scalar_one_or_none()
    if reconstruction is None:
        raise HTTPException(status_code=404, detail="Object reconstruction not found")
    return reconstruction


def _to_read(reconstruction: ObjectReconstruction) -> ObjectReconstructionRead:
    return ObjectReconstructionRead(
        id=reconstruction.id,
        logical_asset_id=reconstruction.logical_asset_id,
        job_id=reconstruction.job_id,
        status=reconstruction.status,
        overlay_url=f"/api/object3d/{reconstruction.id}/overlay" if reconstruction.overlay_path else None,
        mask_url=f"/api/object3d/{reconstruction.id}/mask" if reconstruction.mask_path else None,
        bundle_url=f"/api/object3d/{reconstruction.id}/bundle" if reconstruction.bundle_path else None,
        glb_url=f"/api/object3d/{reconstruction.id}/glb" if reconstruction.glb_path else None,
        glb_download_url=f"/api/object3d/{reconstruction.id}/glb/download" if reconstruction.glb_path else None,
        gaussian_ply_url=f"/api/object3d/{reconstruction.id}/ply" if reconstruction.gaussian_ply_path else None,
        result_json=reconstruction.result_json,
        error_message=reconstruction.error_message,
        created_at=reconstruction.created_at,
        updated_at=reconstruction.updated_at,
    )


@router.get("/{reconstruction_id}", response_model=ObjectReconstructionRead)
def get_object_reconstruction(reconstruction_id: int, db: Session = Depends(get_db)) -> ObjectReconstructionRead:
    return _to_read(_get_reconstruction(db, reconstruction_id))


@router.get("/{reconstruction_id}/overlay")
def get_overlay(reconstruction_id: int, db: Session = Depends(get_db)) -> FileResponse:
    reconstruction = _get_reconstruction(db, reconstruction_id)
    if not reconstruction.overlay_path:
        raise HTTPException(status_code=404, detail="Overlay is not available")
    return FileResponse(reconstruction.overlay_path, media_type="image/png")


@router.get("/{reconstruction_id}/mask")
def get_mask(reconstruction_id: int, db: Session = Depends(get_db)) -> FileResponse:
    reconstruction = _get_reconstruction(db, reconstruction_id)
    if not reconstruction.mask_path:
        raise HTTPException(status_code=404, detail="Mask is not available")
    return FileResponse(reconstruction.mask_path, media_type="image/png")


@router.get("/{reconstruction_id}/bundle")
def get_bundle(reconstruction_id: int, db: Session = Depends(get_db)) -> FileResponse:
    reconstruction = _get_reconstruction(db, reconstruction_id)
    if not reconstruction.bundle_path:
        raise HTTPException(status_code=404, detail="Bundle is not available")
    bundle_path = Path(reconstruction.bundle_path)
    return FileResponse(str(bundle_path), media_type="application/octet-stream", filename=bundle_path.name)


@router.get("/{reconstruction_id}/glb")
def get_glb(reconstruction_id: int, db: Session = Depends(get_db)) -> FileResponse:
    reconstruction = _get_reconstruction(db, reconstruction_id)
    if not reconstruction.glb_path:
        raise HTTPException(status_code=404, detail="GLB is not available")
    return FileResponse(reconstruction.glb_path, media_type="model/gltf-binary")


@router.get("/{reconstruction_id}/glb/download")
def download_glb(reconstruction_id: int, db: Session = Depends(get_db)) -> FileResponse:
    reconstruction = _get_reconstruction(db, reconstruction_id)
    if not reconstruction.glb_path:
        raise HTTPException(status_code=404, detail="GLB is not available")
    glb_path = Path(reconstruction.glb_path)
    return FileResponse(str(glb_path), media_type="application/octet-stream", filename=glb_path.name)


@router.get("/{reconstruction_id}/ply")
def get_ply(reconstruction_id: int, db: Session = Depends(get_db)) -> FileResponse:
    reconstruction = _get_reconstruction(db, reconstruction_id)
    if not reconstruction.gaussian_ply_path:
        raise HTTPException(status_code=404, detail="PLY is not available")
    ply_path = Path(reconstruction.gaussian_ply_path)
    return FileResponse(str(ply_path), media_type="application/octet-stream", filename=ply_path.name)


@router.post("/preview-mask", response_model=ObjectReconstructionPreviewRead)
def preview_mask(
    payload: ObjectReconstructionPreviewRequest,
    db: Session = Depends(get_db),
) -> ObjectReconstructionPreviewRead:
    try:
        preview = object_service.preview_mask(
            db,
            asset_id=payload.asset_id,
            object_bbox=payload.object_bbox,
            mask_index=payload.mask_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ObjectReconstructionPreviewRead(**preview)


@router.get("/previews/{preview_id}/files/{file_name}")
def get_preview_file(preview_id: str, file_name: str) -> FileResponse:
    if "/" in preview_id or "\\" in preview_id or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail="Invalid preview path")
    try:
        preview_root = object_service._preview_root(preview_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    file_path = preview_root / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Preview file not found")
    media_type = "image/png" if file_path.suffix.lower() == ".png" else "application/octet-stream"
    if media_type == "image/png":
        return FileResponse(str(file_path), media_type=media_type)
    return FileResponse(str(file_path), media_type=media_type, filename=file_path.name)
