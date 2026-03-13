#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageColor, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SAM2_ROOT = ROOT / "third_party" / "sam2"
sys.path.insert(0, str(SAM2_ROOT))

from sam2.build_sam import build_sam2  # noqa: E402
from sam2.sam2_image_predictor import SAM2ImagePredictor  # noqa: E402


DEFAULT_CHECKPOINT = SAM2_ROOT / "checkpoints" / "sam2.1_hiera_large.pt"
DEFAULT_MODEL_CFG = "configs/sam2.1/sam2.1_hiera_l.yaml"


def parse_bbox(raw: str) -> np.ndarray:
    values = [float(part.strip()) for part in raw.split(",")]
    if len(values) != 4:
        raise argparse.ArgumentTypeError("bbox must be x1,y1,x2,y2")
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        raise argparse.ArgumentTypeError("bbox must satisfy x2>x1 and y2>y1")
    return np.array([x1, y1, x2, y2], dtype=np.float32)


def clamp_bbox(bbox: np.ndarray, width: int, height: int) -> np.ndarray:
    x1, y1, x2, y2 = bbox.tolist()
    x1 = min(max(x1, 0.0), float(width - 1))
    y1 = min(max(y1, 0.0), float(height - 1))
    x2 = min(max(x2, x1 + 1), float(width))
    y2 = min(max(y2, y1 + 1), float(height))
    return np.array([x1, y1, x2, y2], dtype=np.float32)


def derive_body_bbox(face_bbox: np.ndarray, width: int, height: int) -> np.ndarray:
    x1, y1, x2, y2 = face_bbox.tolist()
    face_width = x2 - x1
    face_height = y2 - y1
    face_center_x = (x1 + x2) / 2.0

    body_bbox = np.array(
        [
            face_center_x - face_width * 3.0,
            y1 - face_height * 1.4,
            face_center_x + face_width * 3.0,
            y2 + face_height * 8.6,
        ],
        dtype=np.float32,
    )
    return clamp_bbox(body_bbox, width, height)


def resize_image(image: Image.Image, max_edge: int) -> Image.Image:
    width, height = image.size
    longest_edge = max(width, height)
    if longest_edge <= max_edge:
        return image

    scale = max_edge / float(longest_edge)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def draw_overlay(image: Image.Image, mask: np.ndarray, prompt_bbox: np.ndarray) -> Image.Image:
    overlay = image.convert("RGBA")
    mask_image = Image.fromarray(mask.astype(np.uint8) * 255)
    mask_color = Image.new("RGBA", overlay.size, ImageColor.getrgb("#ff8b38") + (110,))
    tinted_mask = Image.composite(mask_color, Image.new("RGBA", overlay.size, (0, 0, 0, 0)), mask_image)
    overlay = Image.alpha_composite(overlay, tinted_mask)

    drawer = ImageDraw.Draw(overlay)
    drawer.rectangle(prompt_bbox.tolist(), outline="#111111", width=5)
    return overlay


def to_numpy_rgb(image: Image.Image) -> np.ndarray:
    return np.array(image.convert("RGB"), copy=True)


def resolve_device(raw: str) -> str:
    if raw != "auto":
        return raw
    return "cuda" if torch.cuda.is_available() else "cpu"


