from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.models import ResumeDocument, ScreeningJob, ScreeningResult
from app.core.security import require_permission
from app.db.database import get_db
from app.db.models import User
from app.integrations import llm
from app.screening.schemas import ReviewUpdate, ScreeningJobCreate, ScreeningJobUpdate, ScreeningTagSuggestionRequest
from app.screening.service import (
    create_job,
    dashboard,
    delete_job,
    job_payload,
    result_payload,
    review_result,
    screen_resume,
    suggest_job_tags,
    update_job,
    upload_resume,
)

router = APIRouter(prefix="/screening", tags=["screening"])


def get_job_or_404(db: Session, job_id: int) -> ScreeningJob:
    job = db.get(ScreeningJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="岗位筛选标准不存在")
    return job


@router.get("/jobs")
def list_jobs(
    _: User = Depends(require_permission("resume:view")), db: Session = Depends(get_db)
) -> dict:
    return {
        "data": [
            job_payload(job)
            for job in db.scalars(select(ScreeningJob).order_by(ScreeningJob.id)).all()
        ]
    }


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job_route(
    payload: ScreeningJobCreate,
    _: User = Depends(require_permission("resume:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return {"data": job_payload(create_job(db, payload))}


@router.patch("/jobs/{job_id}")
def update_job_route(
    job_id: int,
    payload: ScreeningJobUpdate,
    _: User = Depends(require_permission("resume:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return {"data": job_payload(update_job(db, get_job_or_404(db, job_id), payload))}


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_route(
    job_id: int,
    _: User = Depends(require_permission("resume:manage")),
    db: Session = Depends(get_db),
) -> None:
    delete_job(db, get_job_or_404(db, job_id))


@router.post("/jobs/suggest-tags")
def suggest_tags_route(
    payload: ScreeningTagSuggestionRequest,
    _: User = Depends(require_permission("resume:manage")),
) -> dict:
    try:
        tags, provider, model = suggest_job_tags(payload.model_dump())
    except llm.LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except llm.LLMRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"data": {"tags": tags, "provider": provider, "model": model}}


@router.post("/resumes", status_code=status.HTTP_201_CREATED)
async def upload_resume_route(
    file: UploadFile = File(...),
    job_id: int | None = Form(default=None),
    _: User = Depends(require_permission("resume:manage")),
    db: Session = Depends(get_db),
) -> dict:
    if job_id is not None:
        get_job_or_404(db, job_id)
    resume = await upload_resume(db, file)
    return {
        "data": {
            "id": resume.id,
            "filename": resume.filename,
            "file_type": resume.file_type,
            "parse_status": resume.parse_status,
            "job_id": job_id,
        }
    }


@router.post("/resumes/{resume_id}/screen", status_code=status.HTTP_201_CREATED)
def screen_resume_route(
    resume_id: int,
    job_id: int = Query(...),
    _: User = Depends(require_permission("resume:manage")),
    db: Session = Depends(get_db),
) -> dict:
    resume = db.get(ResumeDocument, resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    job = get_job_or_404(db, job_id)
    return {"data": result_payload(screen_resume(db, resume, job), resume, job)}


@router.get("/results")
def list_results(
    job_id: int | None = None,
    human_status: str | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    _: User = Depends(require_permission("resume:view")),
    db: Session = Depends(get_db),
) -> dict:
    query = (
        select(ScreeningResult, ResumeDocument, ScreeningJob)
        .join(ResumeDocument, ResumeDocument.id == ScreeningResult.resume_id)
        .join(ScreeningJob, ScreeningJob.id == ScreeningResult.job_id)
    )
    if job_id is not None:
        query = query.where(ScreeningResult.job_id == job_id)
    if human_status:
        query = query.where(ScreeningResult.human_status == human_status)
    if min_score is not None:
        query = query.where(ScreeningResult.score >= min_score)
    rows = db.execute(query.order_by(ScreeningResult.created_at.desc())).all()
    return {"data": [result_payload(result, resume, job) for result, resume, job in rows]}


@router.get("/results/{result_id}")
def get_result(
    result_id: int,
    _: User = Depends(require_permission("resume:view")),
    db: Session = Depends(get_db),
) -> dict:
    row = db.execute(
        select(ScreeningResult, ResumeDocument, ScreeningJob)
        .join(ResumeDocument, ResumeDocument.id == ScreeningResult.resume_id)
        .join(ScreeningJob, ScreeningJob.id == ScreeningResult.job_id)
        .where(ScreeningResult.id == result_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="筛选结果不存在")
    return {"data": result_payload(*row)}


@router.patch("/results/{result_id}/review")
def review(
    result_id: int,
    payload: ReviewUpdate,
    _: User = Depends(require_permission("resume:manage")),
    db: Session = Depends(get_db),
) -> dict:
    result = db.get(ScreeningResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="筛选结果不存在")
    review_result(db, result, payload)
    row = db.execute(
        select(ResumeDocument, ScreeningJob)
        .where(ResumeDocument.id == result.resume_id)
        .where(ScreeningJob.id == result.job_id)
        .select_from(ResumeDocument)
        .join(ScreeningJob, ScreeningJob.id == result.job_id)
    ).first()
    return {"data": result_payload(result, row[0], row[1])}


@router.get("/dashboard")
def dashboard_route(
    _: User = Depends(require_permission("resume:view")), db: Session = Depends(get_db)
) -> dict:
    return {"data": dashboard(db)}


@router.get("/overview")
def overview_route(
    _: User = Depends(require_permission("resume:view")), db: Session = Depends(get_db)
) -> dict:
    jobs = db.scalars(select(ScreeningJob).order_by(ScreeningJob.id)).all()
    rows = db.execute(
        select(ScreeningResult, ResumeDocument, ScreeningJob)
        .join(ResumeDocument, ResumeDocument.id == ScreeningResult.resume_id)
        .join(ScreeningJob, ScreeningJob.id == ScreeningResult.job_id)
        .where(ScreeningResult.human_status == "pending_review")
        .order_by(ScreeningResult.created_at.desc())
    ).all()
    return {
        "data": {
            "summary": dashboard(db),
            "jobs": [job_payload(job) for job in jobs],
            "pending_results": [
                result_payload(result, resume, job) for result, resume, job in rows
            ],
        }
    }
