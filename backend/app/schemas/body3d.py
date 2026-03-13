from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BodyReconstructionPreviewRequest(BaseModel):
    asset_id: int
    face_id: int | None = None
    body_bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    mask_index: int | None = Field(default=None, ge=0)


class BodyMaskCandidateRead(BaseModel):
    index: int
    score: float
    overlay_url: str
    mask_url: str


class BodyMaskEditPoint(BaseModel):
    x: float
    y: float


class BodyMaskEditStroke(BaseModel):
    mode: Literal["add", "erase"]
    radius: float = Field(ge=1, le=512)
    points: list[BodyMaskEditPoint] = Field(min_length=1)


class BodyReconstructionPreviewRead(BaseModel):
    preview_id: str
    asset_id: int
    face_id: int | None
    source_image_url: str
    face_preview_url: str | None
    prompt_bbox: list[float]
    image_width: int
    image_height: int
    selected_mask_index: int
    candidates: list[BodyMaskCandidateRead]
