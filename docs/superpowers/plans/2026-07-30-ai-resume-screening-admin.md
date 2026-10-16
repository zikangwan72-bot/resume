# AI Resume Screening Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Enterprise AI Suite 收缩为一个可上传 PDF/DOC/DOCX、按岗位标准执行 AI 简历筛选并支持人工复核的后台管理端。

**Architecture:** 保留现有 FastAPI、SQLAlchemy、Vue 3、Ant Design Vue、Pinia 和 API client。新增独立 screening 领域模型、文件文本提取和筛选 API；旧招聘/资产/审批后端暂不删除，但从前端导航和可见路由移除。AI 调用只发生在后端，结果必须结构化并记录运行状态。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、SQLite/Supabase PostgreSQL、pypdf、python-docx、Vue 3、TypeScript、Ant Design Vue、Pinia、Vitest-free Playwright E2E。

## Global Constraints

- 第一阶段保留旧招聘后端表、接口和历史数据，不删除数据库对象。
- AI 不自动录用或淘汰候选人，结果必须带人工复核状态。
- 模型密钥只放后端环境变量，不写入前端、不硬编码。
- 支持 PDF、DOC、DOCX；其它文件格式返回明确 400 错误。
- AI 未配置、解析失败、超时或非法 JSON 时，不写入虚假成功结果。
- 第一阶段不做多 Agent、向量数据库、长期记忆、自动通知和外部招聘同步。
- 页面继续使用现有 Vue 3、Ant Design Vue、Pinia 和 Axios client。

---

### Task 1: Add screening persistence and document extraction

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/business/models.py`
- Modify: `backend/app/db/seed.py`
- Create: `backend/app/screening/__init__.py`
- Create: `backend/app/screening/parser.py`
- Test: `backend/tests/test_screening_parser.py`

**Interfaces:**
- `extract_text(filename: str, content: bytes) -> tuple[str, str]` returns `(file_type, text)` or raises `UnsupportedResumeFile` / `ResumeParseError`.
- `ScreeningJob`, `ResumeDocument`, and `ScreeningResult` are SQLAlchemy models available to `Base.metadata.create_all`.

- [ ] **Step 1: Add parser dependencies and failing parser tests.**

Add `pypdf` and `python-docx` to `backend/requirements.txt`. Test PDF text extraction with a generated one-page PDF fixture, DOCX extraction with a generated document, and rejection of `.txt`.

- [ ] **Step 2: Run parser tests and verify the missing implementation fails.**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_screening_parser.py -q
```

Expected: import or implementation failure for `app.screening.parser`.

- [ ] **Step 3: Implement `extract_text`.**

Use `pypdf.PdfReader` for PDF, `docx.Document` for DOCX, and reject legacy binary `.doc` with a clear message that DOCX/PDF is required for this first version. Enforce a 10 MB input limit and return normalized text with repeated whitespace collapsed.

- [ ] **Step 4: Add screening models and seed one safe default job.**

Add JSON-backed fields for job criteria and result evidence. Add `initialize_screening_schema()` only for additive SQLite compatibility if a table already exists. Seed one inactive-by-default example job only when `screening_jobs` is empty; do not modify old recruitment seeds.

- [ ] **Step 5: Run parser and model initialization tests.**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_screening_parser.py -q
```

Expected: PASS.

### Task 2: Build screening API and AI result contract

**Files:**
- Create: `backend/app/screening/schemas.py`
- Create: `backend/app/screening/service.py`
- Create: `backend/app/screening/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/integrations/llm.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_screening_api.py`

**Interfaces:**
- `POST /api/v1/screening/jobs` creates a job with `name`, `description`, `required_skills`, `preferred_skills`, `rejection_conditions`, and `scoring_weights`.
- `GET/PATCH /api/v1/screening/jobs` lists and edits jobs.
- `POST /api/v1/screening/resumes` accepts multipart `file` and `job_id`.
- `POST /api/v1/screening/resumes/{resume_id}/screen` creates a structured result.
- `GET /api/v1/screening/results` filters by `job_id`, `human_status`, and `min_score`.
- `GET /api/v1/screening/results/{result_id}` returns full evidence and extracted text.
- `PATCH /api/v1/screening/results/{result_id}/review` saves `human_status` and `review_note`.
- `GET /api/v1/screening/dashboard` returns counts by job and status.

- [ ] **Step 1: Write API tests for job creation, upload validation, dashboard and review.**

Use `admin_headers` from existing test fixtures. Assert 201 for a valid job, 400 for `.txt`, 201 for a PDF upload, 409 or 422 for duplicate invalid state, and that review updates do not change the AI score.

- [ ] **Step 2: Run API tests and verify failure.**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_screening_api.py -q
```

