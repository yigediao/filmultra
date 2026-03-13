from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.asset import LogicalAsset
from app.models.people import Face, LogicalAssetPerson, Person
from app.schemas.assets import LogicalAssetListItem
from app.schemas.people import (
    ClusterCandidate,
    FaceRead,
    PeopleMergeRequest,
    PersonCreate,
    PersonDetail,
    PersonListItem,
    PersonReviewCandidate,
    PersonReviewFeedbackRequest,
    PersonUpdate,
    ReviewInboxItem,
)
from app.services.faces import FacePipelineService


router = APIRouter(prefix="/people", tags=["people"])
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
        preview_url=f"/api/faces/{face.id}/preview",
        assignment_locked=face.assignment_locked,
        is_excluded=face.is_excluded,
    )


def _asset_to_list_item(asset: LogicalAsset) -> LogicalAssetListItem:
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
        hero_preview_url=f"/api/files/{asset.hero_file_id}/preview" if asset.hero_file_id else None,
        people_count=len(asset.people_links),
    )


def _person_to_list_item(person: Person, template_summary: dict[str, int] | None = None) -> PersonListItem:
    face_count = len(person.faces)
    asset_count = len(person.asset_links)
    summary = template_summary or {
        "positive_training_samples": 0,
        "negative_training_samples": 0,
        "core_template_samples": 0,
        "support_template_samples": 0,
        "weak_template_samples": 0,
    }
    return PersonListItem(
        id=person.id,
        name=person.name,
        alias=person.alias,
        notes=person.notes,
        cover_face_id=person.cover_face_id,
        cover_preview_url=f"/api/faces/{person.cover_face_id}/preview" if person.cover_face_id else None,
        asset_count=asset_count,
        face_count=face_count,
        positive_training_samples=int(summary["positive_training_samples"]),
        negative_training_samples=int(summary["negative_training_samples"]),
        core_template_samples=int(summary["core_template_samples"]),
        support_template_samples=int(summary["support_template_samples"]),
        weak_template_samples=int(summary["weak_template_samples"]),
        created_at=person.created_at,
        updated_at=person.updated_at,
    )


def _review_candidate_to_read(candidate: dict[str, object], people_by_id: dict[int, Person]) -> PersonReviewCandidate:
    competitor_person_id = candidate["competitor_person_id"]
    competitor_person = people_by_id.get(int(competitor_person_id)) if competitor_person_id is not None else None
    return PersonReviewCandidate(
        face=_face_to_read(candidate["face"]),
        decision_score=float(candidate["decision_score"]),
        centroid_similarity=float(candidate["centroid_similarity"]),
        prototype_similarity=float(candidate["prototype_similarity"]),
        exemplar_similarity=float(candidate["exemplar_similarity"]),
        negative_similarity=float(candidate["negative_similarity"]) if candidate["negative_similarity"] is not None else None,
        competitor_score=float(candidate["competitor_score"]) if candidate["competitor_score"] is not None else None,
        competitor_person_id=int(competitor_person_id) if competitor_person_id is not None else None,
        competitor_person_name=competitor_person.name if competitor_person is not None else None,
        ambiguity=float(candidate["ambiguity"]),
        uncertainty=float(candidate["uncertainty"]),
        review_priority=float(candidate["review_priority"]),
        auto_assign_eligible=bool(candidate["auto_assign_eligible"]),
        current_assignment_name=str(candidate["current_assignment_name"]) if candidate["current_assignment_name"] is not None else None,
    )


def _review_inbox_item_to_read(candidate: dict[str, object], people_by_id: dict[int, Person]) -> ReviewInboxItem:
    base = _review_candidate_to_read(candidate, people_by_id)
    target_person = candidate["target_person"]
    return ReviewInboxItem(
        **base.model_dump(),
        target_person_id=target_person.id,
        target_person_name=target_person.name,
        target_cover_preview_url=f"/api/faces/{target_person.cover_face_id}/preview" if target_person.cover_face_id else None,
    )