def run_inference(
    predictor: SAM2ImagePredictor,
    image_rgb: np.ndarray,
    prompt_bbox: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if predictor.device.type == "cuda":
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            predictor.set_image(image_rgb)
            masks, scores, _ = predictor.predict(box=prompt_bbox, multimask_output=True)
    else:
        with torch.inference_mode():
            predictor.set_image(image_rgb)
            masks, scores, _ = predictor.predict(box=prompt_bbox, multimask_output=True)
    return masks, scores


def save_bundle(
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
        face_bbox=np.asarray(metadata["face_bbox"], dtype=np.float32)
        if metadata["face_bbox"] is not None
        else np.empty((0,), dtype=np.float32),
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    return bundle_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a single-image SAM2 body mask smoke test.",
    )
    parser.add_argument("--image", required=True, type=Path, help="Path to the input image.")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for processed image, mask, overlay, and bundle.",
    )
    parser.add_argument(
        "--bbox",
        type=parse_bbox,
        help="Prompt bbox in processed-image coordinates: x1,y1,x2,y2.",
    )
    parser.add_argument(
        "--face-bbox",
        type=parse_bbox,
        help="Face bbox in processed-image coordinates. Used to derive a body bbox if --bbox is omitted.",
    )
    parser.add_argument(
        "--max-edge",
        type=int,
        default=1600,
        help="Resize longest image edge to this value before prompting.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help="SAM2 checkpoint path.",
    )
    parser.add_argument(
        "--model-cfg",
        default=DEFAULT_MODEL_CFG,
        help="SAM2 config path relative to the repo.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Inference device.",
    )
    parser.add_argument(
        "--mask-index",
        type=int,
        default=None,
        help="Explicitly select a SAM2 candidate mask index. Defaults to the highest score.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.bbox is None and args.face_bbox is None:
        parser.error("either --bbox or --face-bbox is required")

    if not args.image.exists():
        parser.error(f"image does not exist: {args.image}")
    if not args.checkpoint.exists():
        parser.error(f"SAM2 checkpoint does not exist: {args.checkpoint}")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    image = ImageOps.exif_transpose(Image.open(args.image)).convert("RGB")
    processed_image = resize_image(image, args.max_edge)
    processed_width, processed_height = processed_image.size

    face_bbox = clamp_bbox(args.face_bbox, processed_width, processed_height) if args.face_bbox is not None else None
    prompt_bbox = (
        clamp_bbox(args.bbox, processed_width, processed_height)
        if args.bbox is not None
        else derive_body_bbox(face_bbox, processed_width, processed_height)
    )

    device = resolve_device(args.device)
    predictor = SAM2ImagePredictor(build_sam2(args.model_cfg, str(args.checkpoint), device=device))
    image_rgb = to_numpy_rgb(processed_image)
    masks, scores = run_inference(predictor, image_rgb, prompt_bbox)

    if args.mask_index is not None and (args.mask_index < 0 or args.mask_index >= len(masks)):
        parser.error(f"mask-index must be between 0 and {len(masks) - 1}")

    best_index = args.mask_index if args.mask_index is not None else int(np.argmax(scores))
    best_mask = masks[best_index].astype(bool)
    processed_path = output_dir / "input_processed.png"
    mask_path = output_dir / "mask.png"
    overlay_path = output_dir / "overlay.png"
    metadata_path = output_dir / "metadata.json"

    processed_image.save(processed_path)
    Image.fromarray(best_mask.astype(np.uint8) * 255).save(mask_path)
    draw_overlay(processed_image, best_mask, prompt_bbox).save(overlay_path)

    mask_candidates: list[dict[str, Any]] = []
    for index, candidate_mask in enumerate(masks):
        candidate_mask_bool = candidate_mask.astype(bool)
        candidate_mask_path = output_dir / f"mask_{index:02d}.png"
        candidate_overlay_path = output_dir / f"overlay_{index:02d}.png"
        Image.fromarray(candidate_mask_bool.astype(np.uint8) * 255).save(candidate_mask_path)
        draw_overlay(processed_image, candidate_mask_bool, prompt_bbox).save(candidate_overlay_path)
        mask_candidates.append(
            {
                "index": index,
                "score": float(scores[index]),
                "mask_path": str(candidate_mask_path.resolve()),
                "overlay_path": str(candidate_overlay_path.resolve()),
            }
        )

    metadata = {
        "original_image_path": str(args.image.resolve()),
        "processed_image_path": str(processed_path.resolve()),
        "image_size": {"width": processed_width, "height": processed_height},
        "prompt_bbox": prompt_bbox.tolist(),
        "face_bbox": face_bbox.tolist() if face_bbox is not None else None,
        "mask_path": str(mask_path.resolve()),
        "overlay_path": str(overlay_path.resolve()),
        "scores": [float(score) for score in scores.tolist()],
        "chosen_mask_index": best_index,
        "mask_candidates": mask_candidates,
        "checkpoint": str(args.checkpoint.resolve()),
        "model_cfg": args.model_cfg,
        "device": device,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    bundle_path = save_bundle(output_dir, metadata, image_rgb, best_mask)

    print(json.dumps({"metadata_path": str(metadata_path), "bundle_path": str(bundle_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
