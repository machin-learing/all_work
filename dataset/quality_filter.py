"""
Quality check and filter role rewrite data.

Input:
    lccc_data/role_rewrite_all.jsonl

Outputs:
    lccc_data/role_rewrite_filtered.jsonl
    lccc_data/quality_issues.jsonl
    lccc_data/quality_report.json

The filter works at role level: if one role rewrite is problematic, only that
role is replaced with "N/A". The item is dropped only when no role remains.
"""

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path


ROLES = ["boss", "colleague", "close_friend", "girlfriend", "mother"]

TIME_KEYWORDS = [
    "今天",
    "明天",
    "昨天",
    "今晚",
    "明晚",
    "早上",
    "上午",
    "中午",
    "下午",
    "晚上",
    "周末",
    "下周",
    "这周",
    "刚才",
    "马上",
    "一会",
    "晚点",
]

ROLE_TEMPLATE_TERMS = {
    "boss": ["您", "同步", "进度", "安排", "确认", "推进"],
    "colleague": ["咱们", "方便", "辛苦", "有空", "麻烦"],
    "close_friend": ["兄弟", "哈哈", "咱", "一起", "回头"],
    "girlfriend": ["宝贝", "亲爱的", "想你", "别担心", "乖"],
    "mother": ["妈", "别担心", "放心", "照顾自己", "早点休息"],
}

HARD_FAIL_REASONS = {
    "empty",
    "too_short",
    "too_long",
    "length_ratio_high",
    "length_ratio_low",
    "digit_lost",
    "time_keyword_lost",
    "semantic_similarity_low",
    "template_only_rewrite",
}


