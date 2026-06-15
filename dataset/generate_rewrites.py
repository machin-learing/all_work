"""
LLM 批量生成多角色风格改写

使用 DeepSeek API 对提取的中性语句生成 5 类角色改写:
  boss / colleague / close_friend / girlfriend / mother

特性:
  - 分批调用 (每批 20 条), 降低格式漂移
  - 三层质量保障: JSON 校验 → 角色区分度 → 重试机制
  - 断点续跑: 中断后自动跳过已完成批次
  - 最终输出按 8:1:1 划分训练/验证/测试集

使用方法:
    # 1. 打开脚本, 在顶部 QIANFAN_API_KEY 处填入你的千帆 API Key
    # 2. 运行
    python dataset/generate_rewrites.py dataset/lccc_data/xxx_neutral.jsonl
    python dataset/generate_rewrites.py dataset/lccc_data/xxx_neutral.jsonl --batch-size 10 --split 8:1:1
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime

import requests

# ══════════════════════════════════════════════════════════════
# DeepSeek API 配置
# ══════════════════════════════════════════════════════════════

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# ============================================================
# 在这里粘贴你的 DeepSeek API Key (sk-xxx)
# ============================================================
DEEPSEEK_API_KEY = "sk-e3718cdf728d444eb7ce25e21a588320"


def load_api_key() -> str:
    if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != "your-api-key-here":
        return DEEPSEEK_API_KEY
    print("错误: 请在脚本顶部 DEEPSEEK_API_KEY 变量中填入你的 DeepSeek API Key")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════
# 角色规范 (从 LLM角色迁移prompt.txt 抽取, 作为 system prompt)
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是中文文本风格迁移数据集的标注员。

任务：对每条中性文本分别生成 5 种角色风格改写：boss、colleague、close_friend、girlfriend、mother。

⚠️ 核心概念（非常重要，不要搞反）：
- 说话的人始终是你自己（"我"），这一点永远不会变
- 角色指的是你正在对谁说话（说话对象），不是让你扮演那个角色
- 你只是在调整"我"说话的方式，以适应不同的说话对象
- 例："我今天加班" 这句话，我（说话者）始终是同一个人
  → 对 boss 说时：我用汇报的语气说
  → 对 girlfriend 说时：我用亲密的语气说
  → 但说话的人永远是我，不是老板在说话，也不是女朋友在说话

总要求：
1. 保持中性文本的核心语义不变。
2. 不新增原文没有的信息。
3. 不改变时间、地点、人物、事件、数量、因果关系。
4. 只改变语气、称呼、礼貌程度、亲密程度、措辞。
5. 输出自然中文，不要生硬。
6. 不要把每条都写成固定模板。
7. 必须输出严格 JSON Array。

语义适配判断（重要）：
在改写每条文本前，必须对每个角色问自己一个问题：
"一个正常人，会不会真的把这句话说给这个人听？"

判断原则（极度严格，仅在明确越界时判 N/A）：
- 你要极其保守地使用 N/A — 大约 95% 的日常内容对所有角色都合适
- 不同角色只是说话语气不同，内容本身几乎都能说
- 只有你 100% 确定越界才判 N/A，但凡有一丝犹豫就正常改写

仅以下 4 种情况判 N/A：
1. 明确吐槽当前公司/领导、说想辞职 → 对 boss N/A
2. 恋爱/前任/分手/暗恋等纯粹的感情纠葛 → 对 boss、colleague N/A
3. 明显性暗示/枕边私密话 → 仅 girlfriend 可, 其他全 N/A
4. 说父母坏话/骂家人 → 对 mother N/A

以下情况全部正常改写，不要判 N/A：
- 加班/累/忙/工作吐槽 → 对所有角色正常（对 boss 是汇报，对朋友是吐槽，方式不同而已）
- 吃饭/购物/出行/天气/计划 → 对所有角色正常
- 生病/不舒服 → 对所有角色正常
- 心情好坏/焦虑/开心 → 对所有角色正常
- 八卦/闲聊/吐槽(非工作类) → 对所有角色正常
- 金钱话题 → 对所有角色正常

角色规范：
boss：
- 关系：上级，远距离，工作领域
- 风格：正式、礼貌、克制、对结果负责
- 可以使用：您、同步、确认、安排、推进、进度、预计
- 注意：不要暴露个人情绪，不要撒娇，不要太随意
- 避免：宝贝、亲爱的、抱怨、不确定性表述过多

colleague：
- 关系：平级，中等距离，工作领域
- 风格：平等协作、留有余地、不卑不亢
- 可以使用：咱们、方便的话、有空、辛苦、帮我
- 注意：保持边界感，不能命令式表达，也不能过度亲密
- 避免：过分正式（不像对老板）、过分亲密（不像对朋友）

close_friend：
- 关系：平等，近距离，生活领域
- 风格：随意自然、共同语境、直来直去
- 可以使用：你、咱们、哈哈哈、一起、走起
- 注意：可以吐槽、可以自嘲，但不要说教
- 避免：正式用语、敬语、汇报式表达

girlfriend：
- 关系：平等，最近距离，恋爱领域
- 风格：亲密、温柔、情绪优先、适度安抚
- 可以使用：宝贝、想你、忙完找你、别生气、乖
- 注意：遇到事情先表达在意对方，不能只顾自己
- 避免：过度正式、冷淡、工作汇报式表达、忽略对方感受

mother：
- 关系：晚辈→长辈，近距离，家庭领域
- 风格：尊重中带温暖、让长辈放心、不报忧
- 可以使用：妈、别担心、我知道了、会照顾自己、不用等我
- 注意：不能用命令语气，不能让母亲觉得你不在乎自己
- 避免：冷淡、生硬、说教、过度情绪化、撒娇

输出格式必须严格如下（不适合的角色填 "N/A"）：
[
  {
    "id": "000001",
    "neutral": "...",
    "rewrites": {
      "boss": "...",
      "colleague": "...",
      "close_friend": "...",
      "girlfriend": "N/A",
      "mother": "..."
    }
  }
]"""

