from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.asset import TimestampMixin


class Person(TimestampMixin, Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cover_face_id: Mapped[int | None] = mapped_column(ForeignKey("faces.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    faces: Mapped[list["Face"]] = relationship(
        "Face",
        back_populates="person",
        foreign_keys="Face.person_id",
    )
    cover_face: Mapped["Face | None"] = relationship(
        "Face",
        foreign_keys=[cover_face_id],
        post_update=True,
    )
    asset_links: Mapped[list["LogicalAssetPerson"]] = relationship(
        "LogicalAssetPerson",
        back_populates="person",
        cascade="all, delete-orphan",
    )
    training_samples: Mapped[list["FaceTrainingSample"]] = relationship(
        "FaceTrainingSample",
        back_populates="person",
        cascade="all, delete-orphan",
    )
    review_feedback: Mapped[list["FaceReviewFeedback"]] = relationship(
        "FaceReviewFeedback",
        back_populates="person",
        cascade="all, delete-orphan",
    )


class Face(TimestampMixin, Base):
    __tablename__ = "faces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    logical_asset_id: Mapped[int] = mapped_column(ForeignKey("logical_assets.id"), index=True)
    physical_file_id: Mapped[int] = mapped_column(ForeignKey("physical_files.id"), index=True)
    face_index: Mapped[int] = mapped_column(Integer, default=0)
    bbox_x1: Mapped[float] = mapped_column(Float)
    bbox_y1: Mapped[float] = mapped_column(Float)
    bbox_x2: Mapped[float] = mapped_column(Float)
    bbox_y2: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    embedding_json: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), nullable=True, index=True)
    preview_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    assignment_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False)

    logical_asset: Mapped["LogicalAsset"] = relationship(
        "LogicalAsset",
        back_populates="faces",
        foreign_keys=[logical_asset_id],
    )
    physical_file: Mapped["PhysicalFile"] = relationship(
        "PhysicalFile",
        back_populates="faces",
        foreign_keys=[physical_file_id],
    )
    person: Mapped["Person | None"] = relationship(
        "Person",
        back_populates="faces",
        foreign_keys=[person_id],
    )
    body_reconstructions: Mapped[list["BodyReconstruction"]] = relationship(
        "BodyReconstruction",
        back_populates="face",
        foreign_keys="BodyReconstruction.face_id",
    )


class LogicalAssetPerson(Base):
    __tablename__ = "logical_asset_people"

    logical_asset_id: Mapped[int] = mapped_column(ForeignKey("logical_assets.id"), primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), primary_key=True)
    face_count: Mapped[int] = mapped_column(Integer, default=1)

    logical_asset: Mapped["LogicalAsset"] = relationship(
        "LogicalAsset",
        back_populates="people_links",
        foreign_keys=[logical_asset_id],
    )
    person: Mapped["Person"] = relationship(
        "Person",
        back_populates="asset_links",
        foreign_keys=[person_id],
    )


class FaceTrainingSample(TimestampMixin, Base):
    __tablename__ = "face_training_samples"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "feedback_type",
            "embedding_digest",
            name="uq_face_training_samples_person_feedback_digest",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    source_face_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_logical_asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    feedback_type: Mapped[str] = mapped_column(String(16), index=True)
    embedding_json: Mapped[list[float]] = mapped_column(JSON)
    embedding_digest: Mapped[str] = mapped_column(String(64), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    person: Mapped["Person"] = relationship(
        "Person",
        back_populates="training_samples",
        foreign_keys=[person_id],
    )


class FaceReviewFeedback(TimestampMixin, Base):
    __tablename__ = "face_review_feedback"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "logical_asset_id",
            "embedding_digest",
            name="uq_face_review_feedback_person_asset_digest",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    logical_asset_id: Mapped[int] = mapped_column(Integer, index=True)
    source_face_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    suggested_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedding_digest: Mapped[str] = mapped_column(String(64), index=True)
    review_count: Mapped[int] = mapped_column(Integer, default=1)

    person: Mapped["Person"] = relationship(
        "Person",
        back_populates="review_feedback",
        foreign_keys=[person_id],
    )