@router.get("", response_model=list[PersonListItem])
def list_people(db: Session = Depends(get_db)) -> list[PersonListItem]:
    people = (
        db.execute(
            select(Person)
            .options(
                selectinload(Person.faces).selectinload(Face.logical_asset),
                selectinload(Person.asset_links),
                selectinload(Person.training_samples),
            )
            .order_by(func.lower(Person.name), Person.id)
        )
        .scalars()
        .unique()
        .all()
    )
    template_summaries = face_service.summarize_training_samples(db, people)
    return [_person_to_list_item(person, template_summaries.get(person.id)) for person in people]


@router.get("/clusters", response_model=list[ClusterCandidate])
def list_clusters(db: Session = Depends(get_db)) -> list[ClusterCandidate]:
    faces = (
        db.execute(
            select(Face)
            .where(Face.person_id.is_(None), Face.cluster_id.is_not(None), Face.is_excluded.is_(False))
            .options(selectinload(Face.person), selectinload(Face.logical_asset))
            .order_by(Face.cluster_id, Face.confidence.desc(), Face.id)
        )
        .scalars()
        .all()
    )
    grouped: dict[str, list[Face]] = {}
    for face in faces:
        grouped.setdefault(face.cluster_id or "cluster:unknown", []).append(face)

    clusters: list[ClusterCandidate] = []
    for cluster_id, cluster_faces in grouped.items():
        asset_ids = {face.logical_asset_id for face in cluster_faces}
        sample_faces = sorted(cluster_faces, key=lambda face: (face.confidence, -face.id), reverse=True)[:6]
        clusters.append(
            ClusterCandidate(
                cluster_id=cluster_id,
                face_count=len(cluster_faces),
                asset_count=len(asset_ids),
                sample_faces=[_face_to_read(face) for face in sample_faces],
            )
        )
    return sorted(clusters, key=lambda cluster: (-cluster.face_count, cluster.cluster_id))


@router.get("/review-inbox", response_model=list[ReviewInboxItem])
def get_review_inbox(
    limit: int = Query(default=30, ge=1, le=90),
    per_person_limit: int = Query(default=12, ge=1, le=24),
    db: Session = Depends(get_db),
) -> list[ReviewInboxItem]:
    people = db.execute(select(Person).order_by(Person.id)).scalars().all()
    people_by_id = {person.id: person for person in people}
    candidates = face_service.list_review_inbox(db, limit=limit, per_person_limit=per_person_limit)
    return [_review_inbox_item_to_read(candidate, people_by_id) for candidate in candidates]


@router.get("/{person_id}", response_model=PersonDetail)
def get_person(person_id: int, db: Session = Depends(get_db)) -> PersonDetail:
    person = (
        db.execute(
            select(Person)
            .where(Person.id == person_id)
            .options(
                selectinload(Person.faces).selectinload(Face.logical_asset),
                selectinload(Person.asset_links),
                selectinload(Person.training_samples),
            )
        )
        .scalars()
        .unique()
        .one_or_none()
    )
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    assets = (
        db.execute(
            select(LogicalAsset)
            .join(LogicalAssetPerson, LogicalAssetPerson.logical_asset_id == LogicalAsset.id)
            .where(LogicalAssetPerson.person_id == person_id)
            .options(selectinload(LogicalAsset.physical_files), selectinload(LogicalAsset.people_links))
            .order_by(LogicalAsset.capture_time.desc(), LogicalAsset.id.desc())
        )
        .scalars()
        .unique()
        .all()
    )
    sample_faces = sorted(person.faces, key=lambda face: (face.confidence, -face.id), reverse=True)[:12]
    template_summaries = face_service.summarize_training_samples(db, [person])
    summary = _person_to_list_item(person, template_summaries.get(person.id))
    return PersonDetail(
        **summary.model_dump(),
        assets=[_asset_to_list_item(asset).model_dump() for asset in assets],
        sample_faces=[_face_to_read(face) for face in sample_faces],
        faces=[_face_to_read(face) for face in sorted(person.faces, key=lambda face: (face.confidence, -face.id), reverse=True)],
    )


