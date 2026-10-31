#!/usr/bin/env python3
"""Download the default BC checkpoint from Hugging Face (plan 04b task 1)."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

DEFAULT_REPO = "cameronangliss/vgc-bench-models"
DEFAULT_FILE = "results/saves_bc/seed1/100.zip"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("checkpoints/bc-seed1-100.zip"),
        help="Destination path for the checkpoint zip",
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--file", default=DEFAULT_FILE)
    args = parser.parse_args()
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            "huggingface-hub manquant dans le venv engine-runtime.\n"
            "Depuis pokecoach2-python : devbox run engine-setup\n"
            "Puis : devbox run engine-fetch-checkpoint"
        )
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cached = hf_hub_download(repo_id=args.repo, filename=args.file)
    data = Path(cached).read_bytes()
    args.output.write_bytes(data)
    digest = sha256_file(args.output)
    print(f"Wrote {args.output} ({len(data)} bytes)")
    print(f"SHA-256: {digest}")
    print(f"Set VGC_CHECKPOINT_PATH={args.output.resolve()}")
    print(f"Set VGC_CHECKPOINT_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
