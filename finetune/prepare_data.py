"""
将 LLM 改写结果按角色拆分为独立的训练数据。

输入:  dataset/lccc_data/role_rewrite_all.jsonl
输出:  data/boss/train.jsonl val.jsonl test.jsonl
      data/colleague/...
      data/close_friend/...
      data/girlfriend/...
      data/mother/...

每个角色的数据格式: {"input": "中性文本", "output": "角色改写文本"}

使用方法:
    python prepare_data.py
    python prepare_data.py --input ../dataset/lccc_data/role_rewrite_all.jsonl
"""

import argparse
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

ROLES = ["boss", "colleague", "close_friend", "girlfriend", "mother"]


def main():
    parser = argparse.ArgumentParser(description="按角色拆分训练数据")
    parser.add_argument("--input", "-i",
                        default="../dataset/lccc_data/role_rewrite_all.jsonl")
    parser.add_argument("--output-dir", "-o", default="data")
    parser.add_argument("--split", default="8:1:1")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 文件不存在: {input_path}")
        sys.exit(1)

    parts = [int(x) for x in args.split.split(":")]
    total = sum(parts)
    train_r, val_r, test_r = parts[0] / total, parts[1] / total, parts[2] / total

    # 加载
    items = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    # 按角色分组
    role_samples = {r: [] for r in ROLES}
    dropped = 0

    for item in items:
        rewrites = item.get("rewrites", {})
        for role in ROLES:
            val = rewrites.get(role, "")
            if val == "N/A" or not val:
                dropped += 1
                continue
            role_samples[role].append({
                "input": item["neutral"],
                "output": val,
            })

    # 每个角色各自打乱 & 划分
    random.seed(args.seed)
    output_dir = Path(args.output_dir)
    total_samples = 0

    for role in ROLES:
        samples = role_samples[role]
        random.shuffle(samples)
        n = len(samples)
        total_samples += n
        n_train, n_val = int(n * train_r), int(n * val_r)

        splits = {
            "train": samples[:n_train],
            "val": samples[n_train:n_train + n_val],
        }
        if test_r > 0:
            splits["test"] = samples[n_train + n_val:]

        role_dir = output_dir / role
        role_dir.mkdir(parents=True, exist_ok=True)

        for name, data in splits.items():
            path = role_dir / f"{name}.jsonl"
            with open(path, "w", encoding="utf-8") as f:
                for s in data:
                    f.write(json.dumps(s, ensure_ascii=False) + "\n")

        print(f"  {role}: train={len(splits['train'])}, val={len(splits['val'])}, test={len(splits.get('test', []))} → {role_dir}")

    print(f"\n总样本: {total_samples}  |  丢弃 N/A: {dropped}")
    print("完成!")


if __name__ == "__main__":
    main()
