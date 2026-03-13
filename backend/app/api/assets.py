from __future__ import annotations

import tempfile
import zipfile
from datetime import datetime
from os import path as os_path
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import Select, desc, func, select
from sqlalchemy.orm import Session, selectinload
from starlette.background import BackgroundTask

from app.core.database import get_db
from app.models.asset import FileType, LogicalAsset, PhysicalFile
from app.models.body3d import BodyReconstruction
from app.models.job import Job, JobStatus, JobType
from app.models.object3d import ObjectReconstruction
from app.models.people import Face, LogicalAssetPerson
from app.schemas.assets import (
    AssetDownloadRequest,
    BodyReconstructionRead,
    LibraryStateRead,
    LogicalAssetDetail,
    LogicalAssetListItem,
    RatingUpdate,
)
from app.schemas.object3d import ObjectReconstructionRead
from app.schemas.people import AssetPersonRead, FaceRead
from app.services.metadata import MetadataSyncService


router = APIRouter(prefix="/assets", tags=["assets"])
metadata_service = MetadataSyncService()


def _parse_ratings_filter(raw_value: str | None) -> list[int]:
    if raw_value is None:
        return []

    parsed: list[int] = []
    for item in raw_value.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        value = int(candidate)
        if value < 0 or value > 5:
            raise ValueError("ratings must contain integers between 0 and 5")
        if value not in parsed:
            parsed.append(value)
    return parsed


def _select_download_file(asset: LogicalAsset, variant: str) -> PhysicalFile | None:
    target_type = FileType.JPG if variant == "JPG" else FileType.RAW
    matching_files = [file for file in asset.physical_files if file.file_type == target_type]
    if not matching_files:
        return None
    return sorted(matching_files, key=lambda item: (not item.is_hero, item.file_path.lower()))[0]


def _cleanup_temp_file(path: str) -> None:
    file_path = Path(path)
    if file_path.exists():
        file_path.unlink()


def _build_archive_name(physical_file: PhysicalFile, common_root: Path | None, used_names: set[str]) -> str:
    source_path = Path(physical_file.file_path)
    if common_root is not None:
        try:
            archive_path = source_path.relative_to(common_root)
        except ValueError:
            archive_path = Path(source_path.name)
    else:
        archive_path = Path(source_path.name)

    archive_name = archive_path.as_posix()
    if archive_name not in used_names:
        used_names.add(archive_name)
        return archive_name

    suffix = 2
    while True:
        candidate = archive_path.with_name(f"{archive_path.stem}__{suffix}{archive_path.suffix}").as_posix()
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        suffix += 1


def _download_media_type(physical_file: PhysicalFile) -> str:
    if physical_file.file_type == FileType.JPG:
        return "image/jpeg"
    if physical_file.file_type == FileType.RAW:
        return "application/octet-stream"
    return "application/octet-stream"


def _asset_to_list_item(asset: LogicalAsset) -> LogicalAssetListItem:
    hero_preview_url = None
    if asset.hero_file_id is not None:
        hero_preview_url = f"/api/files/{asset.hero_file_id}/preview"

    return LogicalAssetListItem(
        id=asset.id,
        capture_key=asset.capture_key,
        display_name=asset.display_name,
        rating=asset.rating,
        capture_time=asset.capture_time,
        camera_model=asset.camera_model,
        lens_model=asset.lens_model,
        width=asset.width,
        height=asset.height,
        file_count=len(asset.physical_files),
        hero_file_id=asset.hero_file_id,
        hero_preview_url=hero_preview_url,
        people_count=len(asset.people_links),
    )


