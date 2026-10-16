from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.models import CandidateApplication, JobOpening
from app.business.schemas import ApplicationCreate, ApplicationStatusUpdate, JobCreate, JobUpdate
from app.core.config import settings
from app.core.security import require_permission
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/recruitment", tags=["recruitment"])


def job_payload(row: JobOpening) -> dict:
    return {"id": row.id, "title": row.title, "department": row.department, "location": row.location, "employment_type": row.employment_type, "description": row.description, "requirements": row.requirements, "status": row.status, "created_at": row.created_at, "updated_at": row.updated_at}


def application_payload(row: CandidateApplication, db: Session) -> dict:
    job = db.get(JobOpening, row.job_id)
    return {"id": row.id, "job_id": row.job_id, "job_title": job.title if job else "", "name": row.name, "email": row.email, "phone": row.phone, "school": row.school, "major": row.major, "graduation_year": row.graduation_year, "resume_text": row.resume_text, "cover_note": row.cover_note, "status": row.status, "ai_status": row.ai_status, "ai_score": row.ai_score, "ai_summary": row.ai_summary, "ai_evidence": row.ai_evidence, "review_note": row.review_note, "reviewed_by": row.reviewed_by, "reviewed_at": row.reviewed_at, "created_at": row.created_at}


def local_screening(job: JobOpening, row: CandidateApplication) -> dict:
    resume = f"{row.resume_text} {row.cover_note or ''} {row.school or ''} {row.major or ''}".lower()
    requirement_text = f"{job.title} {job.description} {job.requirements}".lower()
    dimensions = [
        ("岗位技能", ["sql", "python", "ai", "rag", "llm", "数据", "产品", "workflow", "工作流"]),
        ("业务理解", ["b端", "企业", "流程", "审批", "资产", "招聘", "指标", "需求"]),
        ("交付经验", ["项目", "原型", "上线", "迭代", "dashboard", "api", "fastapi", "vue"]),
        ("沟通协作", ["沟通", "协作", "stakeholder", "访谈", "汇报", "面试"]),
    ]
    evidence = []
    total = 0
    for name, keywords in dimensions:
        hits = [keyword for keyword in keywords if keyword in resume]
        requirement_hits = [keyword for keyword in keywords if keyword in requirement_text]
        score = min(100, 45 + len(hits) * 12 + len(set(hits) & set(requirement_hits)) * 8)
        total += score
        evidence.append({"dimension": name, "score": score, "matched_keywords": hits[:6], "requirement_keywords": requirement_hits[:6]})
    score = round(total / len(dimensions), 1)
    gaps = [item["dimension"] for item in evidence if item["score"] < 70]
    return {
        "provider": "local-rules",
        "score": score,
        "summary": f"候选人与「{job.title}」匹配度 {score}。建议招聘人员重点核验：{('、'.join(gaps) or '岗位动机和项目真实性')}。",
        "evidence": {
            "dimensions": evidence,
            "strengths": [item["dimension"] for item in evidence if item["score"] >= 75],
            "gaps": gaps,
            "recommended_stage": "待面试" if score >= 75 else "人才库" if score >= 65 else "不合适",
            "risk_flags": ["简历材料较少，需要面试核验"] if len(resume.strip()) < 80 else [],
            "interview_questions": [
                "请讲一个你把业务需求拆成产品方案的项目。",
                "如果简历解析结果与人工判断冲突，你会怎样校准筛选标准？",
                "请说明你对岗位核心业务流程的理解和可量化交付。"
            ],
            "human_review_required": True,
            "decision_policy": "AI只提供岗位相关建议，不能自动录用或淘汰候选人。",
        },
    }


def deepseek_screening(job: JobOpening, row: CandidateApplication) -> dict | None:
    if not settings.deepseek_api_key:
        return None
    prompt = (
        "你是企业招聘简历筛选助手。只根据岗位要求和候选人材料输出JSON，"
        "字段：score(0-100), summary, strengths数组, gaps数组, recommended_stage, risk_flags数组, interview_questions数组。"
        "不得使用年龄、性别、民族等受保护属性。最终决策必须人工复核。\n\n"
        f"岗位：{job.title}\n部门：{job.department}\n描述：{job.description}\n要求：{job.requirements}\n\n"
        f"候选人：{row.name}\n学校：{row.school}\n专业：{row.major}\n简历：{row.resume_text}\n求职说明：{row.cover_note or ''}"
    )
    try:
        response = httpx.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": settings.deepseek_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
            },
            timeout=20,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        import json

        parsed = json.loads(content)
        return {
            "provider": "deepseek",
            "score": float(parsed.get("score", 0)),
            "summary": str(parsed.get("summary", "")),
        "evidence": {
            "strengths": parsed.get("strengths", []),
            "gaps": parsed.get("gaps", []),
            "recommended_stage": parsed.get("recommended_stage", "待面试" if float(parsed.get("score", 0)) >= 75 else "人才库"),
            "risk_flags": parsed.get("risk_flags", []),
            "interview_questions": parsed.get("interview_questions", []),
            "human_review_required": True,
            "decision_policy": "AI只提供岗位相关建议，不能自动录用或淘汰候选人。",
        },
    }
    except Exception:
        return None


