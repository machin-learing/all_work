"""
LoRA 多角色风格迁移训练。

为每个角色独立训练一个 LoRA 适配器:
  output/boss/final/       output/colleague/final/
  output/close_friend/final/  output/girlfriend/final/
  output/mother/final/

使用时加载基座模型 + 对应角色的 LoRA 适配器即可。

使用方法:
    python train_lora.py
    python train_lora.py --epochs 8 --lr 1e-4 --lora-r 16 --lora-alpha 32
"""

import argparse
import json
import os
import sys

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer,
    DataCollatorForSeq2Seq,
    EarlyStoppingCallback,
)
from peft import LoraConfig, get_peft_model, TaskType

# ══════════════════════════════════════════════════════════════
MODEL_PATH = "./models/mt5-large"
MAX_INPUT_LEN = 128
MAX_OUTPUT_LEN = 128
DATA_DIR = "data"
OUTPUT_DIR = "output"
ROLES = ["boss", "colleague", "close_friend", "girlfriend", "mother"]


class StyleDataset(Dataset):
    def __init__(self, path: str, tokenizer):
        self.samples = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.samples.append(json.loads(line))
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        s = self.samples[idx]
        inp = self.tokenizer(s["input"], max_length=MAX_INPUT_LEN, truncation=True, padding=False)
        out = self.tokenizer(s["output"], max_length=MAX_OUTPUT_LEN, truncation=True, padding=False)
        return {
            "input_ids": inp["input_ids"],
            "attention_mask": inp["attention_mask"],
            "labels": out["input_ids"],
        }


def load_role_datasets(role: str, data_dir: str, tokenizer):
    role_dir = os.path.join(data_dir, role)
    paths = {
        "train": os.path.join(role_dir, "train.jsonl"),
        "val":   os.path.join(role_dir, "val.jsonl"),
        "test":  os.path.join(role_dir, "test.jsonl"),
    }
    for name, p in paths.items():
        if not os.path.exists(p):
            print(f"  警告: {role}/{name}.jsonl 不存在, 跳过此角色")
            return None, None, None
    return (
        StyleDataset(paths["train"], tokenizer),
        StyleDataset(paths["val"], tokenizer),
        StyleDataset(paths["test"], tokenizer),
    )


def train_role(role: str, args, tokenizer, device):
    print(f"\n{'='*60}")
    print(f"训练角色: {role}")
    print(f"{'='*60}")

    ds = load_role_datasets(role, args.data_dir, tokenizer)
    if ds[0] is None:
        return
    train_ds, val_ds, test_ds = ds
    print(f"  样本: train={len(train_ds)}, val={len(val_ds)}, test={len(test_ds)}")

    # 每个角色独立加载基座模型 (避免 LoRA 权重污染)
    print(f"  加载基座模型...")
    model = AutoModelForSeq2SeqLM.from_pretrained(
        args.model_path, dtype=torch.float32,
    ).to(device)

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q", "v"],
    )
    model = get_peft_model(model, lora_config)

    role_output = os.path.join(args.output_dir, role)
    training_args = Seq2SeqTrainingArguments(
        output_dir=role_output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        weight_decay=0.01,
        logging_steps=100,
        eval_strategy="steps",
        eval_steps=300,
        save_strategy="steps",
        save_steps=300,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        fp16=False,
        max_grad_norm=1.0,
        report_to="none",
        predict_with_generate=True,
        generation_max_length=MAX_OUTPUT_LEN,
    )

    data_collator = DataCollatorForSeq2Seq(tokenizer, model=model, padding=True)
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=data_collator,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=5)],
    )

    trainer.train()

    # 保存 LoRA 适配器
    final_dir = os.path.join(role_output, "final")
    model.save_pretrained(final_dir)
    print(f"  适配器已保存: {final_dir}")

    # 测试集评估
    metrics = trainer.evaluate(test_ds)
    print(f"  Test loss: {metrics.get('eval_loss', 'N/A')}")

    # 推理样例
    print(f"\n  --- {role} 推理样例 ---")
    model.eval()
    with torch.no_grad():
        for i in range(min(3, len(test_ds))):
            sample = test_ds[i]
            input_ids = torch.tensor([sample["input_ids"]]).to(device)
            attention_mask = torch.tensor([sample["attention_mask"]]).to(device)
            output_ids = model.generate(
                input_ids=input_ids, attention_mask=attention_mask,
                max_length=MAX_OUTPUT_LEN, num_beams=4,
            )
            inp = tokenizer.decode(sample["input_ids"], skip_special_tokens=True)
            pred = tokenizer.decode(output_ids[0], skip_special_tokens=True)
            true = tokenizer.decode(sample["labels"], skip_special_tokens=True)
            print(f"    输入: {inp[:60]}")
            print(f"    预测: {pred}")
            print(f"    真值: {true}")
            print()

    del model  # 释放显存


def main():
    parser = argparse.ArgumentParser(description="LoRA 多角色风格迁移训练")
    parser.add_argument("--model-path", default=MODEL_PATH)
    parser.add_argument("--data-dir", default=DATA_DIR)
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.1)
    parser.add_argument("--roles", default=None,
                        help="要训练的角色, 逗号分隔 (默认全部)")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"设备: {device}")
    print(f"模型: {args.model_path}")
    print(f"数据: {args.data_dir}")
    print(f"LoRA r={args.lora_r} alpha={args.lora_alpha}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_path)

    roles = args.roles.split(",") if args.roles else ROLES
    for role in roles:
        train_role(role, args, tokenizer, device)

    print(f"\n全部完成! 适配器保存在 {args.output_dir}/")
    for role in roles:
        print(f"  {args.output_dir}/{role}/final/")


if __name__ == "__main__":
    main()
