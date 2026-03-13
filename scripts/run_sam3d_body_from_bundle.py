#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SAM3D_BODY_ROOT = ROOT / "third_party" / "sam-3d-body"
sys.path.insert(0, str(SAM3D_BODY_ROOT))

from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body  # noqa: E402


DEFAULT_CHECKPOINT = ROOT / "checkpoints" / "sam-3d-body" / "model.ckpt"
DEFAULT_MHR_PATH = ROOT / "checkpoints" / "sam-3d-body" / "assets" / "mhr_model.pt"


def resolve_device(raw: str) -> str:
    if raw != "auto":
        return raw
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_bundle(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    data = np.load(path, allow_pickle=True)
    image_rgb = data["image_rgb"]
    mask = data["mask"]
    prompt_bbox = data["prompt_bbox"].astype(np.float32).reshape(1, 4)
    metadata = json.loads(str(data["metadata_json"]))
    return image_rgb, mask, prompt_bbox, metadata


def write_obj(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for vertex in vertices:
            handle.write(f"v {vertex[0]} {vertex[1]} {vertex[2]}\n")
        for face in faces:
            handle.write(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run SAM 3D Body from a normalized SAM2 bundle.",
    )
    parser.add_argument("--bundle", required=True, type=Path, help="Path to sam2_bundle.npz.")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for dry-run summary or model outputs.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help="Path to SAM 3D Body model.ckpt.",
    )
    parser.add_argument(
        "--mhr-path",
        type=Path,
        default=DEFAULT_MHR_PATH,
        help="Path to mhr_model.pt.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Inference device.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.bundle.exists():
        parser.error(f"bundle does not exist: {args.bundle}")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    image_rgb, mask, prompt_bbox, bundle_meta = load_bundle(args.bundle)
    height, width = mask.shape[:2]
    dry_run_summary = {
        "bundle_path": str(args.bundle.resolve()),
        "processed_image_path": bundle_meta["processed_image_path"],
        "original_image_path": bundle_meta["original_image_path"],
        "image_size": {"width": int(width), "height": int(height)},
        "prompt_bbox": prompt_bbox.reshape(-1).tolist(),
        "mask_shape": list(mask.shape),
        "mask_foreground_pixels": int(mask.astype(bool).sum()),
        "checkpoint_exists": args.checkpoint.exists(),
        "mhr_exists": args.mhr_path.exists(),
    }

    if not args.checkpoint.exists() or not args.mhr_path.exists():
        dry_run_summary["status"] = "ready_for_sam3d_body_weights"
        summary_path = output_dir / "sam3d_dry_run.json"
        summary_path.write_text(
            json.dumps(dry_run_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps({"summary_path": str(summary_path)}, ensure_ascii=False))
        return

    device = resolve_device(args.device)
    model, model_cfg = load_sam_3d_body(
        str(args.checkpoint),
        device=torch.device(device),
        mhr_path=str(args.mhr_path),
    )
    estimator = SAM3DBodyEstimator(model, model_cfg)

    processed_image_path = output_dir / "input_processed.png"
    Image.fromarray(image_rgb.astype(np.uint8)).save(processed_image_path)

    outputs = estimator.process_one_image(
        image_rgb,
        bboxes=prompt_bbox,
        masks=mask.reshape(1, height, width).astype(np.uint8),
        use_mask=True,
    )

    result_summary = {
        **dry_run_summary,
        "status": "completed",
        "device": device,
        "output_count": len(outputs),
        "mesh_faces_count": int(estimator.faces.shape[0]),
    }

    for index, output in enumerate(outputs):
        prefix = output_dir / f"person_{index:02d}"
        np.save(prefix.with_suffix(".vertices.npy"), output["pred_vertices"])
        np.save(prefix.with_suffix(".keypoints3d.npy"), output["pred_keypoints_3d"])
        np.save(prefix.with_suffix(".cam_t.npy"), output["pred_cam_t"])
        if output.get("mask") is not None:
            Image.fromarray((output["mask"].reshape(height, width) * 255).astype(np.uint8)).save(
                prefix.with_suffix(".mask.png")
            )
        write_obj(prefix.with_suffix(".obj"), output["pred_vertices"], estimator.faces)

    summary_path = output_dir / "sam3d_result.json"
    summary_path.write_text(
        json.dumps(result_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"summary_path": str(summary_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
