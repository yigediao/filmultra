from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FaceRead(BaseModel):
    id: int
    logical_asset_id: int
    physical_file_id: int
    asset_display_name: str | None = None
    face_index: int
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    confidence: float
    cluster_id: str | None
    person_id: int | None
    person_name: str | None = None
    preview_url: str | None
    assignment_locked: bool
    is_excluded: bool


class AssetPersonRead(BaseModel):
    id: int
    name: str
    face_count: int
    cover_preview_url: str | None


class PersonListItem(BaseModel):
    id: int
    name: str
    alias: str | None
    notes: str | None
    cover_face_id: int | None
    cover_preview_url: str | None
    asset_count: int
    face_count: int
    positive_training_samples: int
    negative_training_samples: int
    core_template_samples: int
    support_template_samples: int
    weak_template_samples: int
    created_at: datetime
    updated_at: datetime


class PersonDetail(PersonListItem):
    assets: list[dict]
    sample_faces: list[FaceRead]
    faces: list[FaceRead]


class ClusterCandidate(BaseModel):
    cluster_id: str
    face_count: int
    asset_count: int
    sample_faces: list[FaceRead]


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    cluster_id: str
    alias: str | None = None
    notes: str | None = None


class PersonUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    alias: str | None = None
    notes: str | None = None


class PeopleMergeRequest(BaseModel):
    target_person_id: int
    source_person_ids: list[int]


class FaceAssignmentUpdate(BaseModel):
    action: str
    person_id: int | None = None


class PersonReviewCandidate(BaseModel):
    face: FaceRead
    decision_score: float
    centroid_similarity: float
    prototype_similarity: float
    exemplar_similarity: float
    negative_similarity: float | None = None
    competitor_score: float | None = None
    competitor_person_id: int | None = None
    competitor_person_name: str | None = None
    ambiguity: float
    uncertainty: float
    review_priority: float
    auto_assign_eligible: bool
    current_assignment_name: str | None = None


class PersonReviewFeedbackRequest(BaseModel):
    face_id: int
    action: str = Field(pattern="^(confirm|reject|skip)$")


class ReviewInboxItem(PersonReviewCandidate):
    target_person_id: int
    target_person_name: str
    target_cover_preview_url: str | None = None
