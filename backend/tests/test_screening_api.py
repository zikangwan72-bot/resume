import io

from tests.test_screening_parser import docx_fixture, pdf_fixture


def job_payload(name="Python PM"):
    return {
        "name": name,
        "description": "Build enterprise AI products",
        "required_skills": ["Python", "产品设计"],
        "preferred_skills": ["SQL"],
        "rejection_conditions": ["无相关经验"],
        "scoring_weights": {"required_skills": 0.7, "preferred_skills": 0.3},
        "status": "active",
    }


def test_screening_jobs_upload_dashboard_and_review(client, admin_headers, monkeypatch):
    created = client.post("/api/v1/screening/jobs", headers=admin_headers, json=job_payload())
    assert created.status_code == 201
    job_id = created.json()["data"]["id"]

    bad = client.post(
        "/api/v1/screening/resumes",
        headers=admin_headers,
        files={"file": ("resume.txt", b"not supported", "text/plain")},
        data={"job_id": str(job_id)},
    )
    assert bad.status_code == 400
    assert "仅支持 PDF 和 DOCX" in bad.json()["detail"]

    uploaded = client.post(
        "/api/v1/screening/resumes",
        headers=admin_headers,
        files={"file": ("resume.pdf", io.BytesIO(pdf_fixture()), "application/pdf")},
        data={"job_id": str(job_id)},
    )
    assert uploaded.status_code == 201
    resume_id = uploaded.json()["data"]["id"]

    not_configured = client.post(
        f"/api/v1/screening/resumes/{resume_id}/screen",
        headers=admin_headers,
        params={"job_id": job_id},
    )
    assert not_configured.status_code == 503
    assert "AI 未配置" in not_configured.json()["detail"]
    assert client.get("/api/v1/screening/results", headers=admin_headers).json()["data"] == []

    def fake_screening(job, resume_text):
        return (
            {
                "score": 82,
                "recommendation": "待复核",
                "summary": "匹配",
                "strengths": ["Python"],
                "gaps": ["SQL"],
                "risk_flags": [],
                "evidence": [resume_text],
            },
            "local-rules",
            "offline-test",
        )

    from app.integrations import llm

    monkeypatch.setattr(llm, "request_screening", fake_screening)
    screened = client.post(
        f"/api/v1/screening/resumes/{resume_id}/screen",
        headers=admin_headers,
        params={"job_id": job_id},
    )
    assert screened.status_code == 201
    result = screened.json()["data"]
    result_id = result["id"]
    assert result["score"] == 82

    dashboard = client.get("/api/v1/screening/dashboard", headers=admin_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["data"]["total_results"] == 1
    assert dashboard.json()["data"]["pending_review"] == 1

    overview = client.get("/api/v1/screening/overview", headers=admin_headers)
    assert overview.status_code == 200
    overview_data = overview.json()["data"]
    assert overview_data["summary"]["total_results"] == 1
    assert any(job["id"] == job_id for job in overview_data["jobs"])
    assert overview_data["pending_results"][0]["id"] == result_id

    reviewed = client.patch(
        f"/api/v1/screening/results/{result_id}/review",
        headers=admin_headers,
        json={"human_status": "approved", "review_note": "人工确认"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["data"]["score"] == 82
    assert reviewed.json()["data"]["human_status"] == "approved"

    blocked_delete = client.delete(
        f"/api/v1/screening/jobs/{job_id}", headers=admin_headers
    )
    assert blocked_delete.status_code == 409
    assert "已有筛选结果" in blocked_delete.json()["detail"]

    deletable = client.post(
        "/api/v1/screening/jobs",
        headers=admin_headers,
        json=job_payload("可删除岗位标准"),
    ).json()["data"]
    deleted = client.delete(
        f"/api/v1/screening/jobs/{deletable['id']}", headers=admin_headers
    )
    assert deleted.status_code == 204
    assert not any(
        job["id"] == deletable["id"]
        for job in client.get("/api/v1/screening/jobs", headers=admin_headers).json()["data"]
    )


def test_docx_upload_and_invalid_model_output_does_not_create_result(
    client, admin_headers, monkeypatch
):
    job = client.post(
        "/api/v1/screening/jobs", headers=admin_headers, json=job_payload("DOCX PM")
    ).json()["data"]
    uploaded = client.post(
        "/api/v1/screening/resumes",
        headers=admin_headers,
        files={
            "file": (
                "resume.docx",
                io.BytesIO(docx_fixture()),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"job_id": str(job["id"])},
    )
    resume_id = uploaded.json()["data"]["id"]
    from app.integrations import llm

    monkeypatch.setattr(
        llm, "request_screening", lambda *_: ({"score": 101}, "offline-test", "test")
    )
    response = client.post(
        f"/api/v1/screening/resumes/{resume_id}/screen",
        headers=admin_headers,
        params={"job_id": job["id"]},
    )
    assert response.status_code == 502
    assert client.get("/api/v1/screening/results", headers=admin_headers).json()["data"] == []


def test_suggest_job_tags_uses_model_response(client, admin_headers, monkeypatch):
    from app.screening import service

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"tags": ["B端产品经验", "AI产品经验", "跨团队协作"]}'}}]}

    monkeypatch.setattr(service.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(service.httpx, "post", lambda *args, **kwargs: FakeResponse())
    response = client.post(
        "/api/v1/screening/jobs/suggest-tags",
        headers=admin_headers,
        json={
            "name": "高级产品经理",
            "description": "负责企业 AI 产品从需求到上线",
            "required_skills": ["需求分析", "原型设计"],
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["tags"] == ["B端产品经验", "AI产品经验", "跨团队协作"]
