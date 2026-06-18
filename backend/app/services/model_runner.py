"""
模型推理服务。

支持的模型:
  - deepseek_api:    真实调用 DeepSeek API
  - lora_finetuned:  共享单 LoRA 适配器，通过角色条件输入控制风格
  - transformer_scratch:  占位符
"""

import re
import os

import requests

from app.core.config import settings


# ══════════════════════════════════════════════════════════════
# DeepSeek API (教师模型)
# ══════════════════════════════════════════════════════════════

ROLE_SPECS = {
    "boss": {"name": "老板", "spec": "上级, 远距离, 工作领域。风格: 正式, 礼貌, 克制, 对结果负责。称呼用「您」。"},
    "colleague": {"name": "同事", "spec": "平级, 中等距离, 工作领域。风格: 平等协作, 留有余地, 不卑不亢。用「咱们」「方便的话」。"},
    "close_friend": {"name": "好朋友", "spec": "平等, 近距离, 生活领域。风格: 随意自然, 直来直去。可以吐槽, 不要说教。"},
    "girlfriend": {"name": "女朋友", "spec": "平等, 最近距离, 恋爱领域。风格: 亲密, 温柔, 情绪优先。用「宝贝」「想你」。"},
    "mother": {"name": "母亲", "spec": "晚辈到长辈, 近距离, 家庭领域。风格: 尊重中带温暖, 让长辈放心。用「妈」开头。"},
}


def _build_single_prompt(source_text: str, role_code: str) -> str:
    role = ROLE_SPECS.get(role_code, ROLE_SPECS["boss"])
    name, spec = role["name"], role["spec"]
    return (
        f"把我(说话者)的一句话, 改写成我对「{name}」说这句话的语气和措辞。\n"
        f"只改变语气、称呼、礼貌程度、措辞, 不改变核心语义。\n"
        f"{name}特征: {spec}\n"
        f"判断: 明显越界才返回 N/A (如吐槽公司 -> boss N/A; 感情纠葛 -> boss/colleague N/A; 私密 -> 仅girlfriend)\n"
        f"大多数日常对所有角色都正常, 不确定就正常改写。\n\n"
        f"改写这句话:\"{source_text}\"\n对「{name}」应该怎么说? 只返回结果。"
    )


class DeepSeekAPI:
    def __init__(self):
        self.key = settings.deepseek_api_key
        self.base = settings.deepseek_base_url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})

    def rewrite(self, source_text: str, role_code: str) -> str:
        try:
            resp = self.s.post(
                f"{self.base}/v1/chat/completions",
                json={"model": settings.deepseek_model, "messages": [{"role": "user", "content": _build_single_prompt(source_text, role_code)}],
                      "temperature": 0.8, "max_tokens": 512},
                timeout=(30, 60),
            )
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"].strip()
            return re.sub(r'^["\']|["\']$', '', result)
        except Exception as e:
            return f"[DeepSeek error] {type(e).__name__}"


# ══════════════════════════════════════════════════════════════
# LoRA 多角色推理
# ══════════════════════════════════════════════════════════════

ROLES = ["boss", "colleague", "close_friend", "girlfriend", "mother"]
LORA_BASE = settings.lora_model_dir  # e.g. "finetune/output"


LORA_ROLE_SPECS = {
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


def _build_lora_input(source_text: str, role_code: str) -> str:
    role = LORA_ROLE_SPECS[role_code]
    return (
        "任务：保持原意，按目标对象改写语气。\n"
        f"对象：{role['name']}\n"
        f"风格：{role['style']}\n"
        f"原句：{source_text}\n"
        "改写："
    )


class LoRAInference:
    """Load one shared role-conditioned LoRA adapter."""

    def __init__(self):
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        from peft import PeftModel

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.torch = torch
        self.dtype = self._resolve_dtype(torch)
        self.tokenizer = AutoTokenizer.from_pretrained(settings.lora_base_model)

        print(f"[LoRA] loading base model on {self.device}, precision={self.dtype}")
        self.base_model = AutoModelForSeq2SeqLM.from_pretrained(
            settings.lora_base_model,
            torch_dtype=self.dtype,
        ).to(self.device)

        adapter_path = os.path.join(LORA_BASE, "final")
        self.model = PeftModel.from_pretrained(
            self.base_model, adapter_path, adapter_name="role_conditioned"
        )
        self.model.eval()
        print(f"[LoRA] loaded shared adapter: {adapter_path}")

    def _resolve_dtype(self, torch):
        if self.device != "cuda":
            return torch.float32

        precision = settings.lora_precision.lower()
        if precision == "bf16":
            if torch.cuda.is_bf16_supported():
                return torch.bfloat16
            print("[LoRA] bf16 is not supported on this GPU; falling back to fp16.")
            return torch.float16
        if precision == "fp32":
            return torch.float32
        return torch.float16

    def rewrite(self, source_text: str, role_code: str) -> str:
        if role_code not in ROLES:
            return f"[错误] 未知角色: {role_code}"

        model_input = _build_lora_input(source_text, role_code)
        inp = self.tokenizer(model_input, return_tensors="pt", max_length=256, truncation=True)
        inp = {k: v.to(self.device) for k, v in inp.items()}
        with self.torch.inference_mode():
            out = self.model.generate(**inp, max_length=128, num_beams=4)
        return self.tokenizer.decode(out[0], skip_special_tokens=True)


# ══════════════════════════════════════════════════════════════
# 占位符
# ══════════════════════════════════════════════════════════════

_PREFIX = {
    "boss": "您好, ", "colleague": "你好, ", "close_friend": "兄弟, ",
    "girlfriend": "宝贝, ", "mother": "妈, ",
}
_SUFFIX = {
    "boss": "我会同步好相关安排。", "colleague": "有空的话麻烦看一下。",
    "close_friend": "回头一起整。", "girlfriend": "别担心, 忙完我就来找你。",
    "mother": "你早点休息, 不用等我。",
}


# ══════════════════════════════════════════════════════════════
# 统一入口
# ══════════════════════════════════════════════════════════════

_deepseek: DeepSeekAPI | None = None
_lora: LoRAInference | None = None


def _get_deepseek():
    global _deepseek
    if _deepseek is None:
        _deepseek = DeepSeekAPI()
    return _deepseek


def _get_lora():
    global _lora
    if _lora is None:
        _lora = LoRAInference()
    return _lora


def rewrite_text(source_text: str, role_code: str, model_code: str) -> str:
    if model_code == "deepseek_api":
        return _get_deepseek().rewrite(source_text, role_code)
    if model_code == "lora_finetuned":
        return _get_lora().rewrite(source_text, role_code)
    if model_code == "transformer_scratch":
        return f"{_PREFIX.get(role_code, '')}{source_text}。{_SUFFIX.get(role_code, '')}"
    return source_text
