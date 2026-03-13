from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.body3d import BodyReconstruction
from app.models.people import Face
from app.schemas.body3d import BodyReconstructionPreviewRead, BodyReconstructionPreviewRequest
from app.schemas.assets import BodyReconstructionRead
from app.services.body_reconstruction import BodyReconstructionService


router = APIRouter(prefix="/body3d", tags=["body3d"])
body_service = BodyReconstructionService()


def _get_reconstruction(db: Session, reconstruction_id: int) -> BodyReconstruction:
    reconstruction = (
        db.execute(
            select(BodyReconstruction)
            .where(BodyReconstruction.id == reconstruction_id)
            .options(selectinload(BodyReconstruction.face).selectinload(Face.person))
        )
        .scalars()
        .one_or_none()
    )
    if reconstruction is None:
        raise HTTPException(status_code=404, detail="Body reconstruction not found")
    return reconstruction


def _mesh_urls(reconstruction: BodyReconstruction) -> list[str]:
    output_dir = reconstruction.sam3d_output_dir
    if not output_dir:
        return []
    root = Path(output_dir)
    if not root.exists():
        return []
    return [
        f"/api/body3d/{reconstruction.id}/mesh/{mesh_file.name}"
        for mesh_file in sorted(root.glob("person_*.obj"))
    ]


def _to_read(reconstruction: BodyReconstruction) -> BodyReconstructionRead:
    return BodyReconstructionRead(
        id=reconstruction.id,
        logical_asset_id=reconstruction.logical_asset_id,
        face_id=reconstruction.face_id,
        person_id=reconstruction.face.person_id if reconstruction.face is not None else None,
        person_name=reconstruction.face.person.name
        if reconstruction.face is not None and reconstruction.face.person is not None
        else None,
        job_id=reconstruction.job_id,
        status=reconstruction.status,
        overlay_url=f"/api/body3d/{reconstruction.id}/overlay" if reconstruction.overlay_path else None,
        mask_url=f"/api/body3d/{reconstruction.id}/mask" if reconstruction.mask_path else None,
        bundle_url=f"/api/body3d/{reconstruction.id}/bundle" if reconstruction.bundle_path else None,
        face_preview_url=f"/api/faces/{reconstruction.face_id}/preview" if reconstruction.face_id else None,
        mesh_object_urls=_mesh_urls(reconstruction),
        result_json=reconstruction.result_json,
        error_message=reconstruction.error_message,
        created_at=reconstruction.created_at,
        updated_at=reconstruction.updated_at,
    )


@router.get("/{reconstruction_id}", response_model=BodyReconstructionRead)
def get_body_reconstruction(reconstruction_id: int, db: Session = Depends(get_db)) -> BodyReconstructionRead:
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


@router.get("/{reconstruction_id}/mesh/{mesh_name}")
def get_mesh(reconstruction_id: int, mesh_name: str, db: Session = Depends(get_db)) -> FileResponse:
    reconstruction = _get_reconstruction(db, reconstruction_id)
    if "/" in mesh_name or "\\" in mesh_name or not mesh_name.endswith(".obj"):
        raise HTTPException(status_code=400, detail="Invalid mesh name")
    if not reconstruction.sam3d_output_dir:
        raise HTTPException(status_code=404, detail="Mesh is not available")
    mesh_path = Path(reconstruction.sam3d_output_dir) / mesh_name
    if not mesh_path.exists():
        raise HTTPException(status_code=404, detail="Mesh is not available")
    return FileResponse(str(mesh_path), media_type="application/octet-stream", filename=mesh_path.name)


@router.post("/preview-mask", response_model=BodyReconstructionPreviewRead)
def preview_mask(
    payload: BodyReconstructionPreviewRequest,
    db: Session = Depends(get_db),
) -> BodyReconstructionPreviewRead:
    try:
        preview = body_service.preview_mask(
            db,
            asset_id=payload.asset_id,
            face_id=payload.face_id,
            body_bbox=payload.body_bbox,
            mask_index=payload.mask_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BodyReconstructionPreviewRead(**preview)


@router.get("/previews/{preview_id}/files/{file_name}")
def get_preview_file(preview_id: str, file_name: str) -> FileResponse:
    if "/" in preview_id or "\\" in preview_id or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail="Invalid preview path")
    try:
        preview_root = body_service._preview_root(preview_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    file_path = preview_root / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Preview file not found")
    media_type = "image/png" if file_path.suffix.lower() == ".png" else "application/octet-stream"
    if media_type == "image/png":
        return FileResponse(str(file_path), media_type=media_type)
    return FileResponse(str(file_path), media_type=media_type, filename=file_path.name)
