"""
Build one shared role-conditioned LoRA dataset.

Input:
    ../dataset/lccc_data/role_rewrite_filtered.jsonl

Output:
    data/train.jsonl
    data/val.jsonl
    data/test.jsonl

Each output sample uses a short instruction format for mT0:
    任务：保持原意，按目标对象改写语气。
    对象：老板
    风格：正式、礼貌、克制
    原句：我今天加班，可能晚点回去
    改写：
"""

import argparse
import json
import random
import sys
from pathlib import Path


ROLE_SPECS = {
    "boss": {
        "name": "老板",
        "style": "正式、礼貌、克制，强调结果和进度",
    },
    "colleague": {
        "name": "同事",
        "style": "平等协作，保留边界感",
    },
    "close_friend": {
        "name": "好朋友",
        "style": "随意、自然、直接",
    },
    "girlfriend": {
        "name": "女朋友",
        "style": "亲密、温柔、在意对方感受",
    },
    "mother": {
        "name": "母亲",
        "style": "尊重、温暖、让长辈放心",
    },
}

ROLES = list(ROLE_SPECS)


def build_model_input(source_text: str, role_code: str) -> str:
    role = ROLE_SPECS[role_code]
    return (
        "任务：保持原意，按目标对象改写语气。\n"
        f"对象：{role['name']}\n"
        f"风格：{role['style']}\n"
        f"原句：{source_text}\n"
        "改写："
    )


def parse_split(split: str) -> tuple[float, float, float]:
    parts = [int(x) for x in split.split(":")]
    if len(parts) != 3 or sum(parts) <= 0:
        raise ValueError("--split must look like 8:1:1")
    total = sum(parts)
    return parts[0] / total, parts[1] / total, parts[2] / total


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one role-conditioned LoRA dataset")
    parser.add_argument(
        "--input",
        "-i",
        default="../dataset/lccc_data/role_rewrite_filtered.jsonl",
        help="Filtered role rewrite JSONL",
    )
    parser.add_argument("--output-dir", "-o", default="data")
    parser.add_argument("--split", default="8:1:1")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file does not exist: {input_path}")
        sys.exit(1)

    train_r, val_r, test_r = parse_split(args.split)

    samples = []
    dropped = 0
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            source_text = item.get("neutral", "").strip()
            rewrites = item.get("rewrites", {})
            if not source_text:
                continue

            for role_code in ROLES:
                rewritten = str(rewrites.get(role_code, "")).strip()
                if not rewritten or rewritten == "N/A":
                    dropped += 1
                    continue
                samples.append(
                    {
                        "role_code": role_code,
                        "role_name": ROLE_SPECS[role_code]["name"],
                        "source": source_text,
                        "input": build_model_input(source_text, role_code),
                        "output": rewritten,
                    }
                )

    random.seed(args.seed)
    random.shuffle(samples)

    n = len(samples)
    n_train = int(n * train_r)
    n_val = int(n * val_r)
    splits = {
        "train": samples[:n_train],
        "val": samples[n_train:n_train + n_val],
    }
    if test_r > 0:
        splits["test"] = samples[n_train + n_val:]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, split_samples in splits.items():
        path = output_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for sample in split_samples:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        print(f"{name}: {len(split_samples)} -> {path}")

    print(f"total samples: {n}")
    print(f"dropped N/A or empty rewrites: {dropped}")


if __name__ == "__main__":
    main()
