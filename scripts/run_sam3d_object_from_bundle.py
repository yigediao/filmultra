#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
from hydra.utils import instantiate
from omegaconf import OmegaConf


ROOT = Path(__file__).resolve().parents[1]
SAM3D_OBJECTS_ROOT = ROOT / "third_party" / "sam-3d-objects"

os.environ.setdefault("LIDRA_SKIP_INIT", "true")
sys.path.insert(0, str(SAM3D_OBJECTS_ROOT))


DEFAULT_CONFIG = SAM3D_OBJECTS_ROOT / "checkpoints" / "hf" / "pipeline.yaml"


def load_bundle(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    data = np.load(path, allow_pickle=True)
    image_rgb = data["image_rgb"]
    mask = data["mask"]
    metadata = json.loads(str(data["metadata_json"]))
    return image_rgb, mask, metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run SAM 3D Objects from a normalized SAM2 bundle.",
    )
    parser.add_argument("--bundle", required=True, type=Path, help="Path to sam2_bundle.npz.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for result files.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to the SAM 3D Objects pipeline.yaml checkpoint config.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Inference seed.")
    parser.add_argument(
        "--with-texture-baking",
        action="store_true",
        help="Enable texture baking output instead of the lighter default inference path.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.bundle.exists():
        parser.error(f"bundle does not exist: {args.bundle}")
    if not args.config.exists():
        parser.error(f"config does not exist: {args.config}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    image_rgb, mask, metadata = load_bundle(args.bundle)
    config = OmegaConf.load(args.config)
    config.rendering_engine = "pytorch3d"
    config.compile_model = False
    config.workspace_dir = str(args.config.parent.resolve())
    pipeline = instantiate(config)

    if args.with_texture_baking:
        rgba = np.concatenate([image_rgb[..., :3], (mask.astype(np.uint8) * 255)[..., None]], axis=-1)
        output = pipeline.run(
            rgba,
            None,
            args.seed,
            stage1_only=False,
            with_mesh_postprocess=False,
            with_texture_baking=True,
            with_layout_postprocess=False,
            use_vertex_color=False,
            stage1_inference_steps=None,
            pointmap=None,
        )
    else:
        rgba = np.concatenate([image_rgb[..., :3], (mask.astype(np.uint8) * 255)[..., None]], axis=-1)
        output = pipeline.run(
            rgba,
            None,
            args.seed,
            stage1_only=False,
            with_mesh_postprocess=False,
            with_texture_baking=False,
            with_layout_postprocess=False,
            use_vertex_color=True,
            stage1_inference_steps=None,
            pointmap=None,
        )

    glb_path = args.output_dir / "result.glb"
    ply_path = args.output_dir / "result.ply"
    if output.get("glb") is not None:
        output["glb"].export(glb_path)
    if output.get("gs") is not None:
        output["gs"].save_ply(ply_path)

    summary = {
        "status": "completed",
        "seed": args.seed,
        "with_texture_baking": bool(args.with_texture_baking),
        "glb_exists": glb_path.exists(),
        "ply_exists": ply_path.exists(),
        "bundle_metadata": metadata,
        "output_keys": sorted(output.keys()),
    }
    (args.output_dir / "sam3d_object_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
