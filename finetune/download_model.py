"""
Download the default base model for LoRA fine-tuning.

Default:
    bigscience/mt0-large -> ./models/mt0-large

Usage:
    pip install modelscope
    python download_model.py

Override:
    python download_model.py --model-id bigscience/mt0-large --save-dir ./models/mt0-large
"""

import argparse
import shutil
from pathlib import Path


DEFAULT_MODEL_ID = "bigscience/mt0-large"
DEFAULT_SAVE_DIR = Path("./models/mt0-large")
IGNORE_PATTERNS = [
    "tf_model*",
    "flax_model*",
    "onnx/*",
    "*.onnx",
    "*.onnx_data",
    "model.safetensors",
]


def download(model_id: str, save_dir: Path, force: bool = False) -> None:
    if save_dir.exists() and list(save_dir.glob("*.json")) and not force:
        print(f"model already exists: {save_dir}  (use --force to re-download)")
        return

    from modelscope import snapshot_download

    save_dir.mkdir(parents=True, exist_ok=True)

    print(f"downloading {model_id} ...")
    tmp = snapshot_download(
        model_id,
        cache_dir="./.model_tmp",
        ignore_file_pattern=IGNORE_PATTERNS,
    )

    for src in Path(tmp).iterdir():
        dst = save_dir / src.name
        if src.is_dir():
            if dst.exists():
                continue
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

    shutil.rmtree("./.model_tmp", ignore_errors=True)
    print(f"done -> {save_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--save-dir", default=str(DEFAULT_SAVE_DIR))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    download(args.model_id, Path(args.save_dir), args.force)


if __name__ == "__main__":
    main()
