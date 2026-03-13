from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.job import JobStatus, JobType
from app.schemas.body3d import BodyMaskEditStroke


class ScanRequest(BaseModel):
    root_path: str | None = None


class FaceDetectRequest(BaseModel):
    asset_ids: list[int] | None = None


class ReclusterRequest(BaseModel):
    similarity_threshold: float | None = None


class Sam3dBodyRequest(BaseModel):
    asset_id: int
    face_id: int | None = None
    body_bbox: list[float] | None = None
    mask_index: int | None = None
    preview_id: str | None = None
    mask_edits: list[BodyMaskEditStroke] | None = None


class Sam3dObjectRequest(BaseModel):
    asset_id: int
    object_bbox: list[float]
    mask_index: int | None = None
    preview_id: str | None = None
    mask_edits: list[BodyMaskEditStroke] | None = None


class JobRead(BaseModel):
    id: int
    job_type: JobType
    status: JobStatus
    payload_json: dict | None
    result_json: dict | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}
