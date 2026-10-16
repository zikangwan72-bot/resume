import json
from datetime import UTC, datetime

from app.integrations import llm


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "score": 80,
                                "recommendation": "建议复核",
                                "summary": "岗位匹配",
                                "strengths": ["需求分析"],
                                "gaps": ["SQL"],
                                "risk_flags": [],
                                "evidence": ["有相关项目经验"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }


def test_screening_prompt_serializes_job_timestamps(monkeypatch):
    captured: dict = {}

    def fake_post(*args, **kwargs):
        captured.update(kwargs["json"])
        return FakeResponse()

    monkeypatch.setattr(llm.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(llm.settings, "deepseek_model", "deepseek-v4-flash")
    monkeypatch.setattr(llm.httpx, "post", fake_post)

    result, provider, model = llm.request_screening(
        {
            "name": "AI产品经理",
            "created_at": datetime(2026, 7, 30, tzinfo=UTC),
            "updated_at": datetime(2026, 7, 30, tzinfo=UTC),
        },
        "具有企业AI产品经验",
    )

    assert result["score"] == 80
    assert provider == "deepseek"
    assert model == "deepseek-v4-flash"
    assert "2026-07-30" in captured["messages"][1]["content"]
    assert "建议面试" in captured["messages"][1]["content"]
    assert "简体中文" in captured["messages"][1]["content"]
