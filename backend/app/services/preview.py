from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from app.core.config import get_settings
from app.models.asset import FileType, PhysicalFile

try:
    import rawpy
except ImportError:  # pragma: no cover - optional during bootstrap
    rawpy = None


class PreviewService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.cache_dir = Path(self.settings.preview_cache_dir).expanduser()

    def get_or_create_preview(self, physical_file: PhysicalFile) -> Path:
        source_path = Path(physical_file.file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {source_path}")

        cache_path = self._build_cache_path(source_path)
        if cache_path.exists():
            return cache_path

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        image = self._load_preview_image(source_path, physical_file.file_type)
        temp_path = cache_path.with_suffix(".tmp")
        image.save(
            temp_path,
            format="JPEG",
            quality=self.settings.preview_jpeg_quality,
            optimize=True,
        )
        temp_path.replace(cache_path)
        return cache_path

    def _build_cache_path(self, source_path: Path) -> Path:
        stat = source_path.stat()
        cache_key = hashlib.sha256(
            f"{source_path.resolve()}:{stat.st_mtime_ns}:{stat.st_size}:{self.settings.preview_max_edge}".encode(
                "utf-8"
            )
        ).hexdigest()
        return self.cache_dir / cache_key[:2] / f"{cache_key}.jpg"

    def _load_preview_image(self, source_path: Path, file_type: FileType) -> Image.Image:
        if file_type == FileType.RAW:
            return self._load_raw_preview(source_path)
        return self._load_rgb_image(source_path)

    def _load_rgb_image(self, source_path: Path) -> Image.Image:
        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            image.thumbnail(
                (self.settings.preview_max_edge, self.settings.preview_max_edge),
                Image.Resampling.LANCZOS,
            )
            return image.copy()

    def _load_raw_preview(self, source_path: Path) -> Image.Image:
        if rawpy is None:
            raise RuntimeError("rawpy is required for RAW previews")

        with rawpy.imread(str(source_path)) as raw:
            try:
                thumbnail = raw.extract_thumb()
            except Exception:
                thumbnail = None

            if thumbnail is not None and thumbnail.format == rawpy.ThumbFormat.JPEG:
                with Image.open(BytesIO(thumbnail.data)) as image:
                    image = ImageOps.exif_transpose(image)
                    image = image.convert("RGB")
                    image.thumbnail(
                        (self.settings.preview_max_edge, self.settings.preview_max_edge),
                        Image.Resampling.LANCZOS,
                    )
                    return image.copy()

            if thumbnail is not None and thumbnail.format == rawpy.ThumbFormat.BITMAP:
                image = Image.fromarray(thumbnail.data)
                image = ImageOps.exif_transpose(image)
                image = image.convert("RGB")
                image.thumbnail(
                    (self.settings.preview_max_edge, self.settings.preview_max_edge),
                    Image.Resampling.LANCZOS,
                )
                return image

            rgb = raw.postprocess(use_camera_wb=True, half_size=True)
            image = Image.fromarray(rgb)
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            image.thumbnail(
                (self.settings.preview_max_edge, self.settings.preview_max_edge),
                Image.Resampling.LANCZOS,
            )
            return image