def load_jsonl(path: Path) -> list[dict]:
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def write_jsonl(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def digit_tokens(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def lcs_len(a: str, b: str) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b, 1):
            if ca == cb:
                cur.append(prev[j - 1] + 1)
            else:
                cur.append(max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


def rouge_l_f1(a: str, b: str) -> float:
    a = normalize_text(a)
    b = normalize_text(b)
    if not a or not b:
        return 0.0
    lcs = lcs_len(a, b)
    precision = lcs / len(b)
    recall = lcs / len(a)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def template_term_hits(role: str, text: str) -> list[str]:
    return [term for term in ROLE_TEMPLATE_TERMS.get(role, []) if term in text]


def check_role_rewrite(
    source: str,
    role: str,
    rewrite: str,
    min_len: int,
    max_len: int,
    min_similarity: float,
    max_similarity: float,
    max_length_ratio: float,
) -> tuple[list[str], dict]:
    source = normalize_text(source)
    rewrite = normalize_text(rewrite)
    reasons = []

    if not rewrite or rewrite == "N/A":
        return ["empty"], {"length": 0, "similarity": 0.0, "length_ratio": 0.0}

    source_len = len(source)
    rewrite_len = len(rewrite)
    similarity = rouge_l_f1(source, rewrite)
    length_ratio = rewrite_len / max(source_len, 1)

    if rewrite_len < min_len:
        reasons.append("too_short")
    if rewrite_len > max_len:
        reasons.append("too_long")
    if length_ratio > max_length_ratio:
        reasons.append("length_ratio_high")
    if length_ratio < 0.35 and source_len >= 12:
        reasons.append("length_ratio_low")

    lost_digits = sorted(digit_tokens(source) - digit_tokens(rewrite))
    if lost_digits:
        reasons.append("digit_lost")

    lost_time_keywords = [kw for kw in TIME_KEYWORDS if kw in source and kw not in rewrite]
    if lost_time_keywords:
        reasons.append("time_keyword_lost")

    if similarity < min_similarity:
        reasons.append("semantic_similarity_low")
    if similarity > max_similarity:
        reasons.append("rewrite_too_similar")

    hits = template_term_hits(role, rewrite)
    non_template_text = rewrite
    for term in hits:
        non_template_text = non_template_text.replace(term, "")
    if hits and rouge_l_f1(source, non_template_text) > 0.90:
        reasons.append("template_only_rewrite")

    return reasons, {
        "length": rewrite_len,
        "similarity": round(similarity, 4),
        "length_ratio": round(length_ratio, 4),
        "template_hits": hits,
        "lost_digits": lost_digits,
        "lost_time_keywords": lost_time_keywords,
    }


def pairwise_role_warnings(rewrites: dict[str, str], threshold: float) -> list[dict]:
    warnings = []
    for i, role_a in enumerate(ROLES):
        text_a = rewrites.get(role_a, "")
        if not text_a or text_a == "N/A":
            continue
        for role_b in ROLES[i + 1:]:
            text_b = rewrites.get(role_b, "")
            if not text_b or text_b == "N/A":
                continue
            similarity = rouge_l_f1(text_a, text_b)
            if similarity >= threshold:
                warnings.append(
                    {
                        "roles": [role_a, role_b],
                        "reason": "role_outputs_too_similar",
                        "similarity": round(similarity, 4),
                    }
                )
    return warnings


def filter_items(args) -> tuple[list[dict], list[dict], dict]:
    input_path = Path(args.input)
    items = load_jsonl(input_path)

    filtered = []
    issues = []
    role_valid = Counter()
    role_invalid = Counter()
    reason_counts = Counter()
    template_counts = {role: Counter() for role in ROLES}
    similarity_by_role = defaultdict(list)
    length_by_role = defaultdict(list)
    dropped_items = 0

    for item in items:
        source = item.get("neutral", "")
        rewrites = dict(item.get("rewrites", {}))
        item_id = item.get("id")
        item_issues = []

        for role in ROLES:
            rewrite = str(rewrites.get(role, "")).strip()
            reasons, metrics = check_role_rewrite(
                source=source,
                role=role,
                rewrite=rewrite,
                min_len=args.min_len,
                max_len=args.max_len,
                min_similarity=args.min_similarity,
                max_similarity=args.max_similarity,
                max_length_ratio=args.max_length_ratio,
            )

            for term in metrics.get("template_hits", []):
                template_counts[role][term] += 1
            if rewrite and rewrite != "N/A":
                similarity_by_role[role].append(metrics["similarity"])
                length_by_role[role].append(metrics["length"])

            hard_reasons = [reason for reason in reasons if reason in HARD_FAIL_REASONS]
            if hard_reasons:
                role_invalid[role] += 1
                reason_counts.update(hard_reasons)
                rewrites[role] = "N/A"
                item_issues.append(
                    {
                        "id": item_id,
                        "role": role,
                        "action": "set_N/A",
                        "reasons": hard_reasons,
                        "all_reasons": reasons,
                        "metrics": metrics,
                        "source": source,
                        "rewrite": rewrite,
                    }
                )
            else:
                role_valid[role] += 1
                soft_reasons = [reason for reason in reasons if reason not in HARD_FAIL_REASONS]
                if soft_reasons:
                    reason_counts.update(soft_reasons)
                    item_issues.append(
                        {
                            "id": item_id,
                            "role": role,
                            "action": "keep_warn",
                            "reasons": soft_reasons,
                            "metrics": metrics,
                            "source": source,
                            "rewrite": rewrite,
                        }
                    )

        diversity_warnings = pairwise_role_warnings(rewrites, args.role_similarity_threshold)
        for warning in diversity_warnings:
            reason_counts[warning["reason"]] += 1
            item_issues.append(
                {
                    "id": item_id,
                    "action": "keep_warn",
                    **warning,
                    "source": source,
                }
            )

        if item_issues:
            issues.extend(item_issues)

        if any(rewrites.get(role) and rewrites.get(role) != "N/A" for role in ROLES):
            new_item = dict(item)
            new_item["rewrites"] = rewrites
            filtered.append(new_item)
        else:
            dropped_items += 1

    def average(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    report = {
        "input": str(input_path),
        "output": str(args.output),
        "total_items": len(items),
        "kept_items": len(filtered),
        "dropped_items": dropped_items,
        "total_role_rewrites": len(items) * len(ROLES),
        "valid_role_rewrites": sum(role_valid.values()),
        "invalid_role_rewrites": sum(role_invalid.values()),
        "role_valid": dict(role_valid),
        "role_invalid": dict(role_invalid),
        "reason_counts": dict(reason_counts.most_common()),
        "avg_similarity_by_role": {
            role: average(similarity_by_role[role]) for role in ROLES
        },
        "avg_length_by_role": {
            role: average(length_by_role[role]) for role in ROLES
        },
        "template_counts": {
            role: dict(counter.most_common()) for role, counter in template_counts.items()
        },
        "thresholds": {
            "min_len": args.min_len,
            "max_len": args.max_len,
            "min_similarity": args.min_similarity,
            "max_similarity": args.max_similarity,
            "max_length_ratio": args.max_length_ratio,
            "role_similarity_threshold": args.role_similarity_threshold,
        },
    }
    return filtered, issues, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Check and filter role rewrite data")
    parser.add_argument("--input", "-i", default="lccc_data/role_rewrite_all.jsonl")
    parser.add_argument("--output", "-o", default="lccc_data/role_rewrite_filtered.jsonl")
    parser.add_argument("--issues", default="lccc_data/quality_issues.jsonl")
    parser.add_argument("--report", default="lccc_data/quality_report.json")
    parser.add_argument("--min-len", type=int, default=4)
    parser.add_argument("--max-len", type=int, default=120)
    parser.add_argument("--min-similarity", type=float, default=0.25)
    parser.add_argument("--max-similarity", type=float, default=0.96)
    parser.add_argument("--max-length-ratio", type=float, default=2.6)
    parser.add_argument("--role-similarity-threshold", type=float, default=0.90)
    args = parser.parse_args()

    for path in [args.output, args.issues, args.report]:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    filtered, issues, report = filter_items(args)
    write_jsonl(Path(args.output), filtered)
    write_jsonl(Path(args.issues), issues)
    with Path(args.report).open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"items: {report['total_items']} -> {report['kept_items']}")
    print(
        "role rewrites: "
        f"{report['valid_role_rewrites']} valid, "
        f"{report['invalid_role_rewrites']} filtered"
    )
    print(f"filtered data: {args.output}")
    print(f"issues: {args.issues}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
