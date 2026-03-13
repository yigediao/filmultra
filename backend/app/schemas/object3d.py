from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.body3d import BodyMaskCandidateRead, BodyMaskEditStroke


class ObjectReconstructionPreviewRequest(BaseModel):
    asset_id: int
    object_bbox: list[float] = Field(min_length=4, max_length=4)
    mask_index: int | None = Field(default=None, ge=0)


class ObjectReconstructionPreviewRead(BaseModel):
    preview_id: str
    asset_id: int
    source_image_url: str
    prompt_bbox: list[float]
    image_width: int
    image_height: int
    selected_mask_index: int
    candidates: list[BodyMaskCandidateRead]


class ObjectReconstructionRead(BaseModel):
    id: int
    logical_asset_id: int
    job_id: int | None
    status: str
    overlay_url: str | None
    mask_url: str | None
    bundle_url: str | None
    glb_url: str | None
    glb_download_url: str | None
    gaussian_ply_url: str | None
    result_json: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class Sam3dObjectRequestPayload(BaseModel):
    asset_id: int
    object_bbox: list[float] = Field(min_length=4, max_length=4)
    mask_index: int | None = Field(default=None, ge=0)
    preview_id: str | None = None
    mask_edits: list[BodyMaskEditStroke] | None = None
