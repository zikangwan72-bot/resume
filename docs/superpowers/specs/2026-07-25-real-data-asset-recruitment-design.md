# 资产管理与招聘系统真实数据 MVP 设计

日期：2026-07-25

## 目标

将全资产管理和招聘系统从前端展示型页面改造成可操作的业务 MVP。业务数据必须由 FastAPI 写入 SQLite，并由前端通过 API 读取；页面不得再维护业务假数据数组。

本阶段不接入 AI，不重做企业 IT 服务台，不做复杂组织权限和云端文件存储。

## 范围

### 全资产管理

- 资产总览
- 资产台账查询、新增、编辑、删除
- 盘点任务创建、查看、更新进度
- 盘点记录录入
- 差异/异常记录生成与处置归档

### 招聘系统

- 学生端开放岗位列表
- 岗位详情
- 学生在线投递
- 我的投递记录
- 管理端岗位创建、编辑、开放/暂停
- 管理端候选人池
- 候选人详情
- 人工初筛和状态流转

## 页面与角色

当前沿用本地演示登录。学生端和管理端使用不同页面入口，不依赖复杂权限系统。

| 页面 | 使用者 | 主要动作 |
|---|---|---|
| 资产总览/台账/盘点/异常 | 平台管理员 | 管理资产全生命周期 |
| 招聘学生端 | 学生 | 浏览岗位、查看详情、提交投递、查看投递记录 |
| 招聘管理端 | 招聘管理员 | 管理岗位、查看候选人、更新筛选状态 |

## 数据模型

### Asset

- `id`
- `asset_code`
- `name`
- `category`
- `department`
- `owner`
- `location`
- `status`
- `purchase_date`
- `value`
- `last_inventory_at`
- `created_at`
- `updated_at`

### InventoryTask

- `id`
- `name`
- `scope`
- `owner`
- `status`
- `due_date`
- `created_at`
- `updated_at`

### InventoryRecord

- `id`
- `task_id`
- `asset_id`
- `result`
- `actual_location`
- `remark`
- `checked_by`
- `checked_at`

### AssetException

- `id`
- `asset_id`
- `inventory_record_id`
- `type`
- `description`
- `status`
- `resolution`
- `resolved_by`
- `resolved_at`
- `created_at`

### JobOpening

- `id`
- `title`
- `department`
- `location`
- `employment_type`
- `description`
- `requirements`
- `status`
- `created_at`
- `updated_at`

### CandidateApplication

- `id`
- `job_id`
- `name`
- `email`
- `phone`
- `school`
- `major`
- `graduation_year`
- `resume_text`
- `cover_note`
- `status`
- `review_note`
- `reviewed_by`
- `reviewed_at`
- `created_at`

## API 边界

### 资产 API

- `GET /api/v1/assets/summary`
- `GET /api/v1/assets`
- `POST /api/v1/assets`
- `PATCH /api/v1/assets/{id}`
- `DELETE /api/v1/assets/{id}`
- `GET /api/v1/assets/inventory-tasks`
- `POST /api/v1/assets/inventory-tasks`
- `PATCH /api/v1/assets/inventory-tasks/{id}`
- `GET /api/v1/assets/exceptions`
- `POST /api/v1/assets/exceptions/{id}/resolve`

### 招聘 API

- `GET /api/v1/recruitment/jobs`
- `POST /api/v1/recruitment/jobs`
- `PATCH /api/v1/recruitment/jobs/{id}`
- `GET /api/v1/recruitment/jobs/{id}`
- `POST /api/v1/recruitment/applications`
- `GET /api/v1/recruitment/applications`
- `GET /api/v1/recruitment/applications/{id}`
- `PATCH /api/v1/recruitment/applications/{id}/status`

所有写接口完成后提交数据库事务；资源不存在返回 404；参数校验失败返回 422；未登录返回 401。

## 前端结构

前端按业务角色和工作流拆分组件，不使用一个混合大页面承载所有操作。

- `AssetOverviewView`
- `AssetLedgerView`
- `InventoryTaskView`
- `AssetExceptionView`
- `RecruitmentStudentView`
- `RecruitmentApplicationsView`
- `RecruitmentAdminView`
- `RecruitmentJobEditor`
- `CandidateDetailDrawer`

新增和编辑使用 Ant Design Vue Drawer/Modal；列表使用 Table；状态使用 Tag；详情使用 Descriptions；提交操作显示成功/失败反馈。

## 数据流与错误处理

```text
用户操作 -> Vue 表单校验 -> Axios API -> FastAPI 校验 -> SQLAlchemy -> SQLite
                                      <- JSON 响应 <- 提交事务/错误处理
```

- 页面加载失败显示错误提示和重试按钮。
- 新增、编辑、删除成功后重新请求当前列表，避免前端状态与数据库不一致。
- 删除前二次确认。
- 招聘投递防止同一邮箱重复投递同一岗位。
- 资产编号唯一；重复编号由后端拒绝。
- 管理员状态更新必须写入审核人和审核时间。

## 测试策略

### 后端

- 数据库初始化与种子数据只负责首次安装，不覆盖已有业务数据。
- 测试资产新增、列表筛选、盘点任务创建、异常归档。
- 测试岗位新增、学生投递、重复投递拒绝、管理员状态流转。

### 前端

- 页面能分别访问学生端和管理端。
- 资产新增后出现在台账。
- 创建盘点任务后出现在盘点工作台。
- 学生提交投递后，管理端候选人池能看到对应记录。
- 管理员更新候选人状态后，页面显示最新状态。

## 后续 AI 接入位置

本阶段先保留接口边界，后续不改变核心业务模型：

- 资产异常：接入异常解释和处置建议。
- 招聘候选人：接入简历解析、岗位匹配、可解释评分。
- 所有 AI 结果进入人工复核，不直接修改最终业务状态。

## 明确不做

- 不在 Vue 中硬编码业务列表。
- 不把页面假数据称为真实业务数据。
- 不接入外部招聘网站的真实候选人隐私数据。
- 不在本阶段实现 AI 自动拒绝、自动录用或自动资产处置。
