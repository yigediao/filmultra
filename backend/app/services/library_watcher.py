from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.job import Job, JobType
from app.services.scanner import JPG_EXTENSIONS, RAW_EXTENSIONS, AssetScannerService


logger = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = JPG_EXTENSIONS | RAW_EXTENSIONS


class LibraryAutoScanWatcher:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._scanner = AssetScannerService()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_snapshot_signatures: dict[str, str] = {}
        self._reported_invalid_roots: set[str] = set()

    def start(self) -> None:
        if not self._settings.auto_scan_enabled:
            logger.info("Library auto scan watcher is disabled")
            return
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="filmultra-library-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def _run_loop(self) -> None:
        try:
            watched_roots = self._discover_roots()
            if self._settings.auto_scan_on_startup:
                for root in watched_roots:
                    self._trigger_scan(root, reason="startup")
            for root in watched_roots:
                self._last_snapshot_signatures[str(root)] = self._build_snapshot_signature(root)
        except Exception:
            logger.exception("Failed to initialize library auto scan watcher")

        while not self._stop_event.wait(self._settings.auto_scan_interval_seconds):
            try:
                watched_roots = self._discover_roots()
                for root in watched_roots:
                    root_key = str(root)
                    current_signature = self._build_snapshot_signature(root)
                    previous_signature = self._last_snapshot_signatures.get(root_key)
                    if previous_signature is None:
                        self._last_snapshot_signatures[root_key] = current_signature
                        continue
                    if current_signature == previous_signature:
                        continue

                    if not self._trigger_scan(root, reason="filesystem_change"):
                        continue

                    self._last_snapshot_signatures[root_key] = current_signature
            except Exception:
                logger.exception("Library auto scan watcher iteration failed")

    def _trigger_scan(self, root: Path, *, reason: str) -> bool:
        db = SessionLocal()
        try:
            job = self._scanner.enqueue_scan_if_idle(db, str(root))
            if job is None:
                logger.info("Skipped auto scan because another scan job is active: %s", root)
                return False

            logger.info("Starting auto scan (%s) for %s via job %s", reason, root, job.id)
            self._scanner.run_scan_job(job.id)
            return True
        finally:
            db.close()

    def _build_snapshot_signature(self, root: Path) -> str:
        digest = hashlib.sha1()
        file_count = 0

        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            try:
                stat = path.stat()
            except FileNotFoundError:
                continue

            file_count += 1
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(str(stat.st_size).encode("utf-8"))
            digest.update(str(stat.st_mtime_ns).encode("utf-8"))

        return f"{file_count}:{digest.hexdigest()}"

    def _discover_roots(self) -> list[Path]:
        root_values = {self._settings.photo_library_root}

        db = SessionLocal()
        try:
            scan_jobs = db.execute(select(Job).where(Job.job_type == JobType.SCAN)).scalars().all()
            for job in scan_jobs:
                root_path = (job.payload_json or {}).get("root_path")
                if isinstance(root_path, str) and root_path.strip():
                    root_values.add(root_path)
        finally:
            db.close()

        roots: list[Path] = []
        for root_value in sorted(root_values):
            root = Path(root_value).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                root_key = str(root)
                if root_key not in self._reported_invalid_roots:
                    logger.warning("Skipping auto scan watcher root because it is invalid: %s", root)
                    self._reported_invalid_roots.add(root_key)
                continue
            self._reported_invalid_roots.discard(str(root))
            roots.append(root)
        return roots
