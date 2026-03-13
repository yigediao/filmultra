from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from PIL import Image, ImageColor, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.asset import FileType, LogicalAsset, PhysicalFile
from app.models.job import Job, JobStatus, JobType
from app.models.object3d import ObjectReconstruction


class ObjectReconstructionService:
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.project_root = Path(__file__).resolve().parents[3]

    def create_object_job_with_options(
        self,
        db: Session,
        *,
        asset_id: int,
        object_bbox: list[float],
        mask_index: int | None = None,
        preview_id: str | None = None,
        mask_edits: list[dict[str, Any]] | None = None,
    ) -> Job:
        asset = self._load_asset(db, asset_id)
        if asset is None:
            raise ValueError("Asset not found")

        source_file = self._select_source_file(asset)
        if source_file is None:
            raise ValueError("This asset does not have a JPG file for SAM2 / SAM 3D Objects")

        reconstruction = ObjectReconstruction(
            logical_asset_id=asset.id,
            status=self.STATUS_PENDING,
            source_image_path=source_file.file_path,
        )
        db.add(reconstruction)
        db.flush()

        job = Job(
            job_type=JobType.SAM3D_OBJECT,
            status=JobStatus.PENDING,
            payload_json={
                "asset_id": asset.id,
                "object_bbox": object_bbox,
                "mask_index": mask_index,
                "preview_id": preview_id,
                "mask_edits": mask_edits,
                "object_reconstruction_id": reconstruction.id,
            },
        )
        db.add(job)
        db.flush()
        reconstruction.job_id = job.id
        db.commit()
        db.refresh(job)
        return job

    def run_object_job(self, job_id: int) -> None:
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job is None:
                return

            reconstruction_id = int((job.payload_json or {}).get("object_reconstruction_id") or 0)
            reconstruction = db.get(ObjectReconstruction, reconstruction_id) if reconstruction_id else None
            if reconstruction is None:
                raise RuntimeError("Object reconstruction record not found")

            asset = self._load_asset(db, reconstruction.logical_asset_id)
            if asset is None:
                raise RuntimeError("Asset not found")

            source_file = self._select_source_file(asset)
            if source_file is None:
                raise RuntimeError("No JPG source file is available")

            payload = job.payload_json or {}
            object_bbox = payload.get("object_bbox")
            mask_index = payload.get("mask_index")
            preview_id = payload.get("preview_id")
            mask_edits = payload.get("mask_edits")

            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            job.error_message = None
            job.result_json = None
            reconstruction.status = self.STATUS_RUNNING
            reconstruction.error_message = None
            db.commit()

            run_root = self._run_root(reconstruction.id)
            sam2_output_dir = run_root / "sam2"
            sam3d_output_dir = run_root / "sam3d"
            sam2_output_dir.mkdir(parents=True, exist_ok=True)
            sam3d_output_dir.mkdir(parents=True, exist_ok=True)

            reconstruction.sam2_output_dir = str(sam2_output_dir)
            reconstruction.sam3d_output_dir = str(sam3d_output_dir)
            db.commit()

            if preview_id:
                self._materialize_preview_bundle(
                    preview_id=preview_id,
                    output_dir=sam2_output_dir,
                    prompt_bbox=object_bbox,
                    mask_index=mask_index,
                    mask_edits=mask_edits,
                )
            else:
                self._run_sam2(source_file, sam2_output_dir, prompt_bbox=object_bbox, mask_index=mask_index)

            self._run_sam3d_object(sam2_output_dir / "sam2_bundle.npz", sam3d_output_dir)

            sam2_metadata = self._load_json(sam2_output_dir / "metadata.json")
            object_summary = self._load_json(sam3d_output_dir / "sam3d_object_result.json")
            glb_path = sam3d_output_dir / "result.glb"
            ply_path = sam3d_output_dir / "result.ply"

            reconstruction.status = self.STATUS_COMPLETED
            reconstruction.overlay_path = str((sam2_output_dir / "overlay.png").resolve())
            reconstruction.mask_path = str((sam2_output_dir / "mask.png").resolve())
            reconstruction.bundle_path = str((sam2_output_dir / "sam2_bundle.npz").resolve())
            reconstruction.glb_path = str(glb_path.resolve()) if glb_path.exists() else None
            reconstruction.gaussian_ply_path = str(ply_path.resolve()) if ply_path.exists() else None
            reconstruction.result_json = {
                "input": {
                    "object_bbox": object_bbox,
                    "mask_index": mask_index,
                    "preview_id": preview_id,
                    "mask_edit_count": len(mask_edits or []),
                },
                "sam2": sam2_metadata,
                "sam3d_object": object_summary,
            }
            reconstruction.error_message = None

            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.utcnow()
            job.result_json = {
                "object_reconstruction_id": reconstruction.id,
                "asset_id": asset.id,
                "status": self.STATUS_COMPLETED,
                "sam2_mask_index": sam2_metadata.get("chosen_mask_index"),
                "sam2_mask_score": sam2_metadata.get("scores", [None])[sam2_metadata.get("chosen_mask_index", 0)],
                "glb_exists": glb_path.exists(),
                "ply_exists": ply_path.exists(),
                "preview_id": preview_id,
                "mask_edit_count": len(mask_edits or []),
            }
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job_id)
            if job is not None:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)
                job.finished_at = datetime.utcnow()
            reconstruction_id = int((job.payload_json or {}).get("object_reconstruction_id") or 0) if job is not None else 0
            reconstruction = db.get(ObjectReconstruction, reconstruction_id) if reconstruction_id else None
            if reconstruction is not None:
                reconstruction.status = self.STATUS_FAILED
                reconstruction.error_message = str(exc)
            db.commit()
        finally:
            db.close()

    def preview_mask(
        self,
        db: Session,
        *,
        asset_id: int,
        object_bbox: list[float],
        mask_index: int | None = None,
    ) -> dict[str, object]:
        asset = self._load_asset(db, asset_id)
        if asset is None:
            raise ValueError("Asset not found")

        source_file = self._select_source_file(asset)
        if source_file is None:
            raise ValueError("This asset does not have a JPG file for SAM2 / SAM 3D Objects")

        preview_id = uuid4().hex[:12]
        preview_root = self._preview_root(preview_id)
        preview_root.mkdir(parents=True, exist_ok=True)

        self._run_sam2(source_file, preview_root, prompt_bbox=object_bbox, mask_index=mask_index)
        metadata = self._load_json(preview_root / "metadata.json")

        return {
            "preview_id": preview_id,
            "asset_id": asset.id,
            "source_image_url": f"/api/object3d/previews/{preview_id}/files/input_processed.png",
            "prompt_bbox": metadata["prompt_bbox"],
            "image_width": metadata["image_size"]["width"],
            "image_height": metadata["image_size"]["height"],
            "selected_mask_index": metadata["chosen_mask_index"],
            "candidates": [
                {
                    "index": item["index"],
                    "score": item["score"],
                    "overlay_url": f"/api/object3d/previews/{preview_id}/files/{Path(item['overlay_path']).name}",
                    "mask_url": f"/api/object3d/previews/{preview_id}/files/{Path(item['mask_path']).name}",
                }
                for item in metadata.get("mask_candidates", [])
            ],
        }

    def _load_asset(self, db: Session, asset_id: int) -> LogicalAsset | None:
        return (
            db.execute(
                select(LogicalAsset)
                .where(LogicalAsset.id == asset_id)
                .options(
                    selectinload(LogicalAsset.physical_files),
                    selectinload(LogicalAsset.object_reconstructions),
                )
            )
            .scalars()
            .unique()
            .one_or_none()
        )

    def _select_source_file(self, asset: LogicalAsset) -> PhysicalFile | None:
        jpg_files = [file for file in asset.physical_files if file.file_type == FileType.JPG]
        if not jpg_files:
            return None
        return sorted(jpg_files, key=lambda item: (not item.is_hero, item.file_path.lower()))[0]

    def _run_root(self, reconstruction_id: int) -> Path:
        return self._resolve_path(self.settings.sam3d_object_artifacts_dir) / f"run-{reconstruction_id:06d}"

    def _preview_root(self, preview_id: str) -> Path:
        if not preview_id or any(char in preview_id for char in ("/", "\\", "..")):
            raise RuntimeError("Invalid preview id")
        return self._resolve_path(self.settings.sam3d_object_preview_dir) / preview_id

    def _run_sam2(
        self,
        source_file: PhysicalFile,
        output_dir: Path,
        *,
        prompt_bbox: list[float],
        mask_index: int | None = None,
    ) -> None:
        command = [
            str(self._resolve_path(self.settings.sam2_python_bin)),
            str(self._resolve_path(self.settings.sam2_script_path)),
            "--image",
            source_file.file_path,
            "--output-dir",
            str(output_dir),
            "--max-edge",
            str(self.settings.sam2_max_edge),
            "--checkpoint",
            str(self._resolve_path(self.settings.sam2_checkpoint_path)),
            "--model-cfg",
            self.settings.sam2_model_cfg,
            "--bbox",
            ",".join(f"{float(value):.2f}" for value in prompt_bbox),
        ]
        if mask_index is not None:
            command.extend(["--mask-index", str(int(mask_index))])
        self._run_command(command)

    def _materialize_preview_bundle(
        self,
        *,
        preview_id: str,
        output_dir: Path,
        prompt_bbox: list[float] | None,
        mask_index: int | None,
        mask_edits: list[dict[str, Any]] | None,
    ) -> None:
        preview_root = self._preview_root(preview_id)
        metadata_path = preview_root / "metadata.json"
        if not metadata_path.exists():
            raise RuntimeError(f"Preview mask cache not found: {preview_id}")

        metadata = self._load_json(metadata_path)
        processed_image_path = Path(str(metadata["processed_image_path"]))
        if not processed_image_path.exists():
            raise RuntimeError("Preview processed image is not available")

        processed_image = Image.open(processed_image_path).convert("RGB")
        image_width, image_height = processed_image.size
        prompt_bbox_array = self._clamp_bbox(
            np.asarray(prompt_bbox or metadata["prompt_bbox"], dtype=np.float32),
            image_width,
            image_height,
        )
        selected_mask_index = int(mask_index if mask_index is not None else metadata["chosen_mask_index"])
        candidate = next(
            (item for item in metadata.get("mask_candidates", []) if int(item["index"]) == selected_mask_index),
            None,
        )
        if candidate is None:
            raise RuntimeError(f"Preview mask candidate {selected_mask_index} is not available")

        base_mask_path = Path(str(candidate["mask_path"]))
        if not base_mask_path.exists():
            raise RuntimeError("Preview mask file is not available")

        base_mask = (np.array(Image.open(base_mask_path).convert("L")) >= 128).astype(np.uint8)
        final_mask = self._apply_mask_edits(base_mask, mask_edits or [])
        processed_path = output_dir / "input_processed.png"
        mask_path = output_dir / "mask.png"
        overlay_path = output_dir / "overlay.png"
        processed_image.save(processed_path)
        Image.fromarray(final_mask.astype(np.uint8) * 255).save(mask_path)
        self._draw_overlay(processed_image, final_mask, prompt_bbox_array).save(overlay_path)

        final_metadata = {
            **metadata,
            "processed_image_path": str(processed_path.resolve()),
            "prompt_bbox": prompt_bbox_array.tolist(),
            "face_bbox": None,
            "mask_path": str(mask_path.resolve()),
            "overlay_path": str(overlay_path.resolve()),
            "chosen_mask_index": selected_mask_index,
            "mask_edit_count": len(mask_edits or []),
            "mask_edit_applied": bool(mask_edits),
            "preview_id": preview_id,
        }
        (output_dir / "metadata.json").write_text(
            json.dumps(final_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._save_bundle(output_dir, final_metadata, np.array(processed_image.convert("RGB")), final_mask)

    def _run_sam3d_object(self, bundle_path: Path, output_dir: Path) -> None:
        command = [
            str(self._resolve_path(self.settings.sam3d_object_python_bin)),
            str(self._resolve_path(self.settings.sam3d_object_script_path)),
            "--bundle",
            str(bundle_path),
            "--output-dir",
            str(output_dir),
            "--config",
            str(self._resolve_path(self.settings.sam3d_object_pipeline_config_path)),
            "--seed",
            str(self.settings.sam3d_object_seed),
        ]
        if self.settings.sam3d_object_with_texture_baking:
            command.append("--with-texture-baking")
        env = os.environ.copy()
        repo_root = str(self._resolve_path(self.settings.sam3d_object_repo_path))
        pythonpath_entries = [str(Path(repo_root) / "notebook"), repo_root]
        existing_pythonpath = env.get("PYTHONPATH")
        if existing_pythonpath:
            pythonpath_entries.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
        python_bin = self._resolve_path(self.settings.sam3d_object_python_bin)
        conda_prefix = str(python_bin.parent.parent)
        env["CONDA_PREFIX"] = conda_prefix
        env["CUDA_HOME"] = conda_prefix
        env["PATH"] = os.pathsep.join([str(python_bin.parent), env.get("PATH", "")])
        self._run_command(command, env=env)

    def _clamp_bbox(self, bbox: np.ndarray, width: int, height: int) -> np.ndarray:
        x1, y1, x2, y2 = bbox.tolist()
        x1 = min(max(x1, 0.0), float(width - 1))
        y1 = min(max(y1, 0.0), float(height - 1))
        x2 = min(max(x2, x1 + 1), float(width))
        y2 = min(max(y2, y1 + 1), float(height))
        return np.array([x1, y1, x2, y2], dtype=np.float32)

    def _apply_mask_edits(self, base_mask: np.ndarray, mask_edits: list[dict[str, Any]]) -> np.ndarray:
        if not mask_edits:
            return base_mask.astype(np.uint8)

        mask_image = Image.fromarray((base_mask.astype(np.uint8) * 255), mode="L")
        drawer = ImageDraw.Draw(mask_image)
        width, height = mask_image.size

        for stroke in mask_edits:
            points = stroke.get("points") or []
            if not points:
                continue
            radius = max(1, int(round(float(stroke.get("radius") or 1.0))))
            fill = 255 if stroke.get("mode") == "add" else 0
            line_points = [
                (
                    float(max(0.0, min(point["x"], width))),
                    float(max(0.0, min(point["y"], height))),
                )
                for point in points
            ]
            if len(line_points) == 1:
                x, y = line_points[0]
                drawer.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)
                continue
            drawer.line(line_points, fill=fill, width=radius * 2)
            for x, y in line_points:
                drawer.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)

        return (np.array(mask_image) >= 128).astype(np.uint8)

    def _draw_overlay(self, image: Image.Image, mask: np.ndarray, prompt_bbox: np.ndarray) -> Image.Image:
        overlay = image.convert("RGBA")
        mask_image = Image.fromarray(mask.astype(np.uint8) * 255)
        mask_color = Image.new("RGBA", overlay.size, ImageColor.getrgb("#52a3ff") + (110,))
        tinted_mask = Image.composite(mask_color, Image.new("RGBA", overlay.size, (0, 0, 0, 0)), mask_image)
        overlay = Image.alpha_composite(overlay, tinted_mask)
        drawer = ImageDraw.Draw(overlay)
        drawer.rectangle(prompt_bbox.tolist(), outline="#111111", width=5)
        return overlay

    def _save_bundle(
        self,
        output_dir: Path,
        metadata: dict[str, Any],
        image_rgb: np.ndarray,
        mask: np.ndarray,
    ) -> Path:
        bundle_path = output_dir / "sam2_bundle.npz"
        np.savez_compressed(
            bundle_path,
            image_rgb=image_rgb.astype(np.uint8),
            mask=mask.astype(np.uint8),
            prompt_bbox=np.asarray(metadata["prompt_bbox"], dtype=np.float32),
            face_bbox=np.empty((0,), dtype=np.float32),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        return bundle_path

    def _run_command(self, command: list[str], env: dict[str, str] | None = None) -> None:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=env or os.environ.copy(),
            cwd=str(self.project_root),
        )
        if process.returncode == 0:
            return
        raise RuntimeError(
            "\n\n".join(
                part
                for part in [
                    f"command failed with exit code {process.returncode}",
                    " ".join(command),
                    f"stdout:\n{process.stdout.strip()}" if process.stdout.strip() else "",
                    f"stderr:\n{process.stderr.strip()}" if process.stderr.strip() else "",
                ]
                if part
            )
        )

    def _load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()
