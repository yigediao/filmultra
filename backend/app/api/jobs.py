from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.job import Job
from app.schemas.jobs import FaceDetectRequest, JobRead, ReclusterRequest, Sam3dBodyRequest, Sam3dObjectRequest, ScanRequest
from app.services.body_reconstruction import BodyReconstructionService
from app.services.faces import FacePipelineService
from app.services.object_reconstruction import ObjectReconstructionService
from app.services.scanner import AssetScannerService


router = APIRouter(prefix="/jobs", tags=["jobs"])
scanner_service = AssetScannerService()
face_service = FacePipelineService()
body_service = BodyReconstructionService()
object_service = ObjectReconstructionService()


@router.get("", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_db)) -> list[Job]:
    return db.execute(select(Job).order_by(desc(Job.created_at))).scalars().all()


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/scan", response_model=JobRead)
def run_scan(
    payload: ScanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Job:
    settings = get_settings()
    root_path = payload.root_path or settings.photo_library_root
    try:
        job = scanner_service.create_scan_job(db, root_path=root_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(scanner_service.run_scan_job, job.id)
    return job


@router.post("/face-detect", response_model=JobRead)
def run_face_detect(
    payload: FaceDetectRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Job:
    job = face_service.create_face_detect_job(db, asset_ids=payload.asset_ids)
    background_tasks.add_task(face_service.run_face_detect_job, job.id)
    return job


@router.post("/recluster", response_model=JobRead)
def run_recluster(
    payload: ReclusterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Job:
    job = face_service.create_recluster_job(db, similarity_threshold=payload.similarity_threshold)
    background_tasks.add_task(face_service.run_recluster_job, job.id)
    return job


@router.post("/sam3d-body", response_model=JobRead)
def run_sam3d_body(
    payload: Sam3dBodyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Job:
    try:
        job = body_service.create_body_job_with_options(
            db,
            asset_id=payload.asset_id,
            face_id=payload.face_id,
            body_bbox=payload.body_bbox,
            mask_index=payload.mask_index,
            preview_id=payload.preview_id,
            mask_edits=[item.model_dump() for item in payload.mask_edits] if payload.mask_edits else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(body_service.run_body_job, job.id)
    return job


@router.post("/sam3d-object", response_model=JobRead)
def run_sam3d_object(
    payload: Sam3dObjectRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Job:
    try:
        job = object_service.create_object_job_with_options(
            db,
            asset_id=payload.asset_id,
            object_bbox=payload.object_bbox,
            mask_index=payload.mask_index,
            preview_id=payload.preview_id,
            mask_edits=[item.model_dump() for item in payload.mask_edits] if payload.mask_edits else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(object_service.run_object_job, job.id)
    return job
