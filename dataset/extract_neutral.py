"""
从 LCCC 对话中提取中性语句

多阶段筛选管线:
  1. 拆句 → 去空格 → 长度过滤 (8-65字)
  2. 排除: 角色标记 / 强烈情绪 / 敏感 / 广告 / 纯疑问
  3. 必须有"我"且包含可改写信息
  4. 按改写潜力评分排序
  5. 去重输出

使用方法:
    python extract_neutral.py lccc_data/lccc_base_train_5000.jsonl
    python extract_neutral.py lccc_data/lccc_base_train_5000.jsonl -n 2000
    python extract_neutral.py lccc_data/lccc_base_train_5000.jsonl --show-rejects
"""

import argparse
import json
import os
import re
import sys
from collections import Counter


# ══════════════════════════════════════════════════════════════
# 配置: 可调参数
# ══════════════════════════════════════════════════════════════

MIN_LEN = 8       # 最短: "我今天好累。" = 7字，取8
MAX_LEN = 65      # 最长: 留出足够空间

# ══════════════════════════════════════════════════════════════
# 排除词表: 含这些词 → 不中性
# ══════════════════════════════════════════════════════════════

ROLE_MARKERS = [
    # 亲密关系称呼
    "宝贝", "亲爱的", "老婆", "老公", "媳妇", "媳妇儿",
    "妈", "妈妈", "爸", "爸爸", "母亲", "父亲", "老妈", "老爸",
    "儿子", "女儿", "孩子", "宝宝",
    # 正式关系
    "您", "老板", "领导", "客户", "经理", "总监",
    # 亲密语气词
    "么么", "摸摸", "抱抱", "亲亲", "想你", "爱你",
    # 建议/说教
    "你应该", "你不要", "你最好", "你得多",
    # 商家/客服语气
    "亲", "下单", "包邮",
]

# ══════════════════════════════════════════════════════════════
# 排除正则: 含这些模式 → 不中性
# ══════════════════════════════════════════════════════════════

BAD_REGEX = [
    # 过度情绪 (连续标点)
    re.compile(r"[！!]{2,}"),
    re.compile(r"[？?]{2,}"),
    re.compile(r"[哈]{2,}"),
    re.compile(r"[呜]{2,}"),
    re.compile(r"\.{2,}"),           # 无语/省略过多
    # 脏话
    re.compile(r"卧槽|我操|尼玛|妈的|草泥马|傻逼|sb|SB"),
    # 广告营销
    re.compile(r"加微信|扫码|关注公众号|转发|抽奖|福利|优惠|打折|满减|秒杀"),
    # 网络流行梗/无意义
    re.compile(r"^[哈哈嘿嘿嗯哦啊哎嗐啧]{1,4}$"),
    # 纯数字/日期/时间 (无实质内容)
    re.compile(r"^\d{1,4}[年/\-]\d{1,2}[月/\-]\d{1,2}[日号]?$"),
    # 反问/发泄 (不是中性陈述)
    re.compile(r"凭什么|怎么办|怎么搞|咋整|咋办"),
]

# ══════════════════════════════════════════════════════════════
# 性别暴露标记: 含这些词 → 说话者身份与目标角色冲突
# 目标角色 girlfriend/wife 默认说话者为男性，
# 若原句暴露女性身份 (如"我老公") 则应跳过。
# ══════════════════════════════════════════════════════════════

GENDER_FEMALE_MARKERS = [
    # 配偶/伴侣 → 女性说话者
    "我老公", "我男朋友", "我男友", "我前夫",
    # 女性生理/经历
    "怀孕", "大姨妈", "例假", "月经", "坐月子",
    "嫁给他", "嫁人", "出嫁",
    # 女性身份自称
    "老娘", "本姑娘", "本小姐",
    # 女性专属物品/行为
    "穿裙子", "化妆", "涂口红",
]

# ══════════════════════════════════════════════════════════════
# 必须有"我"  — 第一人称是角色迁移的核心
# 下面额外给一个宽松模式: 无"我"但描述个人经历/状态的也收
# ══════════════════════════════════════════════════════════════

# 有"我"时: 加分项 (改写信息量多)
INFO_KEYWORDS = [
    # 时间安排
    "今天", "明天", "昨天", "今晚", "明晚", "下周", "周末", "刚才", "马上", "最近",
    "一会儿", "稍后", "晚点", "早点", "这周", "明早",
    # 工作学习
    "加班", "开会", "出差", "上班", "下班", "项目", "任务", "工作", "面试",
    "学校", "上课", "考试", "作业", "毕业",
    # 行程
    "回家", "出发", "到了", "回来", "过去", "过来", "出去", "出门", "路上",
    # 状态
    "忙", "累", "不舒服", "有事", "堵车", "生病", "感冒", "发烧",
    # 计划/意愿
    "打算", "准备", "计划", "安排",
    # 信息传递
    "回复", "联系", "通知", "告诉", "发消息", "打电话",
    # 吃饭
    "吃饭", "做饭", "外卖", "食堂", "餐厅",
    # 钱
    "工资", "房租", "房贷", "车贷", "花了", "买了",
    # 让步/转折
    "可能", "应该", "不过", "但是", "虽然", "其实",
    # 动作
    "帮忙", "处理", "解决", "搞定", "确认", "核对",
]


