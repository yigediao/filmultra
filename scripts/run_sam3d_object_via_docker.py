#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path


ENTRYPOINT_SCRIPT = r"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

os.environ["LIDRA_SKIP_INIT"] = "true"


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--with-texture-baking", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    repo_path = Path(args.repo_path)
    bundle_path = Path(args.bundle)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(repo_path / "notebook"))

    from inference import Inference  # noqa: E402

    data = np.load(bundle_path, allow_pickle=True)
    image = data["image_rgb"]
    mask = data["mask"]
    metadata = json.loads(str(data["metadata_json"]))

    inference = Inference(str(repo_path / "checkpoints" / "hf" / "pipeline.yaml"), compile=False)

    if args.with_texture_baking:
        rgba = np.concatenate([image[..., :3], (mask.astype(np.uint8) * 255)[..., None]], axis=-1)
        output = inference._pipeline.run(
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
        output = inference(image, mask, seed=args.seed)

    glb_path = output_dir / "result.glb"
    ply_path = output_dir / "result.ply"
    if output.get("glb") is not None:
        output["glb"].export(glb_path)
    if output.get("gs") is not None:
        output["gs"].save_ply(ply_path)

    summary = {
        "status": "completed",
        "with_texture_baking": bool(args.with_texture_baking),
        "glb_exists": glb_path.exists(),
        "ply_exists": ply_path.exists(),
        "bundle_metadata": metadata,
        "output_keys": sorted(output.keys()),
    }
    (output_dir / "sam3d_object_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SAM 3D Objects inside a docker container.")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--container-python-bin", required=True)
    parser.add_argument("--container-repo-path", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--with-texture-baking", action="store_true")
    return parser


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(command, text=True, capture_output=True)
    if process.returncode == 0:
        return process
    raise RuntimeError(
        "\n\n".join(
            part
            for part in [
                f"command failed with exit code {process.returncode}",
                " ".join(command),
                f"stdout:\n{process.stdout.strip()}" if process.stdout.strip() else "",
                f"stderr:\n{process.stderr.strip()}" if process.stderr.strip() else "",
            ]
            if part
        )
    )


def main() -> None:
    args = build_parser().parse_args()
    if not args.bundle.exists():
        raise SystemExit(f"bundle does not exist: {args.bundle}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    local_temp_dir = Path(tempfile.mkdtemp(prefix="sam3d-object-runner-"))
    container_workdir = f"/tmp/sam3d-object-{next(tempfile._get_candidate_names())}"
    container_output_dir = f"{container_workdir}/output"

    try:
        entrypoint_path = local_temp_dir / "entry.py"
        entrypoint_path.write_text(ENTRYPOINT_SCRIPT, encoding="utf-8")

        run(["docker", "exec", args.container_name, "mkdir", "-p", container_workdir, container_output_dir])
        run(["docker", "cp", str(args.bundle), f"{args.container_name}:{container_workdir}/bundle.npz"])
        run(["docker", "cp", str(entrypoint_path), f"{args.container_name}:{container_workdir}/entry.py"])

        conda_prefix = str(Path(args.container_python_bin).resolve().parents[1])
        python_command = " ".join(
            [
                shlex.quote(args.container_python_bin),
                shlex.quote(f"{container_workdir}/entry.py"),
                "--repo-path",
                shlex.quote(args.container_repo_path),
                "--bundle",
                shlex.quote(f"{container_workdir}/bundle.npz"),
                "--output-dir",
                shlex.quote(container_output_dir),
                "--seed",
                shlex.quote(str(args.seed)),
                "--with-texture-baking" if args.with_texture_baking else "",
            ]
        ).strip()
        shell_command = "; ".join(
            [
                f"export CONDA_PREFIX={shlex.quote(conda_prefix)}",
                f"export PATH={shlex.quote(conda_prefix + '/bin')}:$PATH",
                python_command,
            ]
        )

        command = [
            "docker",
            "exec",
            args.container_name,
            "bash",
            "-lc",
            shell_command,
        ]
        process = run(command)
        run(["docker", "cp", f"{args.container_name}:{container_output_dir}/.", str(args.output_dir)])
        if process.stdout.strip():
            print(process.stdout.strip())
    finally:
        subprocess.run(["docker", "exec", args.container_name, "rm", "-rf", container_workdir], capture_output=True)
        shutil.rmtree(local_temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
