"""
Train one shared role-conditioned LoRA adapter.

Before training, build the unified dataset:
    python prepare_data.py

Train:
    python train_lora.py
    python train_lora.py --epochs 8 --lr 1e-4 --lora-r 16 --lora-alpha 32

The final adapter is saved to:
    output/final/
"""

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    EarlyStoppingCallback,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    TrainerCallback,
)
from peft import LoraConfig, TaskType, get_peft_model


MODEL_PATH = "./models/mt0-large"
MAX_INPUT_LEN = 256
MAX_OUTPUT_LEN = 128
DATA_DIR = "data"
OUTPUT_DIR = "output"


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
        sample = self.samples[idx]
        model_input = self.tokenizer(
            sample["input"],
            max_length=MAX_INPUT_LEN,
            truncation=True,
            padding=False,
        )
        model_output = self.tokenizer(
            sample["output"],
            max_length=MAX_OUTPUT_LEN,
            truncation=True,
            padding=False,
        )
        return {
            "input_ids": model_input["input_ids"],
            "attention_mask": model_input["attention_mask"],
            "labels": model_output["input_ids"],
        }


class StopOnNanCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        logs = logs or {}
        for key in ("loss", "eval_loss", "grad_norm"):
            value = logs.get(key)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if math.isnan(numeric) or math.isinf(numeric):
                raise FloatingPointError(
                    f"Training stopped because {key} became {value}. "
                    "Try bf16/fp32, lower learning rate, or smaller LoRA rank."
                )


def load_datasets(data_dir: str, tokenizer):
    paths = {
        "train": os.path.join(data_dir, "train.jsonl"),
        "val": os.path.join(data_dir, "val.jsonl"),
        "test": os.path.join(data_dir, "test.jsonl"),
    }
    missing = [path for path in paths.values() if not os.path.exists(path)]
    if missing:
        missing_text = "\n".join(missing)
        raise FileNotFoundError(
            "Unified dataset files are missing. Run `python prepare_data.py` first.\n"
            f"{missing_text}"
        )
    return (
        StyleDataset(paths["train"], tokenizer),
        StyleDataset(paths["val"], tokenizer),
        StyleDataset(paths["test"], tokenizer),
    )


def save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_training_config(path: str, args, dataset_sizes: dict, device: str) -> None:
    precision = get_precision(args.precision, device)
    config = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "command": " ".join(sys.argv),
        "device": device,
        "model_path": args.model_path,
        "data_dir": args.data_dir,
        "output_dir": args.output_dir,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "gradient_accumulation_steps": args.grad_accum_steps,
        "precision": precision,
        "gradient_checkpointing": not args.no_gradient_checkpointing,
        "learning_rate": args.lr,
        "max_input_len": MAX_INPUT_LEN,
        "max_output_len": MAX_OUTPUT_LEN,
        "lora": {
            "r": args.lora_r,
            "alpha": args.lora_alpha,
            "dropout": args.lora_dropout,
            "target_modules": ["q", "v"],
        },
        "dataset_sizes": dataset_sizes,
    }
    save_json(path, config)


def get_precision(requested: str, device: str) -> str:
    if device != "cuda":
        return "fp32"
    if requested != "auto":
        return requested
    if torch.cuda.is_bf16_supported():
        return "bf16"
    return "fp16"


