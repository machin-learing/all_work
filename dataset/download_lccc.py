"""
下载 LCCC 中文对话数据集（清华大学 CoAI 课题组）

数据来源: silver/lccc (Hugging Face, 公开访问)
论文: A Large-Scale Chinese Short-Text Conversation Dataset (NLPCC 2020)

从 silver/lccc 直接下载 .jsonl.gz 文件，无需 datasets 库，不依赖旧版加载脚本。
适用于任何 Python 3.x 环境。

版本:
  - LCCC-base: 680 万对话 (train/valid/test)
  - LCCC-large: 1200 万对话 (仅 train)

使用方法:
    python download_lccc.py                         # LCCC-base train, 默认 5000 条
    python download_lccc.py --version large         # LCCC-large
    python download_lccc.py -s valid -n 500         # 验证集 500 条
    python download_lccc.py -s test -n 500          # 测试集 500 条
    python download_lccc.py -o ./data/lccc          # 指定输出目录
    python download_lccc.py -n 0                    # 下载全部
"""

import argparse
import gzip
import json
import os
import ssl
import sys
import tempfile
import shutil

# ── SSL patch ────────────────────────────────────────────────
ssl._create_default_https_context = ssl._create_unverified_context
for v in ["CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"]:
    os.environ.setdefault(v, "")

import requests
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
# ──────────────────────────────────────────────────────────────

# 数据文件 URL（从 loading script 提取）
# silver/lccc 是原始 LCCC 数据的实际托管仓库
_BASE_URL = "https://huggingface.co/datasets/silver/lccc/resolve/main"
_MIRROR_BASE = "https://hf-mirror.com/datasets/silver/lccc/resolve/main"

FILE_MAP = {
    ("base", "train"): "lccc_base_train.jsonl.gz",
    ("base", "valid"):  "lccc_base_valid.jsonl.gz",
    ("base", "test"):   "lccc_base_test.jsonl.gz",
    ("large", "train"): "lccc_large.jsonl.gz",
}

# 预计文件大小
SIZE_HINT = {
    "lccc_base_train.jsonl.gz": "~350 MB",
    "lccc_base_valid.jsonl.gz": "~1 MB",
    "lccc_base_test.jsonl.gz":  "~0.5 MB",
    "lccc_large.jsonl.gz":      "~650 MB",
}


def download(save_dir: str, version: str, split: str, max_samples: int):
    save_dir = os.path.abspath(save_dir)
    os.makedirs(save_dir, exist_ok=True)

    key = (version, split)
    if key not in FILE_MAP:
        valid = [f"{v}/{s}" for (v, s) in FILE_MAP if v == version]
        print(f"错误: LCCC-{version} 没有 '{split}' split")
        print(f"可选: {valid}")
        sys.exit(1)

    filename = FILE_MAP[key]
    urls = [f"{_MIRROR_BASE}/{filename}", f"{_BASE_URL}/{filename}"]
    hint = SIZE_HINT.get(filename, "未知")

    # 缓存原始 .gz 文件
    gz_path = os.path.join(save_dir, filename)

    # ── Step 1: 下载 .jsonl.gz ──
    if not os.path.exists(gz_path):
        print(f"文件: {filename}  ({hint})")
        print(f"下载中...")

        downloaded = False
        for url in urls:
            try:
                print(f"  {url}")
                resp = requests.get(url, verify=False, timeout=(30, 600), stream=True)
                if resp.status_code in (401, 403, 404):
                    print(f"  -> {resp.status_code}, 尝试下一个...")
                    continue
                resp.raise_for_status()

                total = int(resp.headers.get("content-length", 0))
                tmp_path = gz_path + ".tmp"
                with open(tmp_path, "wb") as f:
                    received = 0
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        f.write(chunk)
                        received += len(chunk)
                        if total:
                            mb_done = received / 1024 / 1024
                            mb_total = total / 1024 / 1024
                            print(f"\r  {mb_done:.1f}/{mb_total:.1f} MB ({received/total*100:.0f}%)", end="", flush=True)
                print()
                os.replace(tmp_path, gz_path)
                downloaded = True
                break
            except requests.RequestException as e:
                print(f"  -> 失败: {e}")
                if os.path.exists(tmp_path := gz_path + ".tmp"):
                    os.remove(tmp_path)
                continue

        if not downloaded:
            print("\n下载失败。你可以手动下载后放到:")
            print(f"  {gz_path}")
            sys.exit(1)
    else:
        print(f"文件已缓存: {gz_path}")

    # ── Step 2: 解压 → 解析 → 保存为 JSONL ──
    print(f"\n解压并解析 (上限: {max_samples or '全部'}) ...")

    output_fname = f"lccc_{version}_{split}"
    output_fname += f"_{max_samples}" if max_samples > 0 else "_full"
    output_fname += ".jsonl"
    output_path = os.path.join(save_dir, output_fname)

    count = 0
    with gzip.open(gz_path, "rt", encoding="utf-8") as gz_f:
        with open(output_path, "w", encoding="utf-8") as out_f:
            for i, line in enumerate(gz_f):
                line = line.strip()
                if not line:
                    continue
                # 原始格式: 每行是一个 JSON 数组 ["句1", "句2", ...]
                # 统一包装为 {"dialog": [...]}  方便下游使用
                dialog_list = json.loads(line)
                wrapped = json.dumps({"dialog": dialog_list}, ensure_ascii=False)
                out_f.write(wrapped + "\n")
                count += 1
                if max_samples > 0 and count >= max_samples:
                    break
                if count % 100000 == 0:
                    print(f"  已处理 {count:,} 条...")

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n保存: {output_path}")
    print(f"大小: {size_mb:.1f} MB  |  条数: {count:,}")

    # 预览
    print(f"\n{'─'*50}")
    print("数据预览 (前 3 条)")
    print(f"{'─'*50}")
    with open(output_path, "r", encoding="utf-8") as f:
        for j, line in enumerate(f):
            if j >= 3:
                break
            sample = json.loads(line)
            dialog = sample["dialog"]
            turn_count = len(dialog)
            print(f"\n[{j+1}] {turn_count}轮对话")
            for ti, turn in enumerate(dialog[:4]):  # 只展示前 4 轮
                text = turn[:200]
                suffix = "..." if len(turn) > 200 else ""
                print(f"  [{ti+1}] {text}{suffix}")
            if turn_count > 4:
                print(f"  ... 共 {turn_count} 轮")

    print(f"\n{'─'*50}")
    print("格式: 每行 {\"dialog\": [\"句1\", \"句2\", ...]}")
    print("压缩包已缓存，下次运行直接解压，无需重复下载。")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="下载 LCCC 中文对话数据集")
    parser.add_argument("--version", "-v", choices=["base", "large"], default="base")
    parser.add_argument("--split", "-s", default="train",
                        help="base: train/valid/test; large: 仅 train")
    parser.add_argument("--max-samples", "-n", type=int, default=5000,
                        help="截取条数 (默认 5000, 0=全部)")
    parser.add_argument("--save-dir", "-o", default="./lccc_data")
    args = parser.parse_args()

    print(f"{'='*60}")
    print("LCCC 中文对话数据集下载")
    print(f"  来源: silver/lccc (Hugging Face)")
    print(f"  版本: {args.version}  |  split: {args.split}")
    print(f"  保存: {args.save_dir}")
    print(f"  截取: {'全部' if args.max_samples == 0 else f'{args.max_samples} 条'}")
    print(f"{'='*60}\n")

    download(args.save_dir, args.version, args.split, args.max_samples)
    print("\n下载完成!")


if __name__ == "__main__":
    main()
