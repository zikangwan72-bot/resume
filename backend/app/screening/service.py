import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.business.models import ResumeDocument, ScreeningJob, ScreeningResult
from app.db.models import AIRun
from app.integrations import llm
from app.integrations.storage import StorageUploadError, upload_bytes
from app.core.config import settings
from app.screening.parser import ResumeParseError, UnsupportedResumeFile, extract_text
from app.screening.schemas import ReviewUpdate, ScreeningJobCreate, ScreeningJobUpdate

UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "resumes"


def job_payload(job: ScreeningJob) -> dict:
    return {
        key: getattr(job, key)
        for key in (
            "id",
            "name",
            "description",
            "required_skills",
            "preferred_skills",
            "rejection_conditions",
            "scoring_weights",
            "status",
            "created_at",
            "updated_at",
        )
    }


def result_payload(result: ScreeningResult, resume: ResumeDocument, job: ScreeningJob) -> dict:
    return {
        "id": result.id,
        "resume_id": result.resume_id,
        "job_id": result.job_id,
        "filename": resume.filename,
        "job_name": job.name,
        "score": result.score,
        "recommendation": result.recommendation,
        "summary": result.summary,
        "strengths": result.strengths,
        "gaps": result.gaps,
        "risk_flags": result.risk_flags,
        "evidence": result.evidence,
        "human_status": result.human_status,
        "review_note": result.review_note,
        "created_at": result.created_at,
        "extracted_text": resume.extracted_text,
    }


def create_job(db: Session, payload: ScreeningJobCreate) -> ScreeningJob:
    job = ScreeningJob(**payload.model_dump())
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="岗位筛选标准名称已存在") from exc
    db.refresh(job)
    return job


def update_job(db: Session, job: ScreeningJob, payload: ScreeningJobUpdate) -> ScreeningJob:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="岗位筛选标准名称已存在") from exc
    db.refresh(job)
    return job


def delete_job(db: Session, job: ScreeningJob) -> None:
    result_count = db.scalar(
        select(func.count(ScreeningResult.id)).where(ScreeningResult.job_id == job.id)
    ) or 0
    if result_count:
        raise HTTPException(
            status_code=409,
            detail="该岗位标准已有筛选结果，不能删除。请停用后保留历史记录。",
        )
    db.delete(job)
    db.commit()


def suggest_job_tags(payload: dict) -> tuple[list[str], str, str]:
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
        raise llm.LLMNotConfiguredError("AI 未配置，暂时无法生成岗位标签")

    prompt = {
        "job": payload,
        "rules": [
            "只根据岗位名称、岗位画像和必须技能生成标签",
            "标签必须是简体中文短语，每个不超过 20 个字",
            "标签用于简历筛选加分依据，不得使用年龄、性别、民族等受保护属性",
            "只返回 3 到 8 个最有区分度的标签",
        ],
        "output_contract": {"tags": "简体中文字符串数组"},
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
                    {"role": "system", "content": "你是招聘岗位分析助手，只返回合法 JSON。"},
                    {"role": "user", "content": json.dumps(jsonable_encoder(prompt), ensure_ascii=False)},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if isinstance(content, str) and content.startswith("```"):
            content = content.strip().removeprefix("```json").removesuffix("```").strip()
        tags = json.loads(content).get("tags") if isinstance(content, str) else content.get("tags")
        if not isinstance(tags, list) or not all(isinstance(item, str) and item.strip() for item in tags):
            raise ValueError("tags invalid")
        unique_tags = list(dict.fromkeys(item.strip() for item in tags))[:8]
        if not 3 <= len(unique_tags) <= 8:
            raise ValueError("tag count invalid")
        return unique_tags, provider, model
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise llm.LLMRequestError("AI 岗位标签生成失败") from exc


async def upload_resume(db: Session, upload: UploadFile) -> ResumeDocument:
    content = await upload.read()
    try:
        file_type, extracted_text = extract_text(upload.filename or "", content)
    except (UnsupportedResumeFile, ResumeParseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    relative_path = Path("uploads") / "resumes" / f"{uuid4()}.{file_type}"
    storage_key = relative_path.as_posix()
    content_type = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(file_type, "application/octet-stream")
    storage_path = None
    try:
        storage_path = upload_bytes(storage_key, content, content_type)
    except StorageUploadError as exc:
        if settings.app_env.lower() == "production":
            raise HTTPException(status_code=503, detail="云端文件存储不可用，请稍后重试") from exc
    if storage_path is None:
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        target = Path(__file__).resolve().parents[2] / relative_path
        target.write_bytes(content)
        storage_path = str(relative_path)
    resume = ResumeDocument(
        filename=upload.filename or "resume",
        file_type=file_type,
        storage_path=storage_path,
        extracted_text=extracted_text,
        parse_status="parsed",
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def screen_resume(db: Session, resume: ResumeDocument, job: ScreeningJob) -> ScreeningResult:
    started = time.perf_counter()
    run = AIRun(
        module="resume-screening", task_type="screening", status="running", human_review=True
    )
    db.add(run)
    db.flush()
    try:
        raw, provider, model = llm.request_screening(job_payload(job), resume.extracted_text)
        score = float(raw["score"])
        if not 0 <= score <= 100:
            raise ValueError("score out of range")
        fields = {
            key: raw[key]
            for key in ("recommendation", "summary", "strengths", "gaps", "risk_flags", "evidence")
        }
        list_fields = ("strengths", "gaps", "risk_flags", "evidence")
        if not all(
            isinstance(fields[key], list) and all(isinstance(item, str) for item in fields[key])
            for key in list_fields
        ):
            raise ValueError("array field invalid")
    except llm.LLMNotConfiguredError as exc:
        run.status = "not_configured"
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (llm.LLMRequestError, KeyError, TypeError, ValueError) as exc:
        run.status = "failed"
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        db.commit()
        raise HTTPException(status_code=502, detail="AI 返回结果无效，未生成筛选结果") from exc
    run.status = "success"
    run.model = f"{provider}:{model}"
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    result = ScreeningResult(resume_id=resume.id, job_id=job.id, score=score, **fields)
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def review_result(db: Session, result: ScreeningResult, payload: ReviewUpdate) -> ScreeningResult:
    result.human_status = payload.human_status
    result.review_note = payload.review_note
    db.commit()
    db.refresh(result)
    return result


def dashboard(db: Session) -> dict:
    total_resumes, total, pending, active_jobs = db.execute(
        select(
            select(func.count(ResumeDocument.id)).scalar_subquery(),
            select(func.count(ScreeningResult.id)).scalar_subquery(),
            select(func.count(ScreeningResult.id))
            .where(ScreeningResult.human_status == "pending_review")
            .scalar_subquery(),
            select(func.count(ScreeningJob.id))
            .where(ScreeningJob.status == "active")
            .scalar_subquery(),
        )
    ).one()
    by_job = db.execute(
        select(ScreeningJob.id, ScreeningJob.name, func.count(ScreeningResult.id))
        .outerjoin(ScreeningResult, ScreeningResult.job_id == ScreeningJob.id)
        .group_by(ScreeningJob.id, ScreeningJob.name)
    ).all()
    job_distribution = [
        {"id": row[0], "job_id": row[0], "name": row[1], "job_name": row[1], "count": row[2]}
        for row in by_job
    ]
    return {
        "job_count": active_jobs or 0,
        "resume_count": total_resumes or 0,
        "pending_count": pending or 0,
        "reviewed_count": total - pending,
        "job_distribution": job_distribution,
        "total_results": total,
        "pending_review": pending,
        "reviewed": total - pending,
        "by_job": job_distribution,
    }