ROLES = ["boss", "colleague", "close_friend", "girlfriend", "mother"]

# ══════════════════════════════════════════════════════════════
# DeepSeek API 调用
# ══════════════════════════════════════════════════════════════


class DeepSeekAPI:
    """DeepSeek API 接口 (OpenAI 兼容)。"""

    def __init__(self, api_key: str, base_url: str = DEEPSEEK_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def chat(self, user_content: str, temperature: float = 0.8, max_tokens: int = 4096) -> str:
        """单次对话, 返回 response text。失败抛异常。"""
        payload = {
            "model": os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        url = f"{self.base_url}/v1/chat/completions"
        resp = self.session.post(url, json=payload, timeout=(30, 180))
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# ══════════════════════════════════════════════════════════════
# 质量校验
# ══════════════════════════════════════════════════════════════


def validate_batch_result(raw_text: str, expected_ids: list[str]) -> tuple[list[dict] | None, str]:
    """
    校验 LLM 返回的 JSON 是否合法。
    返回 (结果列表或None, 错误信息)。
    """
    # 1. 尝试解析 JSON
    try:
        # DeepSeek 可能返回 ```json ... ``` 包裹的内容
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return None, f"JSON解析失败: {e}"

    if not isinstance(result, list):
        return None, f"期望 Array, 实际 {type(result).__name__}"

    # 2. 逐条检查字段
    if len(result) != len(expected_ids):
        return None, f"条数不匹配: 期望 {len(expected_ids)}, 实际 {len(result)}"

    valid = []
    for i, item in enumerate(result):
        if not isinstance(item, dict):
            return None, f"第{i}条不是 dict"

        # 检查 id
        if item.get("id") != expected_ids[i]:
            return None, f"第{i}条 id 不匹配: 期望 {expected_ids[i]}, 实际 {item.get('id')}"

        # 检查 rewrites
        rewrites = item.get("rewrites")
        if not isinstance(rewrites, dict):
            return None, f"第{i}条缺少 rewrites 字段"

        for role in ROLES:
            if role not in rewrites:
                return None, f"第{i}条缺少角色 {role}"
            val = rewrites[role]
            if val == "N/A":
                continue  # 语义不适合，允许跳过
            if not isinstance(val, str) or len(val) < 2:
                return None, f"第{i}条 {role} 改写为空或太短"

        valid.append(item)

    return valid, "ok"


def check_role_diversity(items: list[dict]) -> list[str]:
    """
    检查角色区分度: ROUGE-L 相似度 > 0.8 则标记。
    返回警告列表。
    """
    warnings = []
    for item in items:
        rewrites = item["rewrites"]
        texts = [rewrites[r] if rewrites[r] != "N/A" else "" for r in ROLES]
        for i in range(len(ROLES)):
            for j in range(i + 1, len(ROLES)):
                if not texts[i] or not texts[j]:
                    continue  # N/A 跳过比较
                sim = _rouge_l_similarity(texts[i], texts[j])
                if sim > 0.8:
                    warnings.append(
                        f"  [{item['id']}] {ROLES[i]}-{ROLES[j]} 过于相似 (ROUGE-L={sim:.2f})"
                    )
    return warnings


def _rouge_l_similarity(a: str, b: str) -> float:
    """简化的 ROUGE-L 相似度 (基于最长公共子序列)。"""
    if not a or not b:
        return 0.0

    # LCS 长度
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0.0

    # 用字符级 LCS (对中文更合适)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            if a[i] == b[j]:
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i + 1][j], dp[i][j + 1])

    lcs_len = dp[m][n]
    recall = lcs_len / m if m > 0 else 0
    precision = lcs_len / n if n > 0 else 0
    if recall + precision == 0:
        return 0.0
    return 2 * recall * precision / (recall + precision)


# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════


def parse_split_ratio(ratio_str: str) -> tuple[float, float, float]:
    parts = ratio_str.split(":")
    if len(parts) != 3:
        raise ValueError(f"分割比例格式错误: {ratio_str}, 应为 8:1:1")
    a, b, c = map(int, parts)
    total = a + b + c
    return a / total, b / total, c / total


def run_pipeline(
    input_path: str,
    output_dir: str,
    batch_size: int = 20,
    temperature: float = 0.8,
    max_retries: int = 3,
    sleep_between_batches: float = 1.0,
    split_ratio: str = "8:1:1",
    api_key: str | None = None,
):
    # 加载 API Key
    if api_key is None:
        api_key = load_api_key()
    if not api_key:
        print("错误: 未提供 API Key")
        sys.exit(1)

    # 加载中性文本
    if not os.path.exists(input_path):
        print(f"错误: 文件不存在: {input_path}")
        sys.exit(1)

    items = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    if not items:
        print("错误: 输入文件为空")
        sys.exit(1)

    print(f"{'='*60}")
    print("多角色风格改写生成")
    print(f"{'='*60}")
    print(f"  模型: {os.environ.get('DEEPSEEK_MODEL', DEEPSEEK_MODEL)}")
    print(f"  输入: {input_path}")
    print(f"  样本数: {len(items)}")
    print(f"  批次大小: {batch_size} 条/批")
    print(f"  总批数: {len(items) // batch_size + (1 if len(items) % batch_size else 0)}")
    print(f"  Temperature: {temperature}")
    print(f"  最大重试: {max_retries}")
    print()

    os.makedirs(output_dir, exist_ok=True)

    # 进度文件
    progress_path = os.path.join(output_dir, "rewrite_progress.json")
    if os.path.exists(progress_path):
        with open(progress_path, "r", encoding="utf-8") as f:
            progress = json.load(f)
        completed = set(progress.get("completed", []))
        failed_batches = progress.get("failed", [])
    else:
        completed = set()
        failed_batches = []

    # 全量输出文件
    all_output_path = os.path.join(output_dir, "role_rewrite_all.jsonl")

    # 初始化 API
    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL)
    api = DeepSeekAPI(api_key, base_url)

    # 分批
    batches = []
    for start in range(0, len(items), batch_size):
        end = min(start + batch_size, len(items))
        batches.append(items[start:end])

    total_batches = len(batches)
    all_results = []
    stats = {"success": 0, "retry_saved": 0, "failed": 0, "role_warnings": 0}

    print(f"开始处理 {total_batches} 批...\n")

    for bi, batch_items in enumerate(batches):
        batch_id = bi

        # 跳过已完成的
        if batch_id in completed:
            stats["retry_saved"] += 1
            # 从已有结果中恢复
            continue

        # 构造输入
        neutral_input = []
        for item in batch_items:
            neutral_input.append({
                "id": str(item.get("id", f"{bi:04d}_{item.get('id', 0)}")).zfill(6),
                "neutral": item["neutral"],
            })

        user_prompt = "输入数据：\n" + json.dumps(neutral_input, ensure_ascii=False, indent=2)
        expected_ids = [ni["id"] for ni in neutral_input]

        # 重试循环
        success = False
        for attempt in range(max_retries):
            try:
                ts = temperature
                if attempt > 0:
                    ts = min(temperature + attempt * 0.1, 1.2)  # 重试加温增加多样性

                raw = api.chat(user_prompt, temperature=ts)
                validated, err = validate_batch_result(raw, expected_ids)

                if validated is None:
                    print(f"  [批{batch_id}] 第{attempt+1}次校验失败: {err}")
                    time.sleep(2 * (attempt + 1))
                    continue

                # 角色区分度检查
                div_warnings = check_role_diversity(validated)
                if div_warnings:
                    stats["role_warnings"] += len(div_warnings)
                    # 只是警告, 不重试
                    for w in div_warnings[:3]:  # 最多打印 3 条
                        print(f"  {w}")
                    if len(div_warnings) > 3:
                        print(f"  ... 共 {len(div_warnings)} 条警告")

                # 写入结果
                with open(all_output_path, "a", encoding="utf-8") as f:
                    for v in validated:
                        f.write(json.dumps(v, ensure_ascii=False) + "\n")

                all_results.extend(validated)
                completed.add(batch_id)
                stats["success"] += 1

                # 更新进度
                with open(progress_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "total": total_batches,
                        "completed": sorted(list(completed)),
                        "failed": failed_batches,
                        "last_updated": datetime.now().isoformat(),
                    }, f, ensure_ascii=False)

                success = True
                break

            except requests.RequestException as e:
                print(f"  [批{batch_id}] 第{attempt+1}次网络错误: {e}")
                time.sleep(3 * (attempt + 1))
            except Exception as e:
                print(f"  [批{batch_id}] 第{attempt+1}次异常: {type(e).__name__}: {e}")
                time.sleep(2 * (attempt + 1))

        if not success:
            stats["failed"] += 1
            failed_batches.append({
                "batch_id": batch_id,
                "item_ids": expected_ids,
                "error": "all retries exhausted",
            })
            # 保存失败记录
            failed_path = os.path.join(output_dir, "rewrite_failed.jsonl")
            with open(failed_path, "w", encoding="utf-8") as f:
                json.dump(failed_batches, f, ensure_ascii=False, indent=2)
            print(f"  [批{batch_id}] 全部重试失败, 已跳过")

        # 批间休息
        if sleep_between_batches > 0 and bi < total_batches - 1:
            time.sleep(sleep_between_batches)

        # 进度条
        done = len(completed) + stats["failed"]
        pct = done / total_batches * 100
        print(f"  进度: {done}/{total_batches} ({pct:.0f}%)  |  "
              f"成功: {stats['success']}  跳过: {stats['retry_saved']}  失败: {stats['failed']}")
        sys.stdout.flush()

    # ── 如果有跳过/恢复的批次, 从文件重读所有结果 ──
    if stats["retry_saved"] > 0:
        all_results = []
        if os.path.exists(all_output_path):
            with open(all_output_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        all_results.append(json.loads(line))

    print(f"\n{'='*60}")
    print("生成完成")
    print(f"{'='*60}")
    print(f"  总改写条数: {len(all_results)} × 5角色 = {len(all_results) * 5} 条")
    print(f"  成功批次:   {stats['success']}")
    print(f"  跳过批次:   {stats['retry_saved']}")
    print(f"  失败批次:   {stats['failed']}")
    print(f"  区分度警告: {stats['role_warnings']}")
    print()

    # ── 按 8:1:1 划分数据集 ──
    train_r, val_r, test_r = parse_split_ratio(split_ratio)

    import random
    random.seed(42)
    shuffled = list(all_results)
    random.shuffle(shuffled)

    n = len(shuffled)
    n_train = int(n * train_r)
    n_val = int(n * val_r)

    splits = {
        "train": shuffled[:n_train],
        "val":   shuffled[n_train:n_train + n_val],
        "test":  shuffled[n_train + n_val:],
    }

    for name, data in splits.items():
        path = os.path.join(output_dir, f"role_rewrite_{name}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for d in data:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        size = os.path.getsize(path) / 1024
        print(f"  {name}: {len(data)} 条 → {path} ({size:.1f} KB)")

    # ── 最终状态 ──
    print(f"\n输出目录: {output_dir}")
    print(f"  全量: {all_output_path}")
    print(f"  进度: {progress_path}")

    # 如果有失败批次, 提示如何重试
    if stats["failed"] > 0:
        failed_path = os.path.join(output_dir, "rewrite_failed.jsonl")
        print(f"\n⚠️  有 {stats['failed']} 批失败, 详情: {failed_path}")
        print("   删除进度文件后重新运行可重试失败批次:")
        print(f"   del {progress_path}")

    return all_results


def main():
    parser = argparse.ArgumentParser(description="LLM 批量生成多角色风格改写 (DeepSeek V3.2)")
    parser.add_argument("input", help="中性语句 JSONL 文件路径 (Step 2 输出)")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="输出目录 (默认: 与输入同目录)")
    parser.add_argument("--batch-size", "-b", type=int, default=20,
                        help="每批条数 (默认: 20)")
    parser.add_argument("--temperature", "-t", type=float, default=0.8,
                        help="生成温度 (默认: 0.8)")
    parser.add_argument("--max-retries", "-r", type=int, default=3,
                        help="每批最大重试次数 (默认: 3)")
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="批间休息秒数 (默认: 1.0)")
    parser.add_argument("--split", default="8:1:1",
                        help="训练/验证/测试分割比例 (默认: 8:1:1)")
    parser.add_argument("--api-key", "-k", default=None,
                        help="千帆 API Key (也可用环境变量 QIANFAN_API_KEY 或 .apikey 文件)")
    args = parser.parse_args()

    if args.output_dir is None:
        args.output_dir = os.path.dirname(args.input) or "."

    print("=" * 60)
    print("多角色风格改写生成")
    print("  API: DeepSeek")
    print("=" * 60)
    print()

    run_pipeline(
        input_path=args.input,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        temperature=args.temperature,
        max_retries=args.max_retries,
        sleep_between_batches=args.sleep,
        split_ratio=args.split,
        api_key=args.api_key,
    )


if __name__ == "__main__":
    main()
