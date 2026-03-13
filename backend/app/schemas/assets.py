from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.asset import FileType
from app.schemas.people import AssetPersonRead, FaceRead
from app.schemas.object3d import ObjectReconstructionRead


class PhysicalFileRead(BaseModel):
    id: int
    file_path: str
    directory_path: str
    basename: str
    extension: str
    file_type: FileType
    file_size: int
    capture_time: datetime | None
    width: int | None
    height: int | None
    is_hero: bool
    metadata_json: dict | None

    model_config = {"from_attributes": True}


class LogicalAssetListItem(BaseModel):
    id: int
    capture_key: str
    display_name: str
    rating: int
    capture_time: datetime | None
    camera_model: str | None
    lens_model: str | None
    width: int | None
    height: int | None
    file_count: int
    hero_file_id: int | None
    hero_preview_url: str | None
    people_count: int


class BodyReconstructionRead(BaseModel):
    id: int
    logical_asset_id: int
    face_id: int | None
    person_id: int | None
    person_name: str | None
    job_id: int | None
    status: str
    overlay_url: str | None
    mask_url: str | None
    bundle_url: str | None
    face_preview_url: str | None
    mesh_object_urls: list[str]
    result_json: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class LogicalAssetDetail(BaseModel):
    id: int
    capture_key: str
    display_name: str
    rating: int
    pick_flag: bool
    reject_flag: bool
    color_label: str | None
    capture_time: datetime | None
    camera_model: str | None
    lens_model: str | None
    width: int | None
    height: int | None
    hero_file_id: int | None
    hero_preview_url: str | None
    hero_display_url: str | None
    hero_metadata: dict | None
    previous_asset_id: int | None
    next_asset_id: int | None
    physical_files: list[PhysicalFileRead]
    people: list[AssetPersonRead]
    faces: list[FaceRead]
    body_reconstructions: list[BodyReconstructionRead]
    object_reconstructions: list[ObjectReconstructionRead]


class RatingUpdate(BaseModel):
    rating: int = Field(ge=0, le=5)


class AssetDownloadRequest(BaseModel):
    asset_ids: list[int] = Field(min_length=1)
    variant: Literal["JPG", "RAW"]


class LibraryStateRead(BaseModel):
    total_assets: int
    total_files: int
    latest_asset_updated_at: datetime | None
    active_scan_jobs: int
    last_completed_scan_at: datetime | None
