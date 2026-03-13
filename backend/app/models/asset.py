from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FileType(str, Enum):
    RAW = "RAW"
    JPG = "JPG"
    XMP = "XMP"
    OTHER = "OTHER"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class LogicalAsset(TimestampMixin, Base):
    __tablename__ = "logical_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    capture_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    hero_file_id: Mapped[int | None] = mapped_column(ForeignKey("physical_files.id"), nullable=True)
    capture_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True, index=True)
    camera_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lens_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, default=0)
    pick_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    reject_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    color_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    face_scan_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    face_scan_signature: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    face_scan_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    physical_files: Mapped[list["PhysicalFile"]] = relationship(
        "PhysicalFile",
        back_populates="logical_asset",
        foreign_keys="PhysicalFile.logical_asset_id",
        cascade="all, delete-orphan",
    )
    hero_file: Mapped["PhysicalFile | None"] = relationship(
        "PhysicalFile",
        foreign_keys=[hero_file_id],
        post_update=True,
    )
    faces: Mapped[list["Face"]] = relationship(
        "Face",
        back_populates="logical_asset",
        foreign_keys="Face.logical_asset_id",
        cascade="all, delete-orphan",
    )
    people_links: Mapped[list["LogicalAssetPerson"]] = relationship(
        "LogicalAssetPerson",
        back_populates="logical_asset",
        cascade="all, delete-orphan",
    )
    body_reconstructions: Mapped[list["BodyReconstruction"]] = relationship(
        "BodyReconstruction",
        back_populates="logical_asset",
        cascade="all, delete-orphan",
    )
    object_reconstructions: Mapped[list["ObjectReconstruction"]] = relationship(
        "ObjectReconstruction",
        back_populates="logical_asset",
        cascade="all, delete-orphan",
    )


class PhysicalFile(TimestampMixin, Base):
    __tablename__ = "physical_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    logical_asset_id: Mapped[int] = mapped_column(ForeignKey("logical_assets.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    directory_path: Mapped[str] = mapped_column(String(1024), index=True)
    basename: Mapped[str] = mapped_column(String(255), index=True)
    extension: Mapped[str] = mapped_column(String(32))
    file_type: Mapped[FileType] = mapped_column(SqlEnum(FileType), default=FileType.OTHER, index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capture_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_hero: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    logical_asset: Mapped[LogicalAsset] = relationship(
        "LogicalAsset",
        back_populates="physical_files",
        foreign_keys=[logical_asset_id],
    )
    faces: Mapped[list["Face"]] = relationship(
        "Face",
        back_populates="physical_file",
        foreign_keys="Face.physical_file_id",
        cascade="all, delete-orphan",
    )
