from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.models import CandidateApplication, JobOpening
from app.business.schemas import ApplicationCreate, ApplicationStatusUpdate, JobCreate, JobUpdate
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/recruitment", tags=["recruitment"])


def job_payload(row: JobOpening) -> dict:
    return {"id": row.id, "title": row.title, "department": row.department, "location": row.location, "employment_type": row.employment_type, "description": row.description, "requirements": row.requirements, "status": row.status, "created_at": row.created_at, "updated_at": row.updated_at}


def application_payload(row: CandidateApplication, db: Session) -> dict:
    job = db.get(JobOpening, row.job_id)
    return {"id": row.id, "job_id": row.job_id, "job_title": job.title if job else "", "name": row.name, "email": row.email, "phone": row.phone, "school": row.school, "major": row.major, "graduation_year": row.graduation_year, "resume_text": row.resume_text, "cover_note": row.cover_note, "status": row.status, "review_note": row.review_note, "reviewed_by": row.reviewed_by, "reviewed_at": row.reviewed_at, "created_at": row.created_at}


@router.get("/jobs")
def list_jobs(status_filter: str = Query("", alias="status"), _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    query = select(JobOpening).order_by(JobOpening.created_at.desc())
    if status_filter: query = query.where(JobOpening.status == status_filter)
    return {"data": [job_payload(row) for row in db.scalars(query).all()]}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(JobOpening, job_id)
    if row is None: raise HTTPException(status_code=404, detail="岗位不存在")
    return {"data": job_payload(row)}


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = JobOpening(**payload.model_dump()); db.add(row); db.commit(); db.refresh(row)
    return {"data": job_payload(row)}


@router.patch("/jobs/{job_id}")
def update_job(job_id: int, payload: JobUpdate, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(JobOpening, job_id)
    if row is None: raise HTTPException(status_code=404, detail="岗位不存在")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    row.updated_at = datetime.now(UTC); db.commit(); db.refresh(row)
    return {"data": job_payload(row)}


@router.post("/applications", status_code=status.HTTP_201_CREATED)
def create_application(payload: ApplicationCreate, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    job = db.get(JobOpening, payload.job_id)
    if job is None or job.status != "开放": raise HTTPException(status_code=404, detail="岗位不存在或已暂停")
    email = payload.email.strip().lower()
    if db.scalar(select(CandidateApplication).where(CandidateApplication.job_id == payload.job_id, CandidateApplication.email == email)):
        raise HTTPException(status_code=409, detail="该邮箱已投递此岗位")
    row = CandidateApplication(**payload.model_dump(exclude={"email"}), email=email)
    db.add(row); db.commit(); db.refresh(row)
    return {"data": application_payload(row, db)}


@router.get("/applications")
def list_applications(job_id: int | None = None, status_filter: str = Query("", alias="status"), _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    query = select(CandidateApplication).order_by(CandidateApplication.created_at.desc())
    if job_id is not None: query = query.where(CandidateApplication.job_id == job_id)
    if status_filter: query = query.where(CandidateApplication.status == status_filter)
    return {"data": [application_payload(row, db) for row in db.scalars(query).all()]}


@router.get("/applications/{application_id}")
def get_application(application_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(CandidateApplication, application_id)
    if row is None: raise HTTPException(status_code=404, detail="投递记录不存在")
    return {"data": application_payload(row, db)}


@router.patch("/applications/{application_id}/status")
def update_application_status(application_id: int, payload: ApplicationStatusUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    allowed = {"待初筛", "待面试", "已通过", "不合适"}
    if payload.status not in allowed: raise HTTPException(status_code=422, detail="无效的候选人状态")
    row = db.get(CandidateApplication, application_id)
    if row is None: raise HTTPException(status_code=404, detail="投递记录不存在")
    row.status = payload.status; row.review_note = payload.review_note; row.reviewed_by = user.display_name; row.reviewed_at = datetime.now(UTC)
    db.commit(); db.refresh(row)
    return {"data": application_payload(row, db)}