def split_chinese_sentences(text: str) -> list[str]:
    """拆分一段文本为单句。处理 LCCC 的空格分词格式。"""
    if not text:
        return []

    # LCCC 文本: "我 今天 加班 ， 可能 晚点 回去 。"
    # 先去空格还原为正常中文
    clean = text.replace(" ", "").replace("　", "")
    if not clean:
        return []

    # 按终结标点切分: 。！？…!?
    sentences = []
    buf = ""
    for ch in clean:
        buf += ch
        if ch in "。！？…!?":
            s = buf.strip()
            if s:
                sentences.append(s)
            buf = ""
    # 残余片段 (无终结标点但内容≥5字)
    leftover = buf.strip()
    if leftover and len(leftover) >= 5:
        sentences.append(leftover)

    return sentences


def score_sentence(s: str) -> int:
    """给句子打分 (0-100)，分数越高改写潜力越大。"""
    score = 0

    # 基础分: 长度适中最好 (10-40字给满分)
    L = len(s)
    if 10 <= L <= 40:
        score += 30
    elif 8 <= L <= 10 or 40 <= L <= 55:
        score += 15
    else:
        score += 5

    # 有"我" +25
    if "我" in s:
        score += 25

    # 信息关键词命中数
    kw_hits = sum(1 for kw in INFO_KEYWORDS if kw in s)
    score += min(kw_hits * 8, 40)

    # 终结标点是句号 (陈述句) +5
    if s.endswith("。"):
        score += 5

    return score


def check_neutral(sentence: str, min_len: int, max_len: int) -> tuple[bool, str]:
    """
    多阶段检查句子是否中性可改写。
    返回 (通过, 原因)。
    """
    s = sentence.strip()

    # Stage 1: 长度
    if len(s) < min_len:
        return False, f"太短({len(s)}字)"
    if len(s) > max_len:
        return False, f"太长({len(s)}字)"

    # Stage 2: 角色标记
    for marker in ROLE_MARKERS:
        if marker in s:
            return False, f"角色词:{marker}"

    # Stage 3: 坏模式
    for pat in BAD_REGEX:
        if pat.search(s):
            desc = pat.pattern[:25].replace("\n", "")
            return False, f"排除:{desc}"

    # Stage 4: 性别暴露 (说话者性别与目标角色冲突)
    for marker in GENDER_FEMALE_MARKERS:
        if marker in s:
            return False, f"女性身份:{marker}"

    # Stage 5: 必须有"我"
    if "我" not in s:
        return False, "无第一人称"

    # Stage 6: 必须包含信息关键词
    if not any(kw in s for kw in INFO_KEYWORDS):
        return False, "信息量不足"

    # Stage 7: 基本句法检查
    alpha_count = len(re.findall(r"[a-zA-Z0-9\s\.\,\!\?\;\:\-\_\@\#\$\%\&\*\(\)\[\]\{\}\\\/\+\=]+", s))
    if alpha_count > len(s) * 0.5:
        return False, "非中文为主"

    return True, "ok"


