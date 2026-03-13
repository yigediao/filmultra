from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.asset import FileType, LogicalAsset
from app.models.job import Job, JobStatus, JobType


class MetadataSyncService:
    def sync_rating(self, db: Session, asset: LogicalAsset) -> Job:
        job = Job(
            job_type=JobType.METADATA_SYNC,
            status=JobStatus.RUNNING,
            payload_json={"asset_id": asset.id, "rating": asset.rating},
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        try:
            written_files: list[str] = []
            for physical_file in asset.physical_files:
                self._write_rating(Path(physical_file.file_path), asset.rating, physical_file.file_type)
                written_files.append(physical_file.file_path)

            job.status = JobStatus.COMPLETED
            job.result_json = {"written_files": written_files, "rating": asset.rating}
            job.finished_at = datetime.utcnow()
            db.commit()
            db.refresh(job)
            return job
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.utcnow()
            db.commit()
            db.refresh(job)
            return job

    def _write_rating(self, file_path: Path, rating: int, file_type: FileType) -> None:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_type == FileType.JPG and shutil.which("exiftool"):
            self._write_jpg_with_exiftool(file_path, rating)
            return

        if file_type == FileType.RAW:
            sidecar_path = file_path.with_suffix(".xmp")
        else:
            sidecar_path = Path(f"{file_path}.xmp")

        self._write_xmp_sidecar(sidecar_path, rating)

    def _write_jpg_with_exiftool(self, file_path: Path, rating: int) -> None:
        command = [
            "exiftool",
            "-overwrite_original",
            f"-XMP:Rating={rating}",
            f"-Rating={rating}",
            str(file_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"Failed to write metadata: {file_path}")

    def _write_xmp_sidecar(self, sidecar_path: Path, rating: int) -> None:
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="{rating}" />
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
        sidecar_path.write_text(content, encoding="utf-8")
