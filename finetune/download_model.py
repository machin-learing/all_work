"""
从 ModelScope 下载 mT5-large (国内直连, 无需代理)

pip install modelscope
python download_model.py
"""

import argparse
import shutil
from pathlib import Path

MODEL_ID = "google/mt5-large"
SAVE_DIR = Path("./models/mt5-large")


def download(force=False):
    if SAVE_DIR.exists() and list(SAVE_DIR.glob("*.json")) and not force:
        print("模型已存在, 跳过 (--force 强制重下)")
        return

    from modelscope import snapshot_download

    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"下载 {MODEL_ID} ...")

    tmp = snapshot_download(
        MODEL_ID,
        cache_dir="./.model_tmp",
        ignore_file_pattern=["tf_model*", "flax_model*"],
    )

    for src in Path(tmp).iterdir():
        dst = SAVE_DIR / src.name
        if src.is_dir():
            if not dst.exists():
                shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

    shutil.rmtree("./.model_tmp", ignore_errors=True)
    print(f"完成 → {SAVE_DIR.resolve()}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    download(args.force)


if __name__ == "__main__":
    main()