Expected: FAIL because the screening router and models are not connected.

- [ ] **Step 3: Implement schemas, service and router.**

Require `resume:view` for reads and `resume:manage` for create/update/screen/review. Save uploads under a non-public backend `uploads/resumes/<uuid>.<ext>` directory, store only the generated path and metadata, and cap extracted text at 50,000 characters.

- [ ] **Step 4: Implement AI provider adapter with explicit fallback behavior.**

Reuse the existing DeepSeek/OpenAI-compatible settings. Prompt for the exact JSON contract:

```json
{"score":0,"recommendation":"待复核","summary":"","strengths":[],"gaps":[],"risk_flags":[],"evidence":[]}
```

Validate score range and arrays with Pydantic. When no provider is configured, return 503 and write an `AIRun` with `status="not_configured"`; when provider output is invalid, return 502 and write `status="failed"`. Only successful results create `ScreeningResult`.

- [ ] **Step 5: Register router and run backend checks.**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_screening_api.py -q
backend\.venv\Scripts\python.exe -m ruff check backend/app/screening backend/app/main.py backend/app/api/v1/router.py
```

Expected: PASS.

### Task 3: Replace the frontend with the AI screening admin surface

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/AppLayout.vue`
- Modify: `frontend/src/views/DashboardView.vue`
- Replace: `frontend/src/views/ResumeScreeningView.vue`
- Create: `frontend/src/views/screening/ScreeningJobsView.vue`
- Create: `frontend/src/views/screening/ScreeningResultView.vue`
- Modify: `frontend/src/views/LoginView.vue`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- `/dashboard` redirects/render the screening dashboard.
- `/modules/resume-screening` is the primary screening dashboard.
- `/screening/jobs` manages criteria.
- `/screening/results/:id` shows evidence and review controls.
- The side navigation contains only `AI 简历筛选`, `岗位标准`, and `AI 运行记录` plus profile/logout.

- [ ] **Step 1: Add an E2E acceptance test for the new admin shell.**

Create `frontend/tests/e2e/screening-admin.spec.ts` covering login, absence of old module labels, dashboard metrics, job-standard creation modal, upload control accept types, and result detail navigation.

- [ ] **Step 2: Run the new E2E test to capture the current failure.**

Run:

```powershell
cd frontend
npm run test:e2e -- tests/e2e/screening-admin.spec.ts
```

Expected: FAIL because the old navigation and old recruitment page are still rendered.

- [ ] **Step 3: Implement the admin layout and dashboard.**

Use a restrained operations-console visual direction: warm white canvas, deep ink navigation, amber AI accent, compact metrics, one prominent upload panel, and dense result table. Keep controls icon-supported and keyboard accessible. Dashboard calls `/screening/dashboard`, `/screening/jobs`, and `/screening/results`.

- [ ] **Step 4: Implement jobs and result detail views.**

Jobs view supports create/edit/deactivate and stores criteria as arrays or JSON fields. Result detail shows score, recommendation, summary, strengths, gaps, risk flags, evidence, extracted text, and a review form. Upload form uses `multipart/form-data` and supports multiple files sequentially with visible success/failure per file.

- [ ] **Step 5: Remove old frontend entry points.**

Remove public recruitment and mobile inventory routes, remove approval/asset/service-desk/admin menu groups, update login copy and default redirect, and keep old files unused so old backend tests/data remain intact.

- [ ] **Step 6: Run typecheck, build and E2E.**

Run:

```powershell
cd frontend
npm run typecheck
npm run build
npm run test:e2e -- tests/e2e/screening-admin.spec.ts
```

Expected: PASS.

### Task 4: End-to-end verification and handoff

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Test: `backend/tests/test_screening_api.py`
- Test: `frontend/tests/e2e/screening-admin.spec.ts`

- [ ] **Step 1: Restart services with the fixed `scripts/restart.ps1`.**

Run:

```powershell
./scripts/restart.ps1
```

Verify `http://127.0.0.1:5173/modules/resume-screening` returns 200 and `/api/v1/health` returns `healthy`.

- [ ] **Step 2: Manually verify the first user path.**

Log in as `admin@demo.local`, create one job standard, upload one PDF/DOCX, trigger screening, inspect the result evidence, then save a human review note.

- [ ] **Step 3: Run the complete project check.**

Run:

```powershell
./scripts/check.ps1
```

Record any pre-existing unrelated test failures separately; do not hide them behind the new feature.

- [ ] **Step 4: Update docs and hand off.**

Document the new routes, environment variables, accepted file types, AI-not-configured behavior, and the exact manual acceptance sequence. Report remaining gaps before any second-phase Agent work.
