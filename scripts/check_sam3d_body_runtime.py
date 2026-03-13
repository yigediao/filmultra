from __future__ import annotations

import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
SAM3D_BODY_ROOT = ROOT / "third_party" / "sam-3d-body"
sys.path.insert(0, str(SAM3D_BODY_ROOT))

from sam_3d_body import load_sam_3d_body  # noqa: E402


def main() -> None:
    checkpoint = ROOT / "checkpoints" / "sam-3d-body" / "model.ckpt"
    mhr_path = ROOT / "checkpoints" / "sam-3d-body" / "assets" / "mhr_model.pt"

    print("python:", sys.executable)
    print("torch:", torch.__version__, "cuda:", torch.cuda.is_available())
    print("checkpoint_exists:", checkpoint.exists())
    print("mhr_exists:", mhr_path.exists())

    if not checkpoint.exists() or not mhr_path.exists():
        print("missing checkpoints, skip model load")
        return

    model, cfg = load_sam_3d_body(
        str(checkpoint),
        device=torch.device("cuda" if torch.cuda.is_available() else "cpu"),
        mhr_path=str(mhr_path),
    )
    print("sam3d body ready:", type(model).__name__, bool(cfg))


if __name__ == "__main__":
    main()
