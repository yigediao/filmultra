from __future__ import annotations

import hashlib
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.asset import LogicalAsset
from app.models.job import Job, JobStatus, JobType
from app.models.people import Face, FaceReviewFeedback, FaceTrainingSample, LogicalAssetPerson, Person
from app.services.preview import PreviewService

try:
    import cv2
except ImportError:  # pragma: no cover - optional during bootstrap
    cv2 = None


class FacePipelineService:
    POSITIVE_FEEDBACK = "positive"
    NEGATIVE_FEEDBACK = "negative"
    REVIEW_CONFIRM = "confirm"
    REVIEW_REJECT = "reject"
    REVIEW_SKIP = "skip"
    TEMPLATE_TIER_CORE = "core"
    TEMPLATE_TIER_SUPPORT = "support"
    TEMPLATE_TIER_WEAK = "weak"
    FACE_SCAN_STATUS_PENDING = "pending"
    FACE_SCAN_STATUS_COMPLETED = "completed"
    FACE_SCAN_STATUS_FAILED = "failed"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.preview_service = PreviewService()
        self.models_dir = Path(self.settings.face_models_dir).expanduser()
        self._face_blur_score_cache: dict[str, float] = {}

    def create_face_detect_job(self, db: Session, asset_ids: list[int] | None = None) -> Job:
        job = Job(
            job_type=JobType.FACE_DETECT,
            status=JobStatus.PENDING,
            payload_json={"asset_ids": asset_ids},
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def run_face_detect_job(self, job_id: int) -> None:
        db = SessionLocal()
        job = db.get(Job, job_id)
        if job is None:
            db.close()
            return

        try:
            asset_ids = None
            if job.payload_json:
                payload_asset_ids = job.payload_json.get("asset_ids")
                if isinstance(payload_asset_ids, list):
                    asset_ids = [int(asset_id) for asset_id in payload_asset_ids]

            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            job.error_message = None
            job.result_json = None
            db.commit()

            result = self._execute_face_detect(db, asset_ids=asset_ids)
            job.status = JobStatus.COMPLETED
            job.result_json = result
            job.finished_at = datetime.utcnow()
            db.commit()
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def detect_faces(self, db: Session, asset_ids: list[int] | None = None) -> Job:
        job = self.create_face_detect_job(db, asset_ids)
        self.run_face_detect_job(job.id)
        db.refresh(job)
        return job

    def create_recluster_job(self, db: Session, similarity_threshold: float | None = None) -> Job:
        job = Job(
            job_type=JobType.RECLUSTER,
            status=JobStatus.PENDING,
            payload_json={"similarity_threshold": similarity_threshold},
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def run_recluster_job(self, job_id: int) -> None:
        db = SessionLocal()
        job = db.get(Job, job_id)
        if job is None:
            db.close()
            return

        try:
            similarity_threshold = None
            if job.payload_json:
                payload_threshold = job.payload_json.get("similarity_threshold")
                if payload_threshold is not None:
                    similarity_threshold = float(payload_threshold)

            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            job.error_message = None
            job.result_json = None
            db.commit()

            result = self._recluster_faces(db, similarity_threshold=similarity_threshold)
            job.status = JobStatus.COMPLETED
            job.result_json = result
            job.finished_at = datetime.utcnow()
            db.commit()
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def recluster(self, db: Session, similarity_threshold: float | None = None) -> Job:
        job = self.create_recluster_job(db, similarity_threshold)
        self.run_recluster_job(job.id)
        db.refresh(job)
        return job

    def _execute_face_detect(self, db: Session, asset_ids: list[int] | None = None) -> dict[str, object]:
        assets = self._load_assets(db, asset_ids)
        if not assets:
            return {
                "processed_assets": 0,
                "detected_faces": 0,
                "named_people": 0,
                "unnamed_clusters": 0,
                "errors": [],
            }

        detector, recognizer = self._load_models()
        self._reset_asset_faces(db, [asset.id for asset in assets])

        detected_faces = 0
        skipped_blurry_faces = 0
        errors: list[dict[str, str | int]] = []
        for asset in assets:
            try:
                faces, skipped_blurry = self._extract_asset_faces(asset, detector, recognizer)
                for face in faces:
                    db.add(face)
                detected_faces += len(faces)
                skipped_blurry_faces += skipped_blurry
                asset.face_scan_status = self.FACE_SCAN_STATUS_COMPLETED
                asset.face_scan_signature = self._asset_face_scan_signature(asset)
                asset.face_scan_completed_at = datetime.utcnow()
            except Exception as exc:  # pragma: no cover - file-specific failures
                asset.face_scan_status = self.FACE_SCAN_STATUS_FAILED
                asset.face_scan_signature = self._asset_face_scan_signature(asset)
                asset.face_scan_completed_at = datetime.utcnow()
                errors.append({"asset_id": asset.id, "display_name": asset.display_name, "error": str(exc)})

        db.commit()
        cluster_result = self._recluster_faces(db, similarity_threshold=None)
        return {
            "processed_assets": len(assets),
            "detected_faces": detected_faces,
            "skipped_blurry_faces": skipped_blurry_faces,
            "named_people": cluster_result["named_people"],
            "unnamed_clusters": cluster_result["unnamed_clusters"],
            "errors": errors,
        }

    def create_person_from_cluster(
        self,
        db: Session,
        *,
        name: str,
        cluster_id: str,
        alias: str | None = None,
        notes: str | None = None,
    ) -> Person:
        normalized_name = self._normalize_person_name(name)
        faces = db.execute(select(Face).where(Face.cluster_id == cluster_id)).scalars().all()
        if not faces:
            raise ValueError(f"Cluster not found: {cluster_id}")

        person = self._find_person_by_normalized_name(db, normalized_name)
        if person is None:
            person = Person(name=name.strip(), alias=alias, notes=notes)
            db.add(person)
            db.flush()
        else:
            if not person.alias and alias:
                person.alias = alias
            if not person.notes and notes:
                person.notes = notes

        for face in faces:
            self._clear_feedback_for_face(db, face.id)
            face.person = person
            face.person_id = person.id
            face.cluster_id = f"person:{person.id}"
            self._record_feedback_from_face(
                db,
                face=face,
                person_id=person.id,
                feedback_type=self.POSITIVE_FEEDBACK,
            )

        db.flush()
        self._rebuild_people_indexes(db)
        db.commit()
        db.refresh(person)
        return person

    def update_person(
        self,
        db: Session,
        person: Person,
        updates: dict[str, object],
    ) -> Person:
        target_name = None
        if "name" in updates and updates["name"] is not None:
            target_name = str(updates["name"]).strip()
            normalized_name = self._normalize_person_name(target_name)
            duplicate = self._find_person_by_normalized_name(db, normalized_name, exclude_person_id=person.id)
            person.name = target_name
            if duplicate is not None:
                self._merge_person_data(target=person, source=duplicate)
                db.flush()
                source_people = [duplicate]
                source_faces = db.execute(select(Face).where(Face.person_id == duplicate.id)).scalars().all()
                for face in source_faces:
                    face.person = person
                    face.person_id = person.id
                    face.cluster_id = f"person:{person.id}"
                self._merge_training_samples(db, target_person=person, source_person_ids=[duplicate.id])
                db.flush()
                for source_person in source_people:
                    db.delete(source_person)
                self._rebuild_people_indexes(db)
                db.commit()
                db.refresh(person)
                return person
        if "alias" in updates:
            person.alias = None if updates["alias"] is None else str(updates["alias"])
        if "notes" in updates:
            person.notes = None if updates["notes"] is None else str(updates["notes"])
        db.commit()
        db.refresh(person)
        return person

    def assign_face_to_person(self, db: Session, *, face_id: int, person_id: int) -> Face:
        face = db.execute(select(Face).where(Face.id == face_id)).scalar_one_or_none()
        if face is None:
            raise ValueError("Face not found")

        person = db.execute(select(Person).where(Person.id == person_id)).scalar_one_or_none()
        if person is None:
            raise ValueError("Person not found")

        previous_person_id = face.person_id
        self._clear_feedback_for_face(db, face.id)
        if previous_person_id is not None and previous_person_id != person_id:
            self._record_feedback_from_face(
                db,
                face=face,
                person_id=previous_person_id,
                feedback_type=self.NEGATIVE_FEEDBACK,
            )
        face.person = person
        face.person_id = person_id
        face.cluster_id = f"person:{person_id}"
        face.assignment_locked = True
        face.is_excluded = False
        self._record_feedback_from_face(
            db,
            face=face,
            person_id=person_id,
            feedback_type=self.POSITIVE_FEEDBACK,
        )
        db.flush()
        self._rebuild_people_indexes(db)
        db.commit()
        db.refresh(face)
        return face

    def unassign_face(self, db: Session, *, face_id: int) -> Face:
        face = db.execute(select(Face).where(Face.id == face_id)).scalar_one_or_none()
        if face is None:
            raise ValueError("Face not found")

        previous_person_id = face.person_id
        self._clear_feedback_for_face(db, face.id)
        if previous_person_id is not None:
            self._record_feedback_from_face(
                db,
                face=face,
                person_id=previous_person_id,
                feedback_type=self.NEGATIVE_FEEDBACK,
            )
        face.person = None
        face.person_id = None
        face.cluster_id = f"manual:unassigned:{face.id}"
        face.assignment_locked = True
        face.is_excluded = False
        db.flush()
        self._rebuild_people_indexes(db)
        db.commit()
        db.refresh(face)
        return face

    def restore_face_to_auto(self, db: Session, *, face_id: int) -> Face:
        face = db.execute(select(Face).where(Face.id == face_id)).scalar_one_or_none()
        if face is None:
            raise ValueError("Face not found")

        self._clear_feedback_for_face(db, face.id)
        face.person = None
        face.person_id = None
        face.cluster_id = None
        face.assignment_locked = False
        face.is_excluded = False
        db.flush()
        self._recluster_faces(db, similarity_threshold=None)
        db.refresh(face)
        return face

    def merge_people(self, db: Session, *, target_person_id: int, source_person_ids: list[int]) -> Person:
        if not source_person_ids:
            raise ValueError("source_person_ids is required")

        target = db.execute(select(Person).where(Person.id == target_person_id)).scalar_one_or_none()
        if target is None:
            raise ValueError("Target person not found")

        clean_source_ids = [person_id for person_id in source_person_ids if person_id != target_person_id]
        if not clean_source_ids:
            return target

        source_people = db.execute(select(Person).where(Person.id.in_(clean_source_ids))).scalars().all()
        source_ids_found = {person.id for person in source_people}
        if len(source_ids_found) != len(set(clean_source_ids)):
            raise ValueError("One or more source people were not found")

        for source_person in source_people:
            self._merge_person_data(target=target, source=source_person)

        faces = db.execute(select(Face).where(Face.person_id.in_(clean_source_ids))).scalars().all()
        for face in faces:
            face.person = target
            face.person_id = target_person_id
            face.cluster_id = f"person:{target_person_id}"

        self._merge_training_samples(db, target_person=target, source_person_ids=clean_source_ids)
        db.flush()
        for person in source_people:
            db.delete(person)

        self._rebuild_people_indexes(db)
        db.commit()
        db.refresh(target)
        return target

    def list_review_candidates(self, db: Session, *, person_id: int, limit: int = 24) -> list[dict[str, object]]:
        person = (
            db.execute(
                select(Person)
                .where(Person.id == person_id)
                .options(selectinload(Person.faces), selectinload(Person.training_samples))
                .execution_options(populate_existing=True)
            )
            .scalars()
            .one_or_none()
        )
        if person is None:
            raise ValueError("Person not found")

        people = (
            db.execute(
                select(Person)
                .options(selectinload(Person.faces), selectinload(Person.training_samples))
                .order_by(Person.id)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .unique()
            .all()
        )
        profiles = self._build_person_profiles(db, people)
        if person_id not in profiles:
            return []

        review_feedback = (
            db.execute(select(FaceReviewFeedback).where(FaceReviewFeedback.person_id == person_id))
            .scalars()
            .all()
        )
        feedback_by_key = {
            (item.logical_asset_id, item.embedding_digest): item
            for item in review_feedback
        }
        faces = (
            db.execute(
                select(Face)
                .options(selectinload(Face.person), selectinload(Face.logical_asset))
                .order_by(Face.id.desc())
                .execution_options(populate_existing=True)
            )
            .scalars()
            .all()
        )

        auto_threshold = max(
            self.settings.face_cluster_similarity_threshold,
            self.settings.face_learning_match_threshold,
        )
        candidates: list[dict[str, object]] = []
        for face in faces:
            if face.is_excluded or face.assignment_locked:
                continue

            embedding = self._embedding(face)
            if embedding is None:
                continue

            ranked = self._rank_person_candidates(
                embedding,
                profiles,
                min_score=self.settings.face_review_candidate_threshold,
            )
            if not ranked:
                continue

            target_candidate = next((item for item in ranked if item["person_id"] == person_id), None)
            if target_candidate is None:
                continue

            top_candidate = ranked[0]
            competitor = next((item for item in ranked if item["person_id"] != person_id), None)
            if top_candidate["person_id"] != person_id:
                top_gap = float(top_candidate["decision_score"]) - float(target_candidate["decision_score"])
                if top_gap > self.settings.face_learning_competitor_margin * 0.5:
                    continue

            auto_assign_eligible = self._is_auto_assign_eligible(
                target_candidate,
                competitor,
                auto_threshold=auto_threshold,
            )
            if auto_assign_eligible and face.person_id == person_id:
                continue

            face_key = self._face_feedback_key(face.logical_asset_id, embedding)
            feedback = feedback_by_key.get(face_key)
            if feedback is not None and self._should_suppress_review_candidate(
                feedback,
                current_score=float(target_candidate["decision_score"]),
            ):
                continue

            uncertainty = self._candidate_uncertainty(
                float(target_candidate["decision_score"]),
                auto_threshold=auto_threshold,
            )
            ambiguity = self._candidate_ambiguity(
                float(target_candidate["decision_score"]),
                float(competitor["decision_score"]) if competitor is not None else None,
            )
            review_priority = self._candidate_review_priority(
                face_confidence=face.confidence,
                decision_score=float(target_candidate["decision_score"]),
                uncertainty=uncertainty,
                ambiguity=ambiguity,
                current_person_id=face.person_id,
                target_person_id=person_id,
            )
            candidates.append(
                {
                    "face": face,
                    "decision_score": float(target_candidate["decision_score"]),
                    "centroid_similarity": float(target_candidate["centroid_similarity"]),
                    "prototype_similarity": float(target_candidate["prototype_similarity"]),
                    "exemplar_similarity": float(target_candidate["exemplar_similarity"]),
                    "negative_similarity": target_candidate["negative_similarity"],
                    "competitor_score": float(competitor["decision_score"]) if competitor is not None else None,
                    "competitor_person_id": int(competitor["person_id"]) if competitor is not None else None,
                    "ambiguity": ambiguity,
                    "uncertainty": uncertainty,
                    "review_priority": review_priority,
                    "auto_assign_eligible": auto_assign_eligible,
                    "current_assignment_name": face.person.name if face.person is not None else None,
                }
            )

        candidates.sort(
            key=lambda item: (
                -float(item["review_priority"]),
                -float(item["decision_score"]),
                -int(item["face"].id),
            )
        )
        return candidates[:limit]

    def list_review_inbox(
        self,
        db: Session,
        *,
        limit: int = 36,
        per_person_limit: int = 12,
    ) -> list[dict[str, object]]:
        people = (
            db.execute(
                select(Person)
                .options(selectinload(Person.faces), selectinload(Person.training_samples))
                .order_by(func.lower(Person.name), Person.id)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .unique()
            .all()
        )
        if not people:
            return []

        candidate_limit = max(1, min(per_person_limit, limit))
        best_by_face_id: dict[int, dict[str, object]] = {}
        for person in people:
            person_candidates = self.list_review_candidates(db, person_id=person.id, limit=candidate_limit)
            for candidate in person_candidates:
                face = candidate["face"]
                inbox_item = {
                    **candidate,
                    "target_person": person,
                }
                existing = best_by_face_id.get(face.id)
                if existing is None or self._is_higher_priority_review_candidate(inbox_item, existing):
                    best_by_face_id[face.id] = inbox_item

        ranked_items = list(best_by_face_id.values())
        ranked_items.sort(
            key=lambda item: (
                -float(item["review_priority"]),
                -float(item["decision_score"]),
                -int(item["face"].id),
            )
        )
        return ranked_items[:limit]

    def summarize_training_samples(self, db: Session, people: list[Person]) -> dict[int, dict[str, int]]:
        if not people:
            return {}

        source_faces = self._load_training_source_faces(db, people)
        summaries: dict[int, dict[str, int]] = {}
        for person in people:
            positive_templates = self._build_training_templates(
                [
                    sample
                    for sample in person.training_samples
                    if sample.is_active and sample.feedback_type == self.POSITIVE_FEEDBACK
                ],
                source_faces,
            )
            negative_templates = self._build_training_templates(
                [
                    sample
                    for sample in person.training_samples
                    if sample.is_active and sample.feedback_type == self.NEGATIVE_FEEDBACK
                ],
                source_faces,
            )
            summaries[person.id] = {
                "positive_training_samples": len(positive_templates),
                "negative_training_samples": len(negative_templates),
                "core_template_samples": sum(
                    1 for template in positive_templates if template["tier"] == self.TEMPLATE_TIER_CORE
                ),
                "support_template_samples": sum(
                    1 for template in positive_templates if template["tier"] == self.TEMPLATE_TIER_SUPPORT
                ),
                "weak_template_samples": sum(
                    1 for template in positive_templates if template["tier"] == self.TEMPLATE_TIER_WEAK
                ),
            }
        return summaries

    def review_candidate(self, db: Session, *, person_id: int, face_id: int, action: str) -> Face:
        person = db.execute(select(Person).where(Person.id == person_id)).scalar_one_or_none()
        if person is None:
            raise ValueError("Person not found")

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
            raise ValueError("Face not found")

        embedding = self._embedding(face)
        score = None
        if embedding is not None:
            people = (
                db.execute(
                    select(Person)
                    .options(selectinload(Person.faces), selectinload(Person.training_samples))
                    .order_by(Person.id)
                    .execution_options(populate_existing=True)
                )
                .scalars()
                .unique()
                .all()
            )
            profiles = self._build_person_profiles(db, people)
            ranked = self._rank_person_candidates(embedding, profiles, min_score=0.0)
            candidate = next((item for item in ranked if item["person_id"] == person_id), None)
            score = float(candidate["decision_score"]) if candidate is not None else None

        if action == self.REVIEW_CONFIRM:
            face = self.assign_face_to_person(db, face_id=face_id, person_id=person_id)
        elif action == self.REVIEW_REJECT:
            face = self.reject_face_for_person(db, face_id=face_id, person_id=person_id)
        elif action == self.REVIEW_SKIP:
            db.refresh(face)
        else:
            raise ValueError("Unsupported review action")

        self._upsert_review_feedback(
            db,
            person_id=person_id,
            face=face,
            decision=action,
            suggested_score=score,
        )
        db.commit()
        db.refresh(face)
        return face

    def reject_face_for_person(self, db: Session, *, face_id: int, person_id: int) -> Face:
        face = db.execute(select(Face).where(Face.id == face_id)).scalar_one_or_none()
        if face is None:
            raise ValueError("Face not found")

        if face.person_id == person_id:
            self._clear_feedback_for_face(db, face.id)
            face.person = None
            face.person_id = None
            face.cluster_id = None

        embedding = self._embedding(face)
        if embedding is not None:
            self._upsert_training_sample(
                db,
                person_id=person_id,
                feedback_type=self.NEGATIVE_FEEDBACK,
                embedding=embedding,
                source_face_id=face.id,
                source_logical_asset_id=face.logical_asset_id,
            )

        face.assignment_locked = False
        face.is_excluded = False
        db.flush()
        self._rebuild_people_indexes(db)
        return face

    def _find_person_by_normalized_name(
        self,
        db: Session,
        normalized_name: str,
        exclude_person_id: int | None = None,
    ) -> Person | None:
        people = db.execute(select(Person).order_by(Person.id)).scalars().all()
        for person in people:
            if exclude_person_id is not None and person.id == exclude_person_id:
                continue
            if self._normalize_person_name(person.name) == normalized_name:
                return person
        return None

    def _normalize_person_name(self, name: str) -> str:
        normalized = " ".join(name.split()).casefold()
        if not normalized:
            raise ValueError("Person name cannot be blank")
        return normalized

    def _merge_person_data(self, *, target: Person, source: Person) -> None:
        if not target.alias and source.alias:
            target.alias = source.alias
        if not target.notes and source.notes:
            target.notes = source.notes

    def _merge_training_samples(self, db: Session, *, target_person: Person, source_person_ids: list[int]) -> None:
        if not source_person_ids:
            return

        source_samples = (
            db.execute(select(FaceTrainingSample).where(FaceTrainingSample.person_id.in_(source_person_ids)))
            .scalars()
            .all()
        )
        existing_samples = (
            db.execute(select(FaceTrainingSample).where(FaceTrainingSample.person_id == target_person.id))
            .scalars()
            .all()
        )
        existing_by_key = {
            (sample.feedback_type, sample.embedding_digest): sample
            for sample in existing_samples
        }

        for sample in source_samples:
            key = (sample.feedback_type, sample.embedding_digest)
            existing = existing_by_key.get(key)
            if existing is None:
                sample.person = target_person
                sample.person_id = target_person.id
                existing_by_key[key] = sample
                continue
            if not existing.is_active and sample.is_active:
                existing.is_active = True
            if existing.source_face_id is None:
                existing.source_face_id = sample.source_face_id
            if existing.source_logical_asset_id is None:
                existing.source_logical_asset_id = sample.source_logical_asset_id
            db.delete(sample)

    def _clear_feedback_for_face(self, db: Session, face_id: int) -> None:
        db.execute(
            update(FaceTrainingSample)
            .where(FaceTrainingSample.source_face_id == face_id, FaceTrainingSample.is_active.is_(True))
            .values(is_active=False)
        )

    def _record_feedback_from_face(
        self,
        db: Session,
        *,
        face: Face,
        person_id: int,
        feedback_type: str,
    ) -> None:
        embedding = self._embedding(face)
        if embedding is None:
            return
        self._upsert_training_sample(
            db,
            person_id=person_id,
            feedback_type=feedback_type,
            embedding=embedding,
            source_face_id=face.id,
            source_logical_asset_id=face.logical_asset_id,
        )

    def _upsert_training_sample(
        self,
        db: Session,
        *,
        person_id: int,
        feedback_type: str,
        embedding: np.ndarray,
        source_face_id: int | None,
        source_logical_asset_id: int | None,
    ) -> None:
        digest = self._embedding_digest(embedding)
        sample = db.execute(
            select(FaceTrainingSample).where(
                FaceTrainingSample.person_id == person_id,
                FaceTrainingSample.feedback_type == feedback_type,
                FaceTrainingSample.embedding_digest == digest,
            )
        ).scalar_one_or_none()
        if sample is None:
            db.add(
                FaceTrainingSample(
                    person_id=person_id,
                    source_face_id=source_face_id,
                    source_logical_asset_id=source_logical_asset_id,
                    feedback_type=feedback_type,
                    embedding_json=embedding.tolist(),
                    embedding_digest=digest,
                    is_active=True,
                )
            )
            return

        sample.source_face_id = source_face_id
        sample.source_logical_asset_id = source_logical_asset_id
        sample.embedding_json = embedding.tolist()
        sample.is_active = True

    def _embedding_digest(self, embedding: np.ndarray) -> str:
        stable_vector = np.round(embedding.astype(np.float32), 6)
        return hashlib.sha256(stable_vector.tobytes()).hexdigest()

    def _face_feedback_key(self, logical_asset_id: int, embedding: np.ndarray) -> tuple[int, str]:
        return logical_asset_id, self._embedding_digest(embedding)

    def _upsert_review_feedback(
        self,
        db: Session,
        *,
        person_id: int,
        face: Face,
        decision: str,
        suggested_score: float | None,
    ) -> None:
        embedding = self._embedding(face)
        if embedding is None:
            return
        logical_asset_id, embedding_digest = self._face_feedback_key(face.logical_asset_id, embedding)
        review_feedback = db.execute(
            select(FaceReviewFeedback).where(
                FaceReviewFeedback.person_id == person_id,
                FaceReviewFeedback.logical_asset_id == logical_asset_id,
                FaceReviewFeedback.embedding_digest == embedding_digest,
            )
        ).scalar_one_or_none()
        if review_feedback is None:
            db.add(
                FaceReviewFeedback(
                    person_id=person_id,
                    logical_asset_id=logical_asset_id,
                    source_face_id=face.id,
                    decision=decision,
                    suggested_score=suggested_score,
                    embedding_digest=embedding_digest,
                    review_count=1,
                )
            )
            return

        review_feedback.source_face_id = face.id
        review_feedback.decision = decision
        review_feedback.suggested_score = suggested_score
        review_feedback.review_count += 1

    def _should_suppress_review_candidate(self, feedback: FaceReviewFeedback, current_score: float) -> bool:
        if feedback.decision in {self.REVIEW_CONFIRM, self.REVIEW_REJECT}:
            return True
        if feedback.decision == self.REVIEW_SKIP:
            previous_score = feedback.suggested_score or 0.0
            return current_score <= previous_score + self.settings.face_review_revisit_margin
        return False

    def _is_higher_priority_review_candidate(
        self,
        candidate: dict[str, object],
        existing: dict[str, object],
    ) -> bool:
        candidate_key = (
            float(candidate["review_priority"]),
            float(candidate["decision_score"]),
            float(candidate["ambiguity"]),
            float(candidate["uncertainty"]),
            int(candidate["target_person"].id),
        )
        existing_key = (
            float(existing["review_priority"]),
            float(existing["decision_score"]),
            float(existing["ambiguity"]),
            float(existing["uncertainty"]),
            int(existing["target_person"].id),
        )
        return candidate_key > existing_key

    def _load_assets(self, db: Session, asset_ids: list[int] | None) -> list[LogicalAsset]:
        stmt = (
            select(LogicalAsset)
            .where(LogicalAsset.hero_file_id.is_not(None))
            .options(selectinload(LogicalAsset.hero_file), selectinload(LogicalAsset.physical_files))
            .order_by(LogicalAsset.id)
        )
        if asset_ids:
            stmt = stmt.where(LogicalAsset.id.in_(asset_ids))
        else:
            stmt = stmt.where(
                or_(
                    LogicalAsset.face_scan_status.is_(None),
                    LogicalAsset.face_scan_status != self.FACE_SCAN_STATUS_COMPLETED,
                )
            )
        return db.execute(stmt).scalars().unique().all()

    def _asset_face_scan_signature(self, asset: LogicalAsset) -> str | None:
        hero_file = asset.hero_file
        if hero_file is None:
            return None
        return (
            f"{hero_file.file_path}:{hero_file.checksum or 'missing'}:"
            f"{hero_file.width or 0}x{hero_file.height or 0}:{hero_file.file_type.value}"
        )

    def _load_models(self):
        if cv2 is None:
            raise RuntimeError("opencv-python-headless is required for face detection")

        detector_path = self._ensure_model(
            self.settings.face_detector_model_url,
            "face_detection_yunet_2023mar.onnx",
        )
        recognizer_path = self._ensure_model(
            self.settings.face_recognizer_model_url,
            "face_recognition_sface_2021dec.onnx",
        )

        detector = cv2.FaceDetectorYN.create(
            str(detector_path),
            "",
            (320, 320),
            score_threshold=self.settings.face_detection_score_threshold,
            nms_threshold=0.3,
            top_k=5000,
        )
        recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")
        return detector, recognizer

    def _ensure_model(self, url: str, filename: str) -> Path:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        target = self.models_dir / filename
        if target.exists():
            return target

        temp_target = target.with_suffix(".tmp")
        urllib.request.urlretrieve(url, temp_target)
        temp_target.replace(target)
        return target

    def _reset_asset_faces(self, db: Session, asset_ids: list[int]) -> None:
        if not asset_ids:
            return

        face_ids = db.execute(select(Face.id).where(Face.logical_asset_id.in_(asset_ids))).scalars().all()
        if face_ids:
            db.execute(update(Person).where(Person.cover_face_id.in_(face_ids)).values(cover_face_id=None))
        db.execute(delete(LogicalAssetPerson).where(LogicalAssetPerson.logical_asset_id.in_(asset_ids)))
        db.execute(delete(Face).where(Face.logical_asset_id.in_(asset_ids)))
        db.commit()

    def _extract_asset_faces(self, asset: LogicalAsset, detector, recognizer) -> tuple[list[Face], int]:
        hero_file = asset.hero_file
        if hero_file is None:
            return [], 0

        preview_path = self.preview_service.get_or_create_preview(hero_file)
        image = cv2.imread(str(preview_path))
        if image is None:
            raise RuntimeError(f"Unable to read image preview: {preview_path}")

        height, width = image.shape[:2]
        detector.setInputSize((width, height))
        _, detections = detector.detect(image)
        if detections is None:
            return [], 0

        faces: list[Face] = []
        skipped_blurry_faces = 0
        sorted_detections = sorted(detections.tolist(), key=lambda row: float(row[-1]), reverse=True)
        for index, row in enumerate(sorted_detections):
            face_row = np.asarray(row, dtype=np.float32)
            x, y, w_box, h_box = face_row[:4]
            x1 = max(0.0, float(x))
            y1 = max(0.0, float(y))
            x2 = min(float(width), float(x + w_box))
            y2 = min(float(height), float(y + h_box))
            if x2 - x1 < 24 or y2 - y1 < 24:
                continue

            face_crop = self._crop_face_region(image, bbox=(x1, y1, x2, y2))
            if face_crop.size == 0:
                continue
            blur_score = self._face_blur_score(face_crop)
            if self.settings.face_blur_filter_enabled and blur_score < self.settings.face_blur_score_threshold:
                skipped_blurry_faces += 1
                continue

            aligned = recognizer.alignCrop(image, face_row)
            if aligned is None or aligned.size == 0:
                continue
            feature = recognizer.feature(aligned).reshape(-1).astype(np.float32)
            feature_norm = np.linalg.norm(feature)
            if feature_norm == 0:
                continue
            normalized_feature = (feature / feature_norm).tolist()

            face_preview_path = self._write_face_preview(
                image=image,
                source_path=preview_path,
                face_index=index,
                bbox=(x1, y1, x2, y2),
            )
            faces.append(
                Face(
                    logical_asset_id=asset.id,
                    physical_file_id=hero_file.id,
                    face_index=index,
                    bbox_x1=x1,
                    bbox_y1=y1,
                    bbox_x2=x2,
                    bbox_y2=y2,
                    confidence=float(face_row[-1]),
                    embedding_json=normalized_feature,
                    cluster_id=None,
                    person_id=None,
                    preview_path=str(face_preview_path),
                    assignment_locked=False,
                    is_excluded=False,
                )
            )
            self._face_blur_score_cache[str(face_preview_path)] = blur_score
        return faces, skipped_blurry_faces

    def _write_face_preview(
        self,
        *,
        image,
        source_path: Path,
        face_index: int,
        bbox: tuple[float, float, float, float],
    ) -> Path:
        crop = self._crop_face_region(image, bbox=bbox)
        if crop.size == 0:
            raise RuntimeError("Empty face crop")

        cache_root = Path(self.settings.preview_cache_dir).expanduser() / "faces"
        cache_root.mkdir(parents=True, exist_ok=True)
        source_stat = source_path.stat()
        digest = hashlib.sha256(
            f"{source_path.resolve()}:{source_stat.st_mtime_ns}:{source_stat.st_size}:{face_index}:{bbox}".encode("utf-8")
        ).hexdigest()
        target = cache_root / digest[:2] / f"{digest}.jpg"
        if target.exists():
            return target

        target.parent.mkdir(parents=True, exist_ok=True)
        crop_height, crop_width = crop.shape[:2]
        scale = min(320 / max(crop_height, crop_width), 1.0)
        if scale < 1.0:
            crop = cv2.resize(crop, (int(crop_width * scale), int(crop_height * scale)), interpolation=cv2.INTER_AREA)

        temp_target = target.with_name(f"{target.stem}.tmp.jpg")
        written = cv2.imwrite(str(temp_target), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not written:
            raise RuntimeError("Unable to write face preview")
        temp_target.replace(target)
        return target

    def _crop_face_region(self, image, *, bbox: tuple[float, float, float, float]):
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        padding_x = width * 0.18
        padding_y = height * 0.18
        crop_x1 = int(max(0, x1 - padding_x))
        crop_y1 = int(max(0, y1 - padding_y))
        crop_x2 = int(min(image.shape[1], x2 + padding_x))
        crop_y2 = int(min(image.shape[0], y2 + padding_y))
        return image[crop_y1:crop_y2, crop_x1:crop_x2]

    def _recluster_faces(self, db: Session, similarity_threshold: float | None) -> dict[str, int]:
        threshold = similarity_threshold or self.settings.face_cluster_similarity_threshold
        auto_threshold = max(threshold, self.settings.face_learning_match_threshold)
        people = (
            db.execute(
                select(Person)
                .options(selectinload(Person.faces), selectinload(Person.training_samples))
                .order_by(Person.id)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .unique()
            .all()
        )
        people_by_id = {person.id: person for person in people}
        faces = db.execute(select(Face).order_by(Face.id).execution_options(populate_existing=True)).scalars().all()
        person_profiles = self._build_person_profiles(db, people)

        unnamed_clusters: list[dict[str, object]] = []
        for face in faces:
            if face.is_excluded:
                face.person = None
                face.person_id = None
                face.cluster_id = None
                continue

            embedding = self._embedding(face)
            if embedding is None:
                face.person = None
                face.person_id = None
                face.cluster_id = None
                continue

            if face.assignment_locked:
                if face.person_id is not None:
                    face.cluster_id = f"person:{face.person_id}"
                elif not face.cluster_id:
                    face.cluster_id = f"manual:unassigned:{face.id}"
                continue

            ranked_candidates = self._rank_person_candidates(
                embedding,
                person_profiles,
                min_score=auto_threshold,
            )
            best_candidate = ranked_candidates[0] if ranked_candidates else None
            competitor = ranked_candidates[1] if len(ranked_candidates) > 1 else None
            if best_candidate is not None and self._is_auto_assign_eligible(
                best_candidate,
                competitor,
                auto_threshold=auto_threshold,
            ):
                person_id = int(best_candidate["person_id"])
                face.person = people_by_id.get(person_id)
                face.person_id = person_id
                face.cluster_id = f"person:{person_id}"
                self._update_running_centroid(person_profiles[person_id], embedding)
                continue

            face.person = None
            face.person_id = None
            cluster_match = self._best_cluster_match(embedding, unnamed_clusters, threshold)
            if cluster_match is not None:
                cluster = unnamed_clusters[cluster_match]
                cluster["faces"].append(face)
                self._update_running_centroid(cluster, embedding)
            else:
                unnamed_clusters.append(
                    {
                        "faces": [face],
                        "centroid": embedding,
                        "count": 1,
                    }
                )

        for cluster_index, cluster in enumerate(unnamed_clusters, start=1):
            cluster_id = f"cluster:{cluster_index:04d}"
            for face in cluster["faces"]:
                face.cluster_id = cluster_id

        self._rebuild_people_indexes(db)
        db.commit()
        return {
            "named_people": len(person_profiles),
            "unnamed_clusters": len(unnamed_clusters),
            "total_faces": len(faces),
        }

    def _build_person_profiles(self, db: Session, people: list[Person]) -> dict[int, dict[str, object]]:
        profiles: dict[int, dict[str, object]] = {}
        source_faces = self._load_training_source_faces(db, people)
        for person in people:
            positive_templates = self._build_training_templates(
                [
                    sample
                    for sample in person.training_samples
                    if sample.is_active and sample.feedback_type == self.POSITIVE_FEEDBACK
                ],
                source_faces,
            )
            negative_templates = self._build_training_templates(
                [
                    sample
                    for sample in person.training_samples
                    if sample.is_active and sample.feedback_type == self.NEGATIVE_FEEDBACK
                ],
                source_faces,
            )
            positive_source_face_ids = {
                sample.source_face_id
                for sample in person.training_samples
                if sample.is_active and sample.feedback_type == self.POSITIVE_FEEDBACK and sample.source_face_id is not None
            }
            locked_templates = self._build_face_templates(
                [
                    face
                    for face in person.faces
                    if face.assignment_locked
                    and not face.is_excluded
                    and face.id not in positive_source_face_ids
                    and self._embedding(face) is not None
                ],
                source_kind="face",
            )
            fallback_templates = self._build_face_templates(
                [
                    face
                    for face in person.faces
                    if not face.is_excluded and self._embedding(face) is not None
                ],
                source_kind="face",
            )

            centroid_templates = positive_templates + locked_templates if positive_templates else fallback_templates
            prototype_templates = positive_templates if positive_templates else fallback_templates
            if not centroid_templates or not prototype_templates:
                continue

            centroid = self._weighted_centroid(centroid_templates)
            profiles[person.id] = {
                "centroid": centroid,
                "count": len(centroid_templates),
                "centroid_weight": sum(float(template["weight"]) for template in centroid_templates),
                "prototype_templates": prototype_templates,
                "core_vectors": [
                    template["vector"]
                    for template in prototype_templates
                    if template["tier"] == self.TEMPLATE_TIER_CORE
                ],
                "support_vectors": [
                    template["vector"]
                    for template in prototype_templates
                    if template["tier"] == self.TEMPLATE_TIER_SUPPORT
                ],
                "weak_vectors": [
                    template["vector"]
                    for template in prototype_templates
                    if template["tier"] == self.TEMPLATE_TIER_WEAK
                ],
                "negative_templates": negative_templates,
                "core_count": sum(
                    1 for template in positive_templates if template["tier"] == self.TEMPLATE_TIER_CORE
                ),
                "support_count": sum(
                    1 for template in positive_templates if template["tier"] == self.TEMPLATE_TIER_SUPPORT
                ),
                "weak_count": sum(
                    1 for template in positive_templates if template["tier"] == self.TEMPLATE_TIER_WEAK
                ),
            }
        return profiles

    def _rank_person_candidates(
        self,
        embedding: np.ndarray,
        person_profiles: dict[int, dict[str, object]],
        *,
        min_score: float,
    ) -> list[dict[str, object]]:
        ranked: list[dict[str, object]] = []
        for person_id, profile in person_profiles.items():
            centroid_similarity, prototype_similarity, exemplar_similarity, negative_similarity, decision_score = (
                self._score_person_candidate(embedding, profile)
            )
            if decision_score < min_score:
                continue
            ranked.append(
                {
                    "person_id": person_id,
                    "centroid_similarity": centroid_similarity,
                    "prototype_similarity": prototype_similarity,
                    "exemplar_similarity": exemplar_similarity,
                    "negative_similarity": negative_similarity,
                    "decision_score": decision_score,
                }
            )
        ranked.sort(key=lambda item: (float(item["decision_score"]), float(item["exemplar_similarity"])), reverse=True)
        return ranked

    def _score_person_candidate(
        self,
        embedding: np.ndarray,
        profile: dict[str, object],
    ) -> tuple[float, float, float, float, float | None]:
        centroid_similarity = float(np.dot(embedding, profile["centroid"]))
        core_similarity = self._top_similarity(embedding, profile.get("core_vectors", []))
        support_similarity = self._top_similarity(embedding, profile.get("support_vectors", []))
        weak_similarity = self._top_similarity(embedding, profile.get("weak_vectors", []))
        if core_similarity is None:
            core_similarity = support_similarity if support_similarity is not None else weak_similarity
        if core_similarity is None:
            core_similarity = centroid_similarity
        if support_similarity is None:
            support_similarity = core_similarity
        if weak_similarity is None:
            weak_similarity = support_similarity

        prototype_templates = profile.get("prototype_templates", [])
        prototype_scores = sorted(
            (
                float(np.dot(embedding, template["vector"])) * float(template["weight"])
                for template in prototype_templates
            ),
            reverse=True,
        )
        exemplar_similarity = prototype_scores[0] if prototype_scores else centroid_similarity
        prototype_similarity = (
            float(np.mean(prototype_scores[: min(4, len(prototype_scores))]))
            if prototype_scores
            else centroid_similarity
        )
        support_bonus = min(0.03, np.log1p(int(profile["count"])) * 0.008)
        quality_bonus = min(
            0.04,
            int(profile.get("core_count", 0)) * 0.008 + int(profile.get("support_count", 0)) * 0.004,
        )
        decision_score = min(
            1.0,
            centroid_similarity * 0.42
            + float(core_similarity) * 0.22
            + float(support_similarity) * 0.14
            + prototype_similarity * 0.14
            + exemplar_similarity * 0.08
            + float(weak_similarity) * 0.03
            + support_bonus
            + quality_bonus,
        )
        negative_templates = profile.get("negative_templates", [])
        negative_similarity = None
        if negative_templates:
            negative_similarity = max(
                float(np.dot(embedding, template["vector"])) * float(template["weight"])
                for template in negative_templates
            )
        return centroid_similarity, prototype_similarity, exemplar_similarity, negative_similarity, decision_score

    def _is_auto_assign_eligible(
        self,
        candidate: dict[str, object],
        competitor: dict[str, object] | None,
        *,
        auto_threshold: float,
    ) -> bool:
        if float(candidate["decision_score"]) < auto_threshold:
            return False
        negative_similarity = candidate["negative_similarity"]
        if negative_similarity is not None and float(negative_similarity) >= float(candidate["decision_score"]) - self.settings.face_learning_negative_margin:
            return False
        if competitor is not None and float(competitor["decision_score"]) >= float(candidate["decision_score"]) - self.settings.face_learning_competitor_margin:
            return False
        return True

    def _candidate_uncertainty(self, decision_score: float, *, auto_threshold: float) -> float:
        distance = abs(decision_score - auto_threshold)
        return max(0.0, 1.0 - min(1.0, distance / 0.12))

    def _candidate_ambiguity(self, decision_score: float, competitor_score: float | None) -> float:
        if competitor_score is None:
            return 0.0
        gap = max(0.0, decision_score - competitor_score)
        return max(0.0, 1.0 - min(1.0, gap / 0.12))

    def _candidate_review_priority(
        self,
        *,
        face_confidence: float,
        decision_score: float,
        uncertainty: float,
        ambiguity: float,
        current_person_id: int | None,
        target_person_id: int,
    ) -> float:
        assignment_bonus = 0.08 if current_person_id == target_person_id else 0.0
        return round(
            decision_score * 0.45
            + uncertainty * 0.3
            + ambiguity * 0.18
            + face_confidence * 0.07
            + assignment_bonus,
            6,
        )

    def _rebuild_people_indexes(self, db: Session) -> None:
        db.flush()
        db.execute(delete(LogicalAssetPerson))
        rows = db.execute(
            select(Face.logical_asset_id, Face.person_id, func.count(Face.id))
            .where(Face.person_id.is_not(None), Face.is_excluded.is_(False))
            .group_by(Face.logical_asset_id, Face.person_id)
        ).all()
        for logical_asset_id, person_id, face_count in rows:
            db.add(
                LogicalAssetPerson(
                    logical_asset_id=logical_asset_id,
                    person_id=person_id,
                    face_count=face_count,
                )
            )

        people = (
            db.execute(
                select(Person)
                .options(selectinload(Person.faces))
                .order_by(Person.id)
                .execution_options(populate_existing=True)
            )
            .scalars()
            .unique()
            .all()
        )
        for person in people:
            candidate_faces = [
                face
                for face in person.faces
                if not face.is_excluded and face.preview_path and self._is_face_recognition_usable(face)
            ]
            if not candidate_faces:
                candidate_faces = [face for face in person.faces if not face.is_excluded]
            cover_face = max(candidate_faces, key=lambda face: (face.confidence, -face.id), default=None)
            person.cover_face_id = cover_face.id if cover_face is not None else None
        db.flush()

    def _best_cluster_match(
        self,
        embedding: np.ndarray,
        clusters: list[dict[str, object]],
        threshold: float,
    ) -> int | None:
        best_index: int | None = None
        best_score = -1.0
        for index, cluster in enumerate(clusters):
            score = float(np.dot(embedding, cluster["centroid"]))
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is None or best_score < threshold:
            return None
        return best_index

    def _update_running_centroid(self, cluster: dict[str, object], embedding: np.ndarray) -> None:
        count = int(cluster["count"])
        centroid_weight = float(cluster.get("centroid_weight", count))
        centroid = cluster["centroid"]
        new_sample_weight = 0.58 if "centroid_weight" in cluster else 1.0
        new_centroid = self._normalize(
            (centroid * centroid_weight + embedding * new_sample_weight) / (centroid_weight + new_sample_weight)
        )
        cluster["centroid"] = new_centroid
        cluster["count"] = count + 1
        cluster["centroid_weight"] = centroid_weight + new_sample_weight

    def _embedding(self, face: Face) -> np.ndarray | None:
        if not face.embedding_json:
            return None
        if not self._is_face_recognition_usable(face):
            return None
        vector = np.asarray(face.embedding_json, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return None
        return vector / norm

    def _sample_embedding(self, sample: FaceTrainingSample) -> np.ndarray | None:
        if not sample.embedding_json:
            return None
        vector = np.asarray(sample.embedding_json, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return None
        return vector / norm

    def _normalize(self, vector: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm

    def _load_training_source_faces(self, db: Session, people: list[Person]) -> dict[int, Face]:
        source_face_ids = {
            sample.source_face_id
            for person in people
            for sample in person.training_samples
            if sample.is_active and sample.source_face_id is not None
        }
        if not source_face_ids:
            return {}

        face_by_id = {
            face.id: face
            for person in people
            for face in getattr(person, "faces", [])
        }
        missing_ids = [face_id for face_id in source_face_ids if face_id not in face_by_id]
        if missing_ids:
            extra_faces = db.execute(select(Face).where(Face.id.in_(missing_ids))).scalars().all()
            for face in extra_faces:
                face_by_id[face.id] = face
        return face_by_id

    def _build_training_templates(
        self,
        samples: list[FaceTrainingSample],
        source_faces: dict[int, Face],
    ) -> list[dict[str, object]]:
        templates: list[dict[str, object]] = []
        for sample in samples:
            vector = self._sample_embedding(sample)
            if vector is None:
                continue
            source_face = source_faces.get(sample.source_face_id) if sample.source_face_id is not None else None
            if source_face is not None and not self._is_face_recognition_usable(source_face):
                continue
            quality_score, tier = self._estimate_training_template_quality(
                face=source_face,
                feedback_type=sample.feedback_type,
            )
            templates.append(
                {
                    "vector": vector,
                    "quality_score": quality_score,
                    "tier": tier,
                    "weight": self._template_weight(
                        feedback_type=sample.feedback_type,
                        tier=tier,
                        quality_score=quality_score,
                        source_kind="training",
                    ),
                }
            )
        templates.sort(key=lambda template: (float(template["weight"]), float(template["quality_score"])), reverse=True)
        return templates

    def _build_face_templates(self, faces: list[Face], *, source_kind: str) -> list[dict[str, object]]:
        templates: list[dict[str, object]] = []
        for face in faces:
            vector = self._embedding(face)
            if vector is None:
                continue
            if not self._is_face_recognition_usable(face):
                continue
            quality_score, tier = self._estimate_face_template_quality(face)
            templates.append(
                {
                    "vector": vector,
                    "quality_score": quality_score,
                    "tier": tier,
                    "weight": self._template_weight(
                        feedback_type=self.POSITIVE_FEEDBACK,
                        tier=tier,
                        quality_score=quality_score,
                        source_kind=source_kind,
                    ),
                }
            )
        templates.sort(key=lambda template: (float(template["weight"]), float(template["quality_score"])), reverse=True)
        return templates

    def _estimate_training_template_quality(
        self,
        *,
        face: Face | None,
        feedback_type: str,
    ) -> tuple[float, str]:
        if face is not None:
            return self._estimate_face_template_quality(face)
        return self._fallback_template_quality(feedback_type)

    def _estimate_face_template_quality(self, face: Face) -> tuple[float, str]:
        box_width = max(1.0, float(face.bbox_x2 - face.bbox_x1))
        box_height = max(1.0, float(face.bbox_y2 - face.bbox_y1))
        min_edge = min(box_width, box_height)
        aspect_ratio = min_edge / max(box_width, box_height)
        confidence_score = max(0.0, min(1.0, (float(face.confidence) - 0.72) / 0.26))
        area_score = max(0.0, min(1.0, float(np.sqrt(box_width * box_height)) / 170.0))
        size_score = max(0.0, min(1.0, min_edge / 135.0))
        framing_score = max(0.0, min(1.0, (aspect_ratio - 0.5) / 0.5))
        blur_score = self._face_blur_score_for_face(face)
        blur_quality_score = 1.0
        if self.settings.face_blur_filter_enabled:
            blur_quality_score = max(
                0.0,
                min(1.0, blur_score / max(self.settings.face_blur_score_threshold * 2.0, 1.0)),
            )
        quality_score = round(
            max(
                0.0,
                min(
                    1.0,
                    confidence_score * 0.35
                    + area_score * 0.28
                    + size_score * 0.16
                    + framing_score * 0.06
                    + blur_quality_score * 0.15,
                ),
            ),
            6,
        )
        if quality_score >= 0.72:
            return quality_score, self.TEMPLATE_TIER_CORE
        if quality_score >= 0.48:
            return quality_score, self.TEMPLATE_TIER_SUPPORT
        return quality_score, self.TEMPLATE_TIER_WEAK

    def _fallback_template_quality(self, feedback_type: str) -> tuple[float, str]:
        if feedback_type == self.NEGATIVE_FEEDBACK:
            return 0.62, self.TEMPLATE_TIER_SUPPORT
        return 0.56, self.TEMPLATE_TIER_SUPPORT

    def _template_weight(
        self,
        *,
        feedback_type: str,
        tier: str,
        quality_score: float,
        source_kind: str,
    ) -> float:
        if feedback_type == self.NEGATIVE_FEEDBACK:
            base_by_tier = {
                self.TEMPLATE_TIER_CORE: 1.0,
                self.TEMPLATE_TIER_SUPPORT: 0.86,
                self.TEMPLATE_TIER_WEAK: 0.7,
            }
        else:
            base_by_tier = {
                self.TEMPLATE_TIER_CORE: 1.0,
                self.TEMPLATE_TIER_SUPPORT: 0.72,
                self.TEMPLATE_TIER_WEAK: 0.38,
            }
        source_multiplier = 1.0 if source_kind == "training" else 0.82
        return round(base_by_tier.get(tier, 0.5) * source_multiplier * (0.85 + quality_score * 0.15), 6)

    def _weighted_centroid(self, templates: list[dict[str, object]]) -> np.ndarray:
        weighted_sum = np.zeros_like(templates[0]["vector"], dtype=np.float32)
        total_weight = 0.0
        for template in templates:
            weight = float(template["weight"])
            weighted_sum += template["vector"] * weight
            total_weight += weight
        if total_weight == 0:
            return self._normalize(weighted_sum)
        return self._normalize(weighted_sum / total_weight)

    def _top_similarity(self, embedding: np.ndarray, vectors: list[np.ndarray]) -> float | None:
        if not vectors:
            return None
        return max(float(np.dot(embedding, vector)) for vector in vectors)

    def _is_face_recognition_usable(self, face: Face) -> bool:
        if not self.settings.face_blur_filter_enabled:
            return True
        return self._face_blur_score_for_face(face) >= self.settings.face_blur_score_threshold

    def _face_blur_score_for_face(self, face: Face) -> float:
        preview_path = face.preview_path
        if not preview_path:
            return self.settings.face_blur_score_threshold

        cached = self._face_blur_score_cache.get(preview_path)
        if cached is not None:
            return cached

        preview_image = cv2.imread(preview_path) if cv2 is not None else None
        if preview_image is None:
            return self.settings.face_blur_score_threshold

        score = self._face_blur_score(preview_image)
        self._face_blur_score_cache[preview_path] = score
        return score

    def _face_blur_score(self, image) -> float:
        if cv2 is None or image is None or getattr(image, "size", 0) == 0:
            return 0.0

        if len(image.shape) == 3:
            grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            grayscale = image

        resized = cv2.resize(
            grayscale,
            (112, 112),
            interpolation=cv2.INTER_AREA
            if grayscale.shape[0] > 112 or grayscale.shape[1] > 112
            else cv2.INTER_CUBIC,
        )
        laplacian_variance = float(cv2.Laplacian(resized, cv2.CV_32F, ksize=3).var())
        sobel_x = cv2.Sobel(resized, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(resized, cv2.CV_32F, 0, 1, ksize=3)
        gradient_energy = float(np.mean(np.sqrt(sobel_x * sobel_x + sobel_y * sobel_y)))
        return round(laplacian_variance * 0.82 + gradient_energy * 0.35, 6)
