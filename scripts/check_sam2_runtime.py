from __future__ import annotations

import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
SAM2_ROOT = ROOT / "third_party" / "sam2"
sys.path.insert(0, str(SAM2_ROOT))

from sam2.build_sam import build_sam2  # noqa: E402
from sam2.sam2_image_predictor import SAM2ImagePredictor  # noqa: E402


def main() -> None:
    checkpoint = SAM2_ROOT / "checkpoints" / "sam2.1_hiera_large.pt"
    model_cfg = "configs/sam2.1/sam2.1_hiera_l.yaml"

    print("python:", sys.executable)
    print("torch:", torch.__version__, "cuda:", torch.cuda.is_available())
    print("checkpoint_exists:", checkpoint.exists())

    if not checkpoint.exists():
        print("missing checkpoint:", checkpoint)
        return

    predictor = SAM2ImagePredictor(build_sam2(model_cfg, str(checkpoint), device="cuda" if torch.cuda.is_available() else "cpu"))
    print("sam2 predictor ready:", type(predictor).__name__)


if __name__ == "__main__":
    main()
