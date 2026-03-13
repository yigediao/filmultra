from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
VAR_ROOT = REPO_ROOT / "var"
RUNTIME_BACKEND_DIR = VAR_ROOT / "runtime" / "backend"
CACHE_BACKEND_DIR = VAR_ROOT / "cache" / "backend"
ARTIFACTS_DIR = VAR_ROOT / "artifacts"


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _home_conda_python(env_name: str) -> str:
    return str(Path.home() / "miniconda3" / "envs" / env_name / "bin" / "python")


class Settings(BaseSettings):
    app_name: str = "FilmUltra API"
    api_prefix: str = "/api"
    database_url: str = _sqlite_url(RUNTIME_BACKEND_DIR / "photo_dam.db")
    photo_library_root: str = "/mnt/photo_library"
    auto_create_tables: bool = True
    preview_cache_dir: str = str(RUNTIME_BACKEND_DIR / "preview_cache")
    preview_max_edge: int = 1600
    preview_jpeg_quality: int = 85
    face_models_dir: str = str(CACHE_BACKEND_DIR / "face-models")
    face_detector_model_url: str = (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
        "face_detection_yunet_2023mar.onnx"
    )
    face_recognizer_model_url: str = (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/"
        "face_recognition_sface_2021dec.onnx"
    )
    face_detection_score_threshold: float = 0.82
    face_cluster_similarity_threshold: float = 0.36
    face_learning_match_threshold: float = 0.42
    face_learning_competitor_margin: float = 0.03
    face_learning_negative_margin: float = 0.02
    face_review_candidate_threshold: float = 0.28
    face_review_revisit_margin: float = 0.05
    face_blur_filter_enabled: bool = True
    face_blur_score_threshold: float = 320.0
    auto_scan_enabled: bool = True
    auto_scan_interval_seconds: int = 15
    auto_scan_on_startup: bool = True
    sam2_python_bin: str = _home_conda_python("sam2-photo")
    sam2_script_path: str = str(REPO_ROOT / "scripts" / "run_sam2_person_mask.py")
    sam2_checkpoint_path: str = str(REPO_ROOT / "third_party" / "sam2" / "checkpoints" / "sam2.1_hiera_large.pt")
    sam2_model_cfg: str = "configs/sam2.1/sam2.1_hiera_l.yaml"
    sam2_max_edge: int = 1600
    sam3d_body_python_bin: str = _home_conda_python("sam3d-body-photo")
    sam3d_body_pythonpath: str = str(REPO_ROOT / "third_party" / "sam-3d-body")
    sam3d_body_script_path: str = str(REPO_ROOT / "scripts" / "run_sam3d_body_from_bundle.py")
    sam3d_body_checkpoint_path: str = str(REPO_ROOT / "checkpoints" / "sam-3d-body" / "model.ckpt")
    sam3d_body_mhr_path: str = str(REPO_ROOT / "checkpoints" / "sam-3d-body" / "assets" / "mhr_model.pt")
    sam3d_artifacts_dir: str = str(ARTIFACTS_DIR / "sam3d-body-runs")
    sam3d_preview_dir: str = str(ARTIFACTS_DIR / "sam3d-body-previews")
    sam3d_object_python_bin: str = _home_conda_python("sam3d-body-photo")
    sam3d_object_repo_path: str = str(REPO_ROOT / "third_party" / "sam-3d-objects")
    sam3d_object_script_path: str = str(REPO_ROOT / "scripts" / "run_sam3d_object_from_bundle.py")
    sam3d_object_pipeline_config_path: str = str(
        REPO_ROOT / "third_party" / "sam-3d-objects" / "checkpoints" / "hf" / "pipeline.yaml"
    )
    sam3d_object_artifacts_dir: str = str(ARTIFACTS_DIR / "sam3d-object-runs")
    sam3d_object_preview_dir: str = str(ARTIFACTS_DIR / "sam3d-object-previews")
    sam3d_object_seed: int = 42
    sam3d_object_with_texture_baking: bool = False

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
