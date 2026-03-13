from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.asset import TimestampMixin


class ObjectReconstruction(TimestampMixin, Base):
    __tablename__ = "object_reconstructions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    logical_asset_id: Mapped[int] = mapped_column(ForeignKey("logical_assets.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    source_image_path: Mapped[str] = mapped_column(String(2048))
    sam2_output_dir: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    sam3d_output_dir: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    overlay_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    mask_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    bundle_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    glb_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    gaussian_ply_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    logical_asset: Mapped["LogicalAsset"] = relationship(
        "LogicalAsset",
        back_populates="object_reconstructions",
        foreign_keys=[logical_asset_id],
    )