def extract(
    input_path: str,
    output_path: str,
    min_len: int = MIN_LEN,
    max_len: int = MAX_LEN,
    max_output: int = 0,
    min_score: int = 0,
    report_path: str | None = None,
    show_rejects: bool = False,
):
    if not os.path.exists(input_path):
        print(f"错误: 文件不存在: {input_path}")
        sys.exit(1)

    total_dialogs = 0
    total_turns = 0
    total_sentences = 0
    candidates = []
    reasons = Counter()
    len_dist = Counter()

    print(f"读取: {input_path}")
    print(f"参数: 句长 {min_len}-{max_len}字, 最低分 {min_score}")
    print()

    with open(input_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue

            dialog = sample.get("dialog", [])
            total_dialogs += 1

            for turn_text in dialog:
                total_turns += 1
                sentences = split_chinese_sentences(turn_text)
                for sent in sentences:
                    total_sentences += 1
                    bucket = (len(sent) // 5) * 5
                    len_dist[bucket] += 1

                    ok, reason = check_neutral(sent, min_len, max_len)
                    if ok:
                        sc = score_sentence(sent)
                        if sc >= min_score:
                            candidates.append({
                                "id": len(candidates),
                                "neutral": sent,
                                "score": sc,
                                "source_dialog": line_num,
                                "length": len(sent),
                            })
                        else:
                            reasons[f"分低({sc})"] += 1
                    else:
                        reasons[reason] += 1

                    if max_output > 0 and len(candidates) >= max_output * 3:
                        break  # 多收一些用于评分排序
                if max_output > 0 and len(candidates) >= max_output * 3:
                    break
            if max_output > 0 and len(candidates) >= max_output * 3:
                break

            if line_num % 50000 == 0:
                print(f"  ...已处理 {line_num:,} 对话, 候选 {len(candidates):,}")

    # ── 按分数排序 ──
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # ── 去重 ──
    seen = set()
    unique = []
    for c in candidates:
        # 归一化去重: 去掉标点后比较
        norm = re.sub(r"[。！？…!?,，\.\s]", "", c["neutral"])
        if norm not in seen:
            seen.add(norm)
            unique.append(c)
    dup_count = len(candidates) - len(unique)
    candidates = unique

    # ── 截取 ──
    if max_output > 0 and len(candidates) > max_output:
        candidates = candidates[:max_output]

    # ── 重新编号 ──
    for i, c in enumerate(candidates):
        c["id"] = i

    # ── 保存 ──
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # ── 打印报告 ──
    print(f"\n{'='*60}")
    print("提取完成")
    print(f"{'='*60}")
    print(f"  对话数:       {total_dialogs:,}")
    print(f"  对话轮次:     {total_turns:,}")
    print(f"  拆出句子:     {total_sentences:,}")
    print(f"  候选 (筛后):  {len(candidates):,}")
    print(f"  去重剔除:     {dup_count}")
    rate = len(candidates) / max(total_sentences, 1) * 100
    print(f"  通过率:       {rate:.1f}%")
    print(f"\n保存到: {output_path}")

    # 排除原因 top-10
    print(f"\n--- 排除原因 Top-10 ---")
    for reason, count in reasons.most_common(10):
        pct = count / max(total_sentences, 1) * 100
        print(f"  {reason:25s} {count:>8,}  ({pct:5.1f}%)")

    # 分数分布
    if candidates:
        scores = [c["score"] for c in candidates]
        print(f"\n--- 候选分数分布 ---")
        print(f"  最高: {max(scores)}, 最低: {min(scores)}, 平均: {sum(scores)/len(scores):.0f}")

    # 样例
    print(f"\n--- 候选样例 (Top-10 高分) ---")
    for c in candidates[:10]:
        print(f"  [分{c['score']:3d} / {c['length']}字] {c['neutral']}")

    # ── 可选的被拒样例 ──
    if show_rejects and candidates:
        print(f"\n--- 被拒样例 (仅供参考) ---")
        import random
        random.seed(0)
        rejected = []
        with open(input_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f):
                if len(rejected) >= 10:
                    break
                line = line.strip()
                if not line: continue
                try:
                    sample = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for turn_text in sample.get("dialog", []):
                    for sent in split_chinese_sentences(turn_text):
                        ok, reason = check_neutral(sent, min_len, max_len)
                        if not ok and len(rejected) < 10:
                            if random.random() < 0.05:  # 5% 采样
                                rejected.append((sent, reason))
        for sent, reason in rejected:
            print(f"  [{reason}] {sent[:80]}")

    # ── 可选: 报告文件 ──
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_dialogs": total_dialogs,
                "total_turns": total_turns,
                "total_sentences": total_sentences,
                "candidates": len(candidates),
                "pass_rate": round(rate, 2),
                "score_range": [min(scores), max(scores)] if candidates else [0, 0],
                "top_reasons": dict(reasons.most_common(20)),
            }, f, ensure_ascii=False, indent=2)
        print(f"\n报告: {report_path}")

    return candidates


def main():
    parser = argparse.ArgumentParser(description="从 LCCC 对话中提取中性语句")
    parser.add_argument("input", help="LCCC JSONL 文件路径")
    parser.add_argument("--output", "-o", default=None,
                        help="输出 JSONL 路径 (默认: <input>_neutral.jsonl)")
    parser.add_argument("--min-len", type=int, default=MIN_LEN,
                        help=f"最短字数 (默认: {MIN_LEN})")
    parser.add_argument("--max-len", type=int, default=MAX_LEN,
                        help=f"最长字数 (默认: {MAX_LEN})")
    parser.add_argument("--max-output", "-n", type=int, default=0,
                        help="最大输出条数 (0=不限)")
    parser.add_argument("--min-score", type=int, default=20,
                        help="最低质量分 (默认: 20)")
    parser.add_argument("--report", "-r", default=None,
                        help="筛选报告 JSON 路径")
    parser.add_argument("--show-rejects", action="store_true",
                        help="展示被拒样例")
    args = parser.parse_args()

    if args.output is None:
        base = os.path.splitext(args.input)[0]
        args.output = f"{base}_neutral.jsonl"

    print(f"{'='*60}")
    print("LCCC 中性语句提取")
    print(f"{'='*60}")
    print(f"  输入: {args.input}")
    print(f"  输出: {args.output}")
    print(f"  句长: {args.min_len}-{args.max_len}字")
    print(f"  最低分: {args.min_score}")
    print(f"  上限: {'不限' if args.max_output == 0 else f'{args.max_output} 条'}")
    print()

    extract(
        input_path=args.input,
        output_path=args.output,
        min_len=args.min_len,
        max_len=args.max_len,
        max_output=args.max_output,
        min_score=args.min_score,
        report_path=args.report,
        show_rejects=args.show_rejects,
    )


if __name__ == "__main__":
    main()