def save_loss_history(output_dir: str, log_history: list[dict]) -> None:
    artifacts_dir = os.path.join(output_dir, "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)
    save_json(os.path.join(artifacts_dir, "train_log_history.json"), log_history)

    csv_path = os.path.join(artifacts_dir, "loss_history.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["step", "epoch", "train_loss", "eval_loss", "learning_rate"])
        writer.writeheader()
        for item in log_history:
            if "loss" not in item and "eval_loss" not in item:
                continue
            writer.writerow(
                {
                    "step": item.get("step", ""),
                    "epoch": item.get("epoch", ""),
                    "train_loss": item.get("loss", ""),
                    "eval_loss": item.get("eval_loss", ""),
                    "learning_rate": item.get("learning_rate", ""),
                }
            )


def plot_loss_curves(output_dir: str, log_history: list[dict]) -> None:
    train_points = [(item.get("step"), item.get("loss")) for item in log_history if "loss" in item]
    eval_points = [(item.get("step"), item.get("eval_loss")) for item in log_history if "eval_loss" in item]
    if not train_points and not eval_points:
        return

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed; skipped loss curve PNG generation.")
        return

    artifacts_dir = os.path.join(output_dir, "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)

    plt.figure(figsize=(8, 5))
    if train_points:
        xs, ys = zip(*train_points)
        plt.plot(xs, ys, label="train loss")
    if eval_points:
        xs, ys = zip(*eval_points)
        plt.plot(xs, ys, label="eval loss")
    plt.xlabel("step")
    plt.ylabel("loss")
    plt.title("LoRA Fine-tuning Train/Eval Loss")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(artifacts_dir, "train_eval_loss_curve.png"), dpi=160)
    plt.close()

    if eval_points:
        xs, ys = zip(*eval_points)
        plt.figure(figsize=(8, 5))
        plt.plot(xs, ys, label="eval loss", color="#d62728")
        plt.xlabel("step")
        plt.ylabel("eval loss")
        plt.title("LoRA Fine-tuning Eval Loss")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(artifacts_dir, "eval_loss_curve.png"), dpi=160)
        plt.close()


def generate_test_predictions(
    output_dir: str,
    model,
    tokenizer,
    test_ds: StyleDataset,
    device: str,
    max_predictions: int,
    num_beams: int,
) -> None:
    predictions_dir = os.path.join(output_dir, "predictions")
    os.makedirs(predictions_dir, exist_ok=True)

    total = len(test_ds) if max_predictions <= 0 else min(max_predictions, len(test_ds))
    jsonl_path = os.path.join(predictions_dir, "test_predictions.jsonl")
    samples_csv_path = os.path.join(predictions_dir, "comparison_samples.csv")

    model.eval()
    rows = []
    with open(jsonl_path, "w", encoding="utf-8") as f, torch.no_grad():
        for i in range(total):
            encoded = test_ds[i]
            raw = test_ds.samples[i]
            input_ids = torch.tensor([encoded["input_ids"]]).to(device)
            attention_mask = torch.tensor([encoded["attention_mask"]]).to(device)
            output_ids = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_length=MAX_OUTPUT_LEN,
                num_beams=num_beams,
            )
            pred = tokenizer.decode(output_ids[0], skip_special_tokens=True)
            record = {
                "index": i,
                "role_code": raw.get("role_code"),
                "role_name": raw.get("role_name"),
                "source": raw.get("source"),
                "input": raw.get("input"),
                "target": raw.get("output"),
                "prediction": pred,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if len(rows) < 30:
                rows.append(record)

    with open(samples_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["index", "role_name", "source", "target", "prediction"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "index": row["index"],
                    "role_name": row["role_name"],
                    "source": row["source"],
                    "target": row["target"],
                    "prediction": row["prediction"],
                }
            )

    print(f"test predictions saved: {jsonl_path}")
    print(f"comparison samples saved: {samples_csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train one role-conditioned LoRA adapter")
    parser.add_argument("--model-path", default=MODEL_PATH)
    parser.add_argument("--data-dir", default=DATA_DIR)
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum-steps", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.1)
    parser.add_argument("--precision", choices=["auto", "bf16", "fp16", "fp32"], default="auto")
    parser.add_argument("--no-gradient-checkpointing", action="store_true")
    parser.add_argument(
        "--max-predictions",
        type=int,
        default=0,
        help="Number of test predictions to save. 0 means the full test set.",
    )
    parser.add_argument("--prediction-beams", type=int, default=4)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}")
    print(f"base model: {args.model_path}")
    print(f"data: {args.data_dir}")
    print(f"LoRA r={args.lora_r} alpha={args.lora_alpha}")
    precision = get_precision(args.precision, device)
    use_bf16 = precision == "bf16"
    use_fp16 = precision == "fp16"
    model_dtype = torch.bfloat16 if use_bf16 else torch.float16 if use_fp16 else torch.float32
    print(f"precision: {precision}")
    print(f"gradient accumulation steps: {args.grad_accum_steps}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    train_ds, val_ds, test_ds = load_datasets(args.data_dir, tokenizer)
    print(f"samples: train={len(train_ds)}, val={len(val_ds)}, test={len(test_ds)}")
    dataset_sizes = {"train": len(train_ds), "val": len(val_ds), "test": len(test_ds)}
    os.makedirs(args.output_dir, exist_ok=True)
    save_training_config(
        os.path.join(args.output_dir, "artifacts", "config.json"),
        args,
        dataset_sizes,
        device,
    )
    with open(os.path.join(args.output_dir, "artifacts", "train_command.txt"), "w", encoding="utf-8") as f:
        f.write(" ".join(sys.argv) + "\n")

    print("loading base model...")
    model = AutoModelForSeq2SeqLM.from_pretrained(
        args.model_path,
        dtype=model_dtype,
    ).to(device)
    if not args.no_gradient_checkpointing:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q", "v"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    training_args = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum_steps,
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
        bf16=use_bf16,
        fp16=use_fp16,
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
        callbacks=[EarlyStoppingCallback(early_stopping_patience=5), StopOnNanCallback()],
    )

    trainer.train()
    save_loss_history(args.output_dir, trainer.state.log_history)
    plot_loss_curves(args.output_dir, trainer.state.log_history)

    final_dir = os.path.join(args.output_dir, "final")
    model.save_pretrained(final_dir)
    tokenizer.save_pretrained(final_dir)
    print(f"adapter saved: {final_dir}")

    best_dir = os.path.join(args.output_dir, "best")
    model.save_pretrained(best_dir)
    tokenizer.save_pretrained(best_dir)
    print(f"best adapter copy saved: {best_dir}")

    metrics = trainer.evaluate(test_ds)
    metrics = {k: float(v) if isinstance(v, (int, float)) else v for k, v in metrics.items()}
    metrics["best_model_checkpoint"] = trainer.state.best_model_checkpoint
    metrics["best_metric"] = trainer.state.best_metric
    save_json(os.path.join(args.output_dir, "artifacts", "test_metrics.json"), metrics)
    print(f"test loss: {metrics.get('eval_loss', 'N/A')}")

    generate_test_predictions(
        args.output_dir,
        model,
        tokenizer,
        test_ds,
        device,
        args.max_predictions,
        args.prediction_beams,
    )

    print("\n--- samples ---")
    model.eval()
    with torch.no_grad():
        for i in range(min(5, len(test_ds))):
            sample = test_ds[i]
            input_ids = torch.tensor([sample["input_ids"]]).to(device)
            attention_mask = torch.tensor([sample["attention_mask"]]).to(device)
            output_ids = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_length=MAX_OUTPUT_LEN,
                num_beams=args.prediction_beams,
            )
            inp = tokenizer.decode(sample["input_ids"], skip_special_tokens=True)
            pred = tokenizer.decode(output_ids[0], skip_special_tokens=True)
            true = tokenizer.decode(sample["labels"], skip_special_tokens=True)
            print(f"input: {inp[:100]}")
            print(f"pred:  {pred}")
            print(f"true:  {true}")
            print()


if __name__ == "__main__":
    main()
