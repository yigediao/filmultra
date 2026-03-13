from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.people import Face
from app.schemas.people import FaceAssignmentUpdate, FaceRead
from app.services.faces import FacePipelineService


router = APIRouter(prefix="/faces", tags=["faces"])
face_service = FacePipelineService()


def _face_to_read(face: Face) -> FaceRead:
    return FaceRead(
        id=face.id,
        logical_asset_id=face.logical_asset_id,
        physical_file_id=face.physical_file_id,
        asset_display_name=face.logical_asset.display_name if face.logical_asset is not None else None,
        face_index=face.face_index,
        bbox_x1=face.bbox_x1,
        bbox_y1=face.bbox_y1,
        bbox_x2=face.bbox_x2,
        bbox_y2=face.bbox_y2,
        confidence=face.confidence,
        cluster_id=face.cluster_id,
        person_id=face.person_id,
        person_name=face.person.name if face.person is not None else None,
        preview_url=f"/api/faces/{face.id}/preview" if face.preview_path else None,
        assignment_locked=face.assignment_locked,
        is_excluded=face.is_excluded,
    )


@router.get("/{face_id}", response_model=FaceRead)
def get_face(face_id: int, db: Session = Depends(get_db)) -> FaceRead:
    face = (
        db.execute(
            select(Face)
            .where(Face.id == face_id)
            .options(selectinload(Face.person), selectinload(Face.logical_asset))
        )
        .scalars()
        .one_or_none()
    )
    if face is None:
        raise HTTPException(status_code=404, detail="Face not found")
    return _face_to_read(face)


@router.get("/{face_id}/preview")
def face_preview(face_id: int, db: Session = Depends(get_db)) -> FileResponse:
    face = db.execute(select(Face).where(Face.id == face_id)).scalar_one_or_none()
    if face is None or face.preview_path is None:
        raise HTTPException(status_code=404, detail="Face preview not found")

    preview_path = Path(face.preview_path)
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Face preview file is missing")
    return FileResponse(preview_path, media_type="image/jpeg")


@router.patch("/{face_id}/assignment", response_model=FaceRead)
def update_face_assignment(
    face_id: int,
    payload: FaceAssignmentUpdate,
    db: Session = Depends(get_db),
) -> FaceRead:
    try:
        if payload.action == "assign_person":
            if payload.person_id is None:
                raise HTTPException(status_code=400, detail="person_id is required for assign_person")
            face = face_service.assign_face_to_person(db, face_id=face_id, person_id=payload.person_id)
        elif payload.action == "unassign":
            face = face_service.unassign_face(db, face_id=face_id)
        elif payload.action == "restore_auto":
            face = face_service.restore_face_to_auto(db, face_id=face_id)
        else:
            raise HTTPException(status_code=400, detail="Unsupported face assignment action")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    face = (
        db.execute(
            select(Face)
            .where(Face.id == face.id)
            .options(selectinload(Face.person), selectinload(Face.logical_asset))
        )
        .scalars()
        .one()
    )
    return _face_to_read(face)