@router.get("/{person_id}/assets", response_model=list[LogicalAssetListItem])
def get_person_assets(person_id: int, db: Session = Depends(get_db)) -> list[LogicalAssetListItem]:
    assets = (
        db.execute(
            select(LogicalAsset)
            .join(LogicalAssetPerson, LogicalAssetPerson.logical_asset_id == LogicalAsset.id)
            .where(LogicalAssetPerson.person_id == person_id)
            .options(selectinload(LogicalAsset.physical_files), selectinload(LogicalAsset.people_links))
            .order_by(LogicalAsset.capture_time.desc(), LogicalAsset.id.desc())
        )
        .scalars()
        .unique()
        .all()
    )
    return [_asset_to_list_item(asset) for asset in assets]


@router.get("/{person_id}/review-candidates", response_model=list[PersonReviewCandidate])
def get_person_review_candidates(
    person_id: int,
    limit: int = Query(default=18, ge=1, le=60),
    db: Session = Depends(get_db),
) -> list[PersonReviewCandidate]:
    people = db.execute(select(Person).order_by(Person.id)).scalars().all()
    people_by_id = {person.id: person for person in people}
    try:
        candidates = face_service.list_review_candidates(db, person_id=person_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_review_candidate_to_read(candidate, people_by_id) for candidate in candidates]


@router.post("", response_model=PersonListItem)
def create_person(payload: PersonCreate, db: Session = Depends(get_db)) -> PersonListItem:
    try:
        person = face_service.create_person_from_cluster(
            db,
            name=payload.name,
            cluster_id=payload.cluster_id,
            alias=payload.alias,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    person = (
        db.execute(
            select(Person)
            .where(Person.id == person.id)
            .options(
                selectinload(Person.faces).selectinload(Face.logical_asset),
                selectinload(Person.asset_links),
                selectinload(Person.training_samples),
            )
        )
        .scalars()
        .unique()
        .one()
    )
    template_summaries = face_service.summarize_training_samples(db, [person])
    return _person_to_list_item(person, template_summaries.get(person.id))


@router.patch("/{person_id}", response_model=PersonListItem)
def update_person(person_id: int, payload: PersonUpdate, db: Session = Depends(get_db)) -> PersonListItem:
    person = db.execute(select(Person).where(Person.id == person_id)).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    updates = payload.model_dump(exclude_unset=True)
    person = face_service.update_person(db, person, updates)
    person = (
        db.execute(
            select(Person)
            .where(Person.id == person.id)
            .options(
                selectinload(Person.faces).selectinload(Face.logical_asset),
                selectinload(Person.asset_links),
                selectinload(Person.training_samples),
            )
        )
        .scalars()
        .unique()
        .one()
    )
    template_summaries = face_service.summarize_training_samples(db, [person])
    return _person_to_list_item(person, template_summaries.get(person.id))


@router.post("/merge", response_model=PersonListItem)
def merge_people(payload: PeopleMergeRequest, db: Session = Depends(get_db)) -> PersonListItem:
    try:
        person = face_service.merge_people(
            db,
            target_person_id=payload.target_person_id,
            source_person_ids=payload.source_person_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    person = (
        db.execute(
            select(Person)
            .where(Person.id == person.id)
            .options(
                selectinload(Person.faces).selectinload(Face.logical_asset),
                selectinload(Person.asset_links),
                selectinload(Person.training_samples),
            )
        )
        .scalars()
        .unique()
        .one()
    )
    template_summaries = face_service.summarize_training_samples(db, [person])
    return _person_to_list_item(person, template_summaries.get(person.id))


@router.post("/{person_id}/review-feedback", response_model=FaceRead)
def review_person_candidate(
    person_id: int,
    payload: PersonReviewFeedbackRequest,
    db: Session = Depends(get_db),
) -> FaceRead:
    try:
        face = face_service.review_candidate(
            db,
            person_id=person_id,
            face_id=payload.face_id,
            action=payload.action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
