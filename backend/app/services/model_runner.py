import os
import re

import requests

from app.core.config import settings


ROLE_SPECS = {
    "boss": {
        "name": "老板",
        "spec": "上级、远距离、工作领域。正式、礼貌、克制，称呼用“您”。",
        "style": "正式、礼貌、克制，强调结果和进度",
        "prefix": "您好, ",
        "suffix": "我会同步好相关安排。",
    },
    "colleague": {
        "name": "同事",
        "spec": "平级、中等距离、工作领域。平等协作，留有余地。",
        "style": "平等协作，保留边界感",
        "prefix": "你好, ",
        "suffix": "有空的话麻烦看一下。",
    },
    "close_friend": {
        "name": "好朋友",
        "spec": "平等、近距离、生活领域。随意自然，直来直去。",
        "style": "随意、自然、直接",
        "prefix": "兄弟, ",
        "suffix": "回头一起整。",
    },
    "girlfriend": {
        "name": "女朋友",
        "spec": "平等、最近距离、恋爱领域。亲密、温柔、情绪优先。",
        "style": "亲密、温柔、在意对方感受",
        "prefix": "宝贝, ",
        "suffix": "别担心, 忙完我就来找你。",
    },
    "mother": {
        "name": "母亲",
        "spec": "晚辈到长辈、近距离、家庭领域。尊重中带温暖，让长辈放心。",
        "style": "尊重、温暖、让长辈放心",
        "prefix": "妈, ",
        "suffix": "你早点休息, 不用等我。",
    },
}


def _role(role_code: str) -> dict[str, str]:
    return ROLE_SPECS.get(role_code, ROLE_SPECS["boss"])


def _build_deepseek_prompt(source_text: str, role_code: str) -> str:
    role = _role(role_code)
    return (
        f"把我(说话者)的一句话改写成我对“{role['name']}”说话的语气和措辞。\n"
        "只改变语气、称呼、礼貌程度和措辞，不改变核心语义。\n"
        f"目标对象特征：{role['spec']}\n"
        "明显越界才返回 N/A；大多数日常表达都应正常改写。\n\n"
        f"原句：{source_text}\n"
        "只返回改写结果。"
    )


def _build_lora_input(source_text: str, role_code: str) -> str:
    role = ROLE_SPECS[role_code]
    return (
        "任务：保持原意，按目标对象改写语气。\n"
        f"对象：{role['name']}\n"
        f"风格：{role['style']}\n"
        f"原句：{source_text}\n"
        "改写："
    )


class DeepSeekAPI:
    def __init__(self) -> None:
        self.base_url = settings.deepseek_base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            }
        )

    def rewrite(self, source_text: str, role_code: str) -> str:
        try:
            response = self.session.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": _build_deepseek_prompt(source_text, role_code),
                        }
                    ],
                    "temperature": 0.8,
                    "max_tokens": 512,
                },
                timeout=(30, 60),
            )
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"].strip()
            return re.sub(r'^["\']|["\']$', "", text)
        except Exception as exc:
            return f"[DeepSeek error] {type(exc).__name__}"


class LoRAInference:
    def __init__(self) -> None:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.torch = torch
        self.dtype = self._resolve_dtype(torch)
        self.tokenizer = AutoTokenizer.from_pretrained(settings.lora_base_model)

        print(f"[LoRA] loading base model on {self.device}, precision={self.dtype}")
        base_model = AutoModelForSeq2SeqLM.from_pretrained(
            settings.lora_base_model,
            torch_dtype=self.dtype,
        ).to(self.device)

        adapter_path = os.path.join(settings.lora_model_dir, "final")
        self.model = PeftModel.from_pretrained(
            base_model,
            adapter_path,
            adapter_name="role_conditioned",
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
        if role_code not in ROLE_SPECS:
            return f"[错误] 未知角色: {role_code}"

        inputs = self.tokenizer(
            _build_lora_input(source_text, role_code),
            return_tensors="pt",
            max_length=256,
            truncation=True,
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with self.torch.inference_mode():
            output = self.model.generate(**inputs, max_length=128, num_beams=4)
        return self.tokenizer.decode(output[0], skip_special_tokens=True)


_deepseek: DeepSeekAPI | None = None
_lora: LoRAInference | None = None


def _get_deepseek() -> DeepSeekAPI:
    global _deepseek
    if _deepseek is None:
        _deepseek = DeepSeekAPI()
    return _deepseek


def _get_lora() -> LoRAInference:
    global _lora
    if _lora is None:
        _lora = LoRAInference()
    return _lora


def _rule_rewrite(source_text: str, role_code: str) -> str:
    role = _role(role_code)
    return f"{role['prefix']}{source_text}。{role['suffix']}"


def rewrite_text(source_text: str, role_code: str, model_code: str) -> str:
    if model_code == "deepseek_api":
        return _get_deepseek().rewrite(source_text, role_code)
    if model_code == "lora_finetuned":
        return _get_lora().rewrite(source_text, role_code)
    if model_code == "transformer_scratch":
        return _rule_rewrite(source_text, role_code)
    return source_text
