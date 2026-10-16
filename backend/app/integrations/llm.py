import json
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi.encoders import jsonable_encoder

from app.core.config import settings


@dataclass(frozen=True)
class LLMStatus:
    configured: bool
    provider: str
    model: str | None
    message: str


def get_llm_status() -> LLMStatus:
    if not settings.ai_configured:
        return LLMStatus(
            configured=False,
            provider="openai-compatible",
            model=None,
            message="AI provider is disabled until server-side credentials are configured.",
        )
    if settings.deepseek_api_key:
        return LLMStatus(
            configured=True,
            provider="deepseek",
            model=settings.deepseek_model,
            message="DeepSeek provider configured; AI results require human review.",
        )
    return LLMStatus(
        configured=True,
        provider="openai",
        model=settings.openai_model,
        message="Provider configured; business modules must still implement evaluation and review.",
    )


class LLMNotConfiguredError(RuntimeError):
    """No server-side AI credentials are configured."""


class LLMRequestError(RuntimeError):
    """Provider request or response failed."""


def request_screening(job: dict[str, Any], resume_text: str) -> tuple[dict[str, Any], str, str]:
    if settings.deepseek_api_key:
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url
        model = settings.deepseek_model
        provider = "deepseek"
    elif settings.openai_api_key and settings.openai_model:
        api_key = settings.openai_api_key
        base_url = "https://api.openai.com/v1"
        model = settings.openai_model
        provider = "openai"
    else:
        raise LLMNotConfiguredError("AI 未配置，请先配置服务端模型密钥")

    prompt = {
        "job": job,
        "resume_text": resume_text,
        "rules": [
            "所有输出使用简体中文",
            "只评价与岗位直接相关的经历和技能，不使用年龄、性别、民族等受保护属性",
            "AI仅提供辅助判断，不能自动录用或淘汰候选人",
            "evidence必须引用简历或岗位标准中的具体事实",
        ],
        "output_contract": {
            "score": "number 0-100",
            "recommendation": "只能是：建议面试、建议保留、不建议推进",
            "summary": "简体中文字符串",
            "strengths": "简体中文字符串数组",
            "gaps": "简体中文字符串数组",
            "risk_flags": "简体中文字符串数组",
            "evidence": "简体中文字符串数组",
        },
    }
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0,
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "你是简历筛选助手，只返回合法 JSON，不做自动录用或淘汰。",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(jsonable_encoder(prompt), ensure_ascii=False),
                    },
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, str) and content.startswith("```"):
            content = content.strip().removeprefix("```json").removesuffix("```").strip()
        result = json.loads(content) if isinstance(content, str) else content
        if not isinstance(result, dict):
            raise ValueError("model output is not an object")
        return result, provider, model
    except (
        httpx.HTTPError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise LLMRequestError("AI 模型调用失败或返回了非法 JSON") from exc