def _asset_to_detail(
    asset: LogicalAsset,
    *,
    previous_asset_id: int | None = None,
    next_asset_id: int | None = None,
) -> LogicalAssetDetail:
    hero_file = next((file for file in asset.physical_files if file.id == asset.hero_file_id), None)
    return LogicalAssetDetail(
        id=asset.id,
        capture_key=asset.capture_key,
        display_name=asset.display_name,
        rating=asset.rating,
        pick_flag=asset.pick_flag,
        reject_flag=asset.reject_flag,
        color_label=asset.color_label,
        capture_time=asset.capture_time,
        camera_model=asset.camera_model,
        lens_model=asset.lens_model,
        width=asset.width,
        height=asset.height,
        hero_file_id=asset.hero_file_id,
        hero_preview_url=f"/api/files/{asset.hero_file_id}/preview" if asset.hero_file_id else None,
        hero_display_url=f"/api/files/{asset.hero_file_id}/display" if asset.hero_file_id else None,
        hero_metadata=hero_file.metadata_json if hero_file is not None else None,
        previous_asset_id=previous_asset_id,
        next_asset_id=next_asset_id,
        physical_files=asset.physical_files,
        people=[
            AssetPersonRead(
                id=link.person.id,
                name=link.person.name,
                face_count=link.face_count,
                cover_preview_url=f"/api/faces/{link.person.cover_face_id}/preview"
                if link.person.cover_face_id
                else None,
            )
            for link in asset.people_links
            if link.person is not None
        ],
        faces=[
            FaceRead(
                id=face.id,
                logical_asset_id=face.logical_asset_id,
                physical_file_id=face.physical_file_id,
                asset_display_name=asset.display_name,
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
            for face in sorted(
                [item for item in asset.faces if not item.is_excluded],
                key=lambda item: (item.person_id is None, -item.confidence, item.id),
            )
        ],
        body_reconstructions=[
            BodyReconstructionRead(
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
                mesh_object_urls=[
                    f"/api/body3d/{reconstruction.id}/mesh/{mesh_file.name}"
                    for mesh_file in sorted(Path(reconstruction.sam3d_output_dir).glob("person_*.obj"))
                ]
                if reconstruction.sam3d_output_dir and Path(reconstruction.sam3d_output_dir).exists()
                else [],
                result_json=reconstruction.result_json,
                error_message=reconstruction.error_message,
                created_at=reconstruction.created_at,
                updated_at=reconstruction.updated_at,
            )
            for reconstruction in sorted(asset.body_reconstructions, key=lambda item: (item.created_at, item.id), reverse=True)
        ],
        object_reconstructions=[
            ObjectReconstructionRead(
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
            for reconstruction in sorted(asset.object_reconstructions, key=lambda item: (item.created_at, item.id), reverse=True)
        ],
    )


def _asset_neighbors(db: Session, asset_id: int) -> tuple[int | None, int | None]:
    ordered_asset_ids = db.execute(
        select(LogicalAsset.id).order_by(desc(LogicalAsset.capture_time), desc(LogicalAsset.id))
    ).scalars().all()
    try:
        current_index = ordered_asset_ids.index(asset_id)
    except ValueError:
        return None, None

    previous_asset_id = ordered_asset_ids[current_index - 1] if current_index > 0 else None
    next_asset_id = ordered_asset_ids[current_index + 1] if current_index + 1 < len(ordered_asset_ids) else None
    return previous_asset_id, next_asset_id


@router.get("", response_model=list[LogicalAssetListItem])
def list_assets(
    limit: int = Query(default=180, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ratings: str | None = Query(default=None),
    rating: int | None = Query(default=None, ge=0, le=5),
    rating_min: int | None = Query(default=None, ge=1, le=5),
    rating_max: int | None = Query(default=None, ge=0, le=5),
    unrated_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[LogicalAssetListItem]:
    stmt: Select[tuple[LogicalAsset]] = (
        select(LogicalAsset)
        .options(selectinload(LogicalAsset.physical_files), selectinload(LogicalAsset.people_links))
        .order_by(desc(LogicalAsset.capture_time), desc(LogicalAsset.id))
        .limit(limit)
        .offset(offset)
    )
    try:
        parsed_ratings = _parse_ratings_filter(ratings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if parsed_ratings:
        stmt = stmt.where(LogicalAsset.rating.in_(parsed_ratings))
    elif rating is not None:
        stmt = stmt.where(LogicalAsset.rating == rating)
    elif unrated_only:
        stmt = stmt.where(LogicalAsset.rating == 0)
    else:
        if rating_min is not None:
            stmt = stmt.where(LogicalAsset.rating >= rating_min)
        if rating_max is not None:
            stmt = stmt.where(LogicalAsset.rating <= rating_max)

    assets = db.execute(stmt).scalars().unique().all()
    return [_asset_to_list_item(asset) for asset in assets]


@router.get("/count")
def asset_count(db: Session = Depends(get_db)) -> dict[str, int]:
    total = db.execute(select(func.count()).select_from(LogicalAsset)).scalar_one()
    return {"total": total}


@router.get("/state", response_model=LibraryStateRead)
def library_state(db: Session = Depends(get_db)) -> LibraryStateRead:
    total_assets = db.execute(select(func.count()).select_from(LogicalAsset)).scalar_one()
    total_files = db.execute(select(func.count()).select_from(PhysicalFile)).scalar_one()
    latest_asset_updated_at = db.execute(select(func.max(LogicalAsset.updated_at))).scalar_one()
    active_scan_jobs = db.execute(
        select(func.count())
        .select_from(Job)
        .where(
            Job.job_type == JobType.SCAN,
            Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING)),
        )
    ).scalar_one()
    last_completed_scan_at = db.execute(
        select(func.max(Job.finished_at)).where(
            Job.job_type == JobType.SCAN,
            Job.status == JobStatus.COMPLETED,
        )
    ).scalar_one()
    return LibraryStateRead(
        total_assets=total_assets,
        total_files=total_files,
        latest_asset_updated_at=latest_asset_updated_at,
        active_scan_jobs=active_scan_jobs,
        last_completed_scan_at=last_completed_scan_at,
    )


@router.get("/{asset_id}", response_model=LogicalAssetDetail)
def get_asset(asset_id: int, db: Session = Depends(get_db)) -> LogicalAssetDetail:
    asset = (
        db.execute(
            select(LogicalAsset)
            .where(LogicalAsset.id == asset_id)
            .options(
                selectinload(LogicalAsset.physical_files),
                selectinload(LogicalAsset.faces).selectinload(Face.person),
                selectinload(LogicalAsset.people_links).selectinload(LogicalAssetPerson.person),
                selectinload(LogicalAsset.body_reconstructions).selectinload(BodyReconstruction.face).selectinload(Face.person),
                selectinload(LogicalAsset.object_reconstructions),
            )
        )
        .scalars()
        .unique()
        .one_or_none()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    previous_asset_id, next_asset_id = _asset_neighbors(db, asset.id)
    return _asset_to_detail(asset, previous_asset_id=previous_asset_id, next_asset_id=next_asset_id)


@router.patch("/{asset_id}/rating", response_model=LogicalAssetDetail)
def update_rating(
    asset_id: int,
    payload: RatingUpdate,
    db: Session = Depends(get_db),
) -> LogicalAssetDetail:
    asset = (
        db.execute(
            select(LogicalAsset)
            .where(LogicalAsset.id == asset_id)
            .options(
                selectinload(LogicalAsset.physical_files),
                selectinload(LogicalAsset.faces).selectinload(Face.person),
                selectinload(LogicalAsset.people_links).selectinload(LogicalAssetPerson.person),
                selectinload(LogicalAsset.body_reconstructions).selectinload(BodyReconstruction.face).selectinload(Face.person),
                selectinload(LogicalAsset.object_reconstructions),
            )
        )
        .scalars()
        .unique()
        .one_or_none()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset.rating = payload.rating
    db.commit()
    db.refresh(asset)
    asset = (
        db.execute(
            select(LogicalAsset)
            .where(LogicalAsset.id == asset_id)
            .options(
                selectinload(LogicalAsset.physical_files),
                selectinload(LogicalAsset.faces).selectinload(Face.person),
                selectinload(LogicalAsset.people_links).selectinload(LogicalAssetPerson.person),
                selectinload(LogicalAsset.body_reconstructions).selectinload(BodyReconstruction.face).selectinload(Face.person),
                selectinload(LogicalAsset.object_reconstructions),
            )
        )
        .scalars()
        .unique()
        .one()
    )
    metadata_service.sync_rating(db, asset)
    previous_asset_id, next_asset_id = _asset_neighbors(db, asset.id)
    return _asset_to_detail(asset, previous_asset_id=previous_asset_id, next_asset_id=next_asset_id)


@router.get("/{asset_id}/download-file")
def download_asset_file(
    asset_id: int,
    variant: str = Query(default="JPG", pattern="^(JPG|RAW)$"),
    db: Session = Depends(get_db),
) -> FileResponse:
    asset = (
        db.execute(
            select(LogicalAsset)
            .where(LogicalAsset.id == asset_id)
            .options(selectinload(LogicalAsset.physical_files))
        )
        .scalars()
        .unique()
        .one_or_none()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    selected_file = _select_download_file(asset, variant)
    if selected_file is None:
        raise HTTPException(status_code=404, detail=f"No {variant} file is available for this asset")

    source_path = Path(selected_file.file_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="File is missing on disk")

    return FileResponse(
        source_path,
        media_type=_download_media_type(selected_file),
        filename=source_path.name,
    )


@router.post("/download")
def download_assets(
    payload: AssetDownloadRequest,
    db: Session = Depends(get_db),
) -> FileResponse:
    unique_asset_ids = list(dict.fromkeys(payload.asset_ids))
    assets = (
        db.execute(
            select(LogicalAsset)
            .where(LogicalAsset.id.in_(unique_asset_ids))
            .options(selectinload(LogicalAsset.physical_files))
        )
        .scalars()
        .unique()
        .all()
    )
    if not assets:
        raise HTTPException(status_code=404, detail="No matching assets were found")

    selected_files: list[tuple[LogicalAsset, PhysicalFile]] = []
    skipped_assets: list[str] = []
    for asset in assets:
        selected_file = _select_download_file(asset, payload.variant)
        if selected_file is None:
            skipped_assets.append(asset.display_name)
            continue
        source_path = Path(selected_file.file_path)
        if not source_path.exists():
            skipped_assets.append(f"{asset.display_name} (missing on disk)")
            continue
        selected_files.append((asset, selected_file))

    if not selected_files:
        raise HTTPException(status_code=404, detail=f"No {payload.variant} files were available for the selected assets")

    common_root: Path | None = None
    try:
        common_root = Path(os_path.commonpath([str(Path(file.file_path).parent) for _, file in selected_files]))
    except ValueError:
        common_root = None

    temp_file = tempfile.NamedTemporaryFile(prefix=f"filmultra-{payload.variant.lower()}-", suffix=".zip", delete=False)
    temp_file.close()
    used_names: set[str] = set()
    with zipfile.ZipFile(temp_file.name, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for _, physical_file in selected_files:
            archive_name = _build_archive_name(physical_file, common_root, used_names)
            archive.write(physical_file.file_path, arcname=archive_name)

        if skipped_assets:
            archive.writestr(
                "_download_report.txt",
                "\n".join(
                    [
                        f"variant={payload.variant}",
                        f"included_files={len(selected_files)}",
                        f"skipped_assets={len(skipped_assets)}",
                        "",
                        *skipped_assets,
                    ]
                ),
            )

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return FileResponse(
        temp_file.name,
        media_type="application/zip",
        filename=f"filmultra-{payload.variant.lower()}-{timestamp}.zip",
        background=BackgroundTask(_cleanup_temp_file, temp_file.name),
    )