def persist_application(payload: ApplicationCreate, db: Session) -> CandidateApplication:
    job = db.get(JobOpening, payload.job_id)
    if job is None or job.status != "开放":
        raise HTTPException(status_code=404, detail="岗位不存在或已暂停")
    email = payload.email.strip().lower()
    if db.scalar(select(CandidateApplication).where(CandidateApplication.job_id == payload.job_id, CandidateApplication.email == email)):
        raise HTTPException(status_code=409, detail="该邮箱已投递此岗位")
    row = CandidateApplication(**payload.model_dump(exclude={"email"}), email=email)
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.get("/public/jobs")
def list_public_jobs(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(JobOpening).where(JobOpening.status == "开放").order_by(JobOpening.created_at.desc())).all()
    return {"data": [job_payload(row) for row in rows]}


@router.post("/public/applications", status_code=status.HTTP_201_CREATED)
def create_public_application(payload: ApplicationCreate, db: Session = Depends(get_db)) -> dict:
    row = persist_application(payload, db)
    return {"data": {"application_id": row.id, "status": row.status}}


@router.get("/jobs")
def list_jobs(status_filter: str = Query("", alias="status"), _: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> dict:
    query = select(JobOpening).order_by(JobOpening.created_at.desc())
    if status_filter: query = query.where(JobOpening.status == status_filter)
    return {"data": [job_payload(row) for row in db.scalars(query).all()]}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, _: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(JobOpening, job_id)
    if row is None: raise HTTPException(status_code=404, detail="岗位不存在")
    return {"data": job_payload(row)}


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, _: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> dict:
    row = JobOpening(**payload.model_dump()); db.add(row); db.commit(); db.refresh(row)
    return {"data": job_payload(row)}


@router.patch("/jobs/{job_id}")
def update_job(job_id: int, payload: JobUpdate, _: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(JobOpening, job_id)
    if row is None: raise HTTPException(status_code=404, detail="岗位不存在")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    row.updated_at = datetime.now(UTC); db.commit(); db.refresh(row)
    return {"data": job_payload(row)}


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, _: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> None:
    row = db.get(JobOpening, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    has_applications = db.scalar(select(CandidateApplication.id).where(CandidateApplication.job_id == job_id).limit(1))
    if has_applications is not None:
        raise HTTPException(status_code=409, detail="已有候选人投递的岗位不能删除，请关闭岗位保留历史记录")
    db.delete(row)
    db.commit()


@router.post("/applications", status_code=status.HTTP_201_CREATED)
def create_application(payload: ApplicationCreate, _: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> dict:
    row = persist_application(payload, db)
    return {"data": application_payload(row, db)}


@router.get("/applications")
def list_applications(job_id: int | None = None, status_filter: str = Query("", alias="status"), _: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> dict:
    query = select(CandidateApplication).order_by(CandidateApplication.created_at.desc())
    if job_id is not None: query = query.where(CandidateApplication.job_id == job_id)
    if status_filter: query = query.where(CandidateApplication.status == status_filter)
    return {"data": [application_payload(row, db) for row in db.scalars(query).all()]}


@router.get("/applications/{application_id}")
def get_application(application_id: int, _: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(CandidateApplication, application_id)
    if row is None: raise HTTPException(status_code=404, detail="投递记录不存在")
    return {"data": application_payload(row, db)}


@router.patch("/applications/{application_id}/status")
def update_application_status(application_id: int, payload: ApplicationStatusUpdate, user: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> dict:
    allowed = {"待初筛", "待面试", "面试中", "Offer", "已录用", "已通过", "不合适", "人才库"}
    if payload.status not in allowed: raise HTTPException(status_code=422, detail="无效的候选人状态")
    row = db.get(CandidateApplication, application_id)
    if row is None: raise HTTPException(status_code=404, detail="投递记录不存在")
    row.status = payload.status; row.review_note = payload.review_note; row.reviewed_by = user.display_name; row.reviewed_at = datetime.now(UTC)
    db.commit(); db.refresh(row)
    return {"data": application_payload(row, db)}


@router.post("/applications/{application_id}/screen")
def screen_application(application_id: int, _: User = Depends(require_permission("recruitment:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(CandidateApplication, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    job = db.get(JobOpening, row.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    result = deepseek_screening(job, row) or local_screening(job, row)
    row.ai_status = "已筛选"
    row.ai_score = result["score"]
    row.ai_summary = result["summary"]
    row.ai_evidence = result["evidence"] | {"provider": result["provider"]}
    db.commit()
    db.refresh(row)
    return {"data": application_payload(row, db)}
