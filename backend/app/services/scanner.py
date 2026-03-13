from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import threading

import PIL.ExifTags
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.asset import FileType, LogicalAsset, PhysicalFile
from app.models.job import Job, JobStatus, JobType
from app.models.people import Face

try:
    import exifread
except ImportError:  # pragma: no cover - optional during bootstrap
    exifread = None

try:
    import rawpy
except ImportError:  # pragma: no cover - optional during bootstrap
    rawpy = None


RAW_EXTENSIONS = {
    ".arw",
    ".cr2",
    ".cr3",
    ".dng",
    ".nef",
    ".orf",
    ".raf",
    ".rw2",
}
JPG_EXTENSIONS = {".jpeg", ".jpg"}


@dataclass
class ScannedFile:
    file_path: str
    directory_path: str
    basename: str
    extension: str
    file_type: FileType
    file_size: int
    checksum: str
    capture_time: datetime | None
    width: int | None
    height: int | None
    metadata_json: dict


class AssetScannerService:
    def has_active_scan_job(self, db: Session, root_path: str | None = None) -> bool:
        active_jobs = db.execute(
            select(Job).where(
                Job.job_type == JobType.SCAN,
                Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING)),
            )
        ).scalars().all()
        if root_path is None:
            return len(active_jobs) > 0

        normalized_root = str(Path(root_path).expanduser().resolve())
        return any((job.payload_json or {}).get("root_path") == normalized_root for job in active_jobs)

    def enqueue_scan_if_idle(self, db: Session, root_path: str) -> Job | None:
        if self.has_active_scan_job(db, root_path=root_path):
            return None
        return self.create_scan_job(db, root_path=root_path)

    def create_scan_job(self, db: Session, root_path: str) -> Job:
        root = Path(root_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Scan path does not exist or is not a directory: {root}")

        job = Job(
            job_type=JobType.SCAN,
            status=JobStatus.PENDING,
            payload_json={"root_path": str(root)},
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def run_scan_job(self, job_id: int) -> None:
        db = SessionLocal()
        job = db.get(Job, job_id)
        if job is None:
            db.close()
            return

        try:
            root_value = job.payload_json.get("root_path") if job.payload_json else None
            if not root_value:
                raise FileNotFoundError("Missing root_path in scan job payload")

            root = Path(root_value).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                raise FileNotFoundError(f"Scan path does not exist or is not a directory: {root}")

            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            job.error_message = None
            job.result_json = None
            db.commit()

            scan_result = self._scan_directory(db, root)
            pending_face_asset_ids = scan_result.pop("pending_face_asset_ids", [])
            auto_face_detect_job_id = None
            auto_face_detect_job_status = None
            if pending_face_asset_ids:
                from app.services.faces import FacePipelineService

                face_service = FacePipelineService()
                face_job = face_service.create_face_detect_job(db, asset_ids=pending_face_asset_ids)
                auto_face_detect_job_id = face_job.id
                auto_face_detect_job_status = face_job.status.value
                threading.Thread(
                    target=face_service.run_face_detect_job,
                    args=(face_job.id,),
                    name=f"filmultra-face-detect-{face_job.id}",
                    daemon=True,
                ).start()

            scan_result["pending_face_detection_assets"] = len(pending_face_asset_ids)
            scan_result["auto_face_detect_job_id"] = auto_face_detect_job_id
            scan_result["auto_face_detect_job_status"] = auto_face_detect_job_status
            job.status = JobStatus.COMPLETED
            job.result_json = scan_result
            job.finished_at = datetime.utcnow()
            db.commit()
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def scan(self, db: Session, root_path: str) -> Job:
        job = self.create_scan_job(db, root_path)
        self.run_scan_job(job.id)
        db.refresh(job)
        return job

    def _scan_directory(self, db: Session, root: Path) -> dict:
        scanned_files = self._collect_supported_files(root)
        existing_detected_asset_ids = set(db.execute(select(Face.logical_asset_id).distinct()).scalars().all())
        existing_files = {
            physical_file.file_path: physical_file
            for physical_file in db.execute(select(PhysicalFile)).scalars().all()
        }
        existing_assets = {
            asset.capture_key: asset
            for asset in db.execute(select(LogicalAsset)).scalars().all()
        }

        grouped: dict[str, list[ScannedFile]] = {}
        for scanned_file in scanned_files:
            capture_key = self._build_capture_key(root, Path(scanned_file.file_path))
            grouped.setdefault(capture_key, []).append(scanned_file)

        created_assets = 0
        updated_assets = 0
        created_files = 0
        updated_files = 0
        pending_face_asset_ids: set[int] = set()

        for capture_key, group_files in grouped.items():
            logical_asset = existing_assets.get(capture_key)
            asset_is_new = logical_asset is None
            if logical_asset is None:
                logical_asset = LogicalAsset(
                    capture_key=capture_key,
                    display_name=group_files[0].basename,
                    face_scan_status="pending",
                )
                db.add(logical_asset)
                db.flush()
                existing_assets[capture_key] = logical_asset
                created_assets += 1
            else:
                updated_assets += 1

            hero_source = self._select_hero_file(group_files)
            hero_signature = self._build_face_scan_signature(hero_source)
            logical_asset.display_name = hero_source.basename
            logical_asset.capture_time = self._choose_capture_time(group_files)
            logical_asset.camera_model = self._first_metadata_value(group_files, "camera_model")
            logical_asset.lens_model = self._first_metadata_value(group_files, "lens_model")
            logical_asset.width = hero_source.width
            logical_asset.height = hero_source.height

            for scanned_file in group_files:
                physical_file = existing_files.get(scanned_file.file_path)
                if physical_file is None:
                    physical_file = PhysicalFile(
                        logical_asset_id=logical_asset.id,
                        file_path=scanned_file.file_path,
                        directory_path=scanned_file.directory_path,
                        basename=scanned_file.basename,
                        extension=scanned_file.extension,
                        file_type=scanned_file.file_type,
                        file_size=scanned_file.file_size,
                        checksum=scanned_file.checksum,
                        capture_time=scanned_file.capture_time,
                        width=scanned_file.width,
                        height=scanned_file.height,
                        metadata_json=scanned_file.metadata_json,
                    )
                    db.add(physical_file)
                    db.flush()
                    existing_files[scanned_file.file_path] = physical_file
                    created_files += 1
                else:
                    physical_file.logical_asset_id = logical_asset.id
                    physical_file.directory_path = scanned_file.directory_path
                    physical_file.basename = scanned_file.basename
                    physical_file.extension = scanned_file.extension
                    physical_file.file_type = scanned_file.file_type
                    physical_file.file_size = scanned_file.file_size
                    physical_file.checksum = scanned_file.checksum
                    physical_file.capture_time = scanned_file.capture_time
                    physical_file.width = scanned_file.width
                    physical_file.height = scanned_file.height
                    physical_file.metadata_json = scanned_file.metadata_json
                    updated_files += 1

            asset_files = sorted(
                [existing_files[file.file_path] for file in group_files],
                key=lambda item: (item.file_type != FileType.JPG, item.file_path.lower()),
            )
            for physical_file in asset_files:
                physical_file.is_hero = False
            if asset_files:
                asset_files[0].is_hero = True
                logical_asset.hero_file_id = asset_files[0].id

            if (
                logical_asset.face_scan_status is None
                and logical_asset.id in existing_detected_asset_ids
                and logical_asset.face_scan_signature is None
            ):
                logical_asset.face_scan_status = "completed"
                logical_asset.face_scan_signature = hero_signature
                logical_asset.face_scan_completed_at = logical_asset.updated_at or logical_asset.created_at

            if asset_is_new or logical_asset.face_scan_status != "completed" or logical_asset.face_scan_signature != hero_signature:
                logical_asset.face_scan_status = "pending"
                logical_asset.face_scan_signature = hero_signature
                logical_asset.face_scan_completed_at = None
                pending_face_asset_ids.add(logical_asset.id)

        db.commit()

        total_assets = db.execute(select(func.count()).select_from(LogicalAsset)).scalar_one()
        total_files = db.execute(select(func.count()).select_from(PhysicalFile)).scalar_one()
        return {
            "root_path": str(root),
            "scanned_files": len(scanned_files),
            "created_assets": created_assets,
            "updated_assets": updated_assets,
            "created_files": created_files,
            "updated_files": updated_files,
            "total_assets": total_assets,
            "total_files": total_files,
            "pending_face_asset_ids": sorted(pending_face_asset_ids),
        }

    def _collect_supported_files(self, root: Path) -> list[ScannedFile]:
        files: list[ScannedFile] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue

            file_type = self._classify_file(path.suffix)
            if file_type not in {FileType.RAW, FileType.JPG}:
                continue

            file_stat = path.stat()
            image_metadata = self._extract_image_metadata(path, file_type)
            files.append(
                ScannedFile(
                    file_path=str(path),
                    directory_path=str(path.parent),
                    basename=path.stem,
                    extension=path.suffix.lower(),
                    file_type=file_type,
                    file_size=file_stat.st_size,
                    checksum=f"{file_stat.st_mtime_ns}:{file_stat.st_size}",
                    capture_time=image_metadata["capture_time"],
                    width=image_metadata["width"],
                    height=image_metadata["height"],
                    metadata_json=image_metadata["metadata"],
                )
            )
        return files

    def _classify_file(self, suffix: str) -> FileType:
        suffix = suffix.lower()
        if suffix in RAW_EXTENSIONS:
            return FileType.RAW
        if suffix in JPG_EXTENSIONS:
            return FileType.JPG
        return FileType.OTHER

    def _build_capture_key(self, root: Path, file_path: Path) -> str:
        relative_parent = file_path.parent.relative_to(root)
        return str(relative_parent / file_path.stem).lower()

    def _build_face_scan_signature(self, scanned_file: ScannedFile) -> str:
        return (
            f"{scanned_file.file_path}:{scanned_file.checksum}:"
            f"{scanned_file.width or 0}x{scanned_file.height or 0}:{scanned_file.file_type.value}"
        )

    def _extract_image_metadata(self, path: Path, file_type: FileType) -> dict:
        metadata = self._blank_metadata()
        mtime_capture_time = datetime.fromtimestamp(path.stat().st_mtime)
        capture_time = mtime_capture_time
        width = None
        height = None
        capture_time_source = "mtime"

        if file_type == FileType.JPG:
            self._merge_metadata(metadata, self._extract_exifread_metadata(path))
            try:
                with Image.open(path) as image:
                    width, height = image.size
                    self._merge_metadata(metadata, self._extract_pillow_metadata(image))
            except (OSError, UnidentifiedImageError):
                pass
        elif file_type == FileType.RAW:
            width, height = self._extract_raw_dimensions(path)

        date_value = metadata.get("date_time_original") or metadata.get("date_time_digitized")
        subsec_value = metadata.get("subsec_time_original") or metadata.get("subsec_time_digitized")
        if isinstance(date_value, str):
            capture_time = self._parse_exif_datetime(date_value, str(subsec_value) if subsec_value is not None else None) or capture_time
            if capture_time != mtime_capture_time:
                capture_time_source = "exif"

        metadata["camera_model"] = metadata.get("camera_model") or metadata.get("camera_make")
        metadata["capture_time_source"] = capture_time_source
        metadata["scanned_at"] = datetime.utcnow().isoformat()
        return {
            "capture_time": capture_time,
            "width": width,
            "height": height,
            "metadata": metadata,
        }

    def _parse_exif_datetime(self, value: str, subsec_value: str | None = None) -> datetime | None:
        normalized = value.strip().replace(":", "-", 2)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                if subsec_value:
                    digits = "".join(character for character in subsec_value if character.isdigit())
                    if digits:
                        microsecond = int((digits + "000000")[:6])
                        parsed = parsed.replace(microsecond=microsecond)
                return parsed
            except ValueError:
                continue
        return None

    def _blank_metadata(self) -> dict[str, str | int | None]:
        return {
            "camera_make": None,
            "camera_model": None,
            "lens_model": None,
            "date_time_original": None,
            "date_time_digitized": None,
            "subsec_time_original": None,
            "subsec_time_digitized": None,
            "aperture": None,
            "exposure_time": None,
            "iso": None,
            "focal_length": None,
            "exposure_bias": None,
            "flash": None,
            "metering_mode": None,
            "white_balance": None,
            "exposure_program": None,
            "exposure_mode": None,
            "software": None,
            "lens_serial_number": None,
            "lens_specification": None,
        }

    def _merge_metadata(
        self,
        target: dict[str, str | int | None],
        updates: dict[str, str | int | None],
    ) -> None:
        for key, value in updates.items():
            if value is not None:
                target[key] = value

    def _extract_pillow_metadata(self, image: Image.Image) -> dict[str, str | int | None]:
        metadata = self._blank_metadata()
        exif = image.getexif()
        if not exif:
            return metadata

        tag_map = {
            PIL.ExifTags.TAGS.get(tag, tag): value
            for tag, value in exif.items()
        }
        metadata["camera_make"] = self._stringify_metadata_value(tag_map.get("Make"))
        metadata["camera_model"] = self._stringify_metadata_value(tag_map.get("Model"))
        metadata["lens_model"] = self._stringify_metadata_value(tag_map.get("LensModel"))
        metadata["date_time_original"] = self._stringify_metadata_value(tag_map.get("DateTimeOriginal"))
        metadata["date_time_digitized"] = self._stringify_metadata_value(tag_map.get("DateTimeDigitized") or tag_map.get("DateTime"))
        metadata["subsec_time_original"] = self._stringify_metadata_value(
            tag_map.get("SubsecTimeOriginal") or tag_map.get("SubSecTimeOriginal")
        )
        metadata["subsec_time_digitized"] = self._stringify_metadata_value(
            tag_map.get("SubsecTimeDigitized") or tag_map.get("SubSecTimeDigitized")
        )
        metadata["software"] = self._stringify_metadata_value(tag_map.get("Software"))
        return metadata

    def _extract_exifread_metadata(self, path: Path) -> dict[str, str | int | None]:
        metadata = self._blank_metadata()
        if exifread is None:
            return metadata

        try:
            with path.open("rb") as file_handle:
                tags = exifread.process_file(file_handle, details=False)
        except OSError:
            return metadata

        metadata["camera_make"] = self._tag_value(tags, "Image Make")
        metadata["camera_model"] = self._tag_value(tags, "Image Model")
        metadata["lens_model"] = self._tag_value(tags, "EXIF LensModel")
        metadata["date_time_original"] = self._tag_value(tags, "EXIF DateTimeOriginal")
        metadata["date_time_digitized"] = self._tag_value(tags, "EXIF DateTimeDigitized", "Image DateTime")
        metadata["subsec_time_original"] = self._tag_value(tags, "EXIF SubSecTimeOriginal")
        metadata["subsec_time_digitized"] = self._tag_value(tags, "EXIF SubSecTimeDigitized")
        metadata["aperture"] = self._format_aperture(self._tag_raw_value(tags, "EXIF FNumber"))
        metadata["exposure_time"] = self._tag_value(tags, "EXIF ExposureTime")
        metadata["iso"] = self._tag_int(tags, "EXIF ISOSpeedRatings", "EXIF PhotographicSensitivity")
        metadata["focal_length"] = self._format_focal_length(self._tag_raw_value(tags, "EXIF FocalLength"))
        metadata["exposure_bias"] = self._format_exposure_bias(self._tag_raw_value(tags, "EXIF ExposureBiasValue"))
        metadata["flash"] = self._tag_value(tags, "EXIF Flash")
        metadata["metering_mode"] = self._tag_value(tags, "EXIF MeteringMode")
        metadata["white_balance"] = self._tag_value(tags, "EXIF WhiteBalance")
        metadata["exposure_program"] = self._tag_value(tags, "EXIF ExposureProgram")
        metadata["exposure_mode"] = self._tag_value(tags, "EXIF ExposureMode")
        metadata["software"] = self._tag_value(tags, "Image Software")
        metadata["lens_serial_number"] = self._tag_value(tags, "EXIF LensSerialNumber")
        metadata["lens_specification"] = self._tag_value(tags, "EXIF LensSpecification")
        return metadata

    def _tag_raw_value(self, tags: dict, *names: str):
        for name in names:
            value = tags.get(name)
            if value is not None:
                return value
        return None

    def _tag_value(self, tags: dict, *names: str) -> str | None:
        raw_value = self._tag_raw_value(tags, *names)
        return self._stringify_metadata_value(raw_value)

    def _tag_int(self, tags: dict, *names: str) -> int | None:
        raw_value = self._tag_raw_value(tags, *names)
        string_value = self._stringify_metadata_value(raw_value)
        if string_value is None:
            return None
        try:
            return int(float(string_value))
        except ValueError:
            return None

    def _stringify_metadata_value(self, value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _format_aperture(self, value) -> str | None:
        ratio = self._ratio_to_float(value)
        if ratio is None:
            return self._stringify_metadata_value(value)
        return f"f/{ratio:.1f}"

    def _format_focal_length(self, value) -> str | None:
        ratio = self._ratio_to_float(value)
        if ratio is None:
            return self._stringify_metadata_value(value)
        if abs(ratio - round(ratio)) < 0.05:
            return f"{int(round(ratio))}mm"
        return f"{ratio:.1f}mm"

    def _format_exposure_bias(self, value) -> str | None:
        text = self._stringify_metadata_value(value)
        if text is None:
            return None
        if text.endswith("EV"):
            return text
        return f"{text} EV"

    def _ratio_to_float(self, value) -> float | None:
        if value is None:
            return None
        try:
            if hasattr(value, "values") and value.values:
                ratio = value.values[0]
                return float(ratio.num) / float(ratio.den)
            if hasattr(value, "num") and hasattr(value, "den"):
                return float(value.num) / float(value.den)
            text = str(value).strip()
            if "/" in text:
                numerator, denominator = text.split("/", 1)
                return float(numerator) / float(denominator)
            return float(text)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    def _select_hero_file(self, files: list[ScannedFile]) -> ScannedFile:
        return sorted(
            files,
            key=lambda item: (item.file_type != FileType.JPG, item.file_path.lower()),
        )[0]

    def _extract_raw_dimensions(self, path: Path) -> tuple[int | None, int | None]:
        if rawpy is None:
            return None, None

        try:
            with rawpy.imread(str(path)) as raw:
                sizes = raw.sizes
                width = sizes.crop_width or sizes.width or sizes.iwidth or None
                height = sizes.crop_height or sizes.height or sizes.iheight or None
                return width, height
        except Exception:
            return None, None

    def _choose_capture_time(self, files: list[ScannedFile]) -> datetime | None:
        exif_times = [
            file.capture_time
            for file in files
            if file.capture_time is not None and file.metadata_json.get("capture_time_source") == "exif"
        ]
        if exif_times:
            return min(exif_times)

        capture_times = [file.capture_time for file in files if file.capture_time is not None]
        return min(capture_times) if capture_times else None

    def _first_metadata_value(self, files: list[ScannedFile], key: str) -> str | None:
        for file in files:
            value = file.metadata_json.get(key)
            if value:
                return str(value)
        return None
