# API Contract v1

统一响应：成功 `{ "data": ... }`；失败 `{ "detail": "可理解的错误信息" }`。

## 资产

`Asset`: `id`, `asset_code`, `name`, `category`, `department`, `owner`, `location`, `status`, `purchase_date`, `value`, `last_inventory_at`, `created_at`, `updated_at`。

状态：`在用`、`闲置`、`维修中`、`待处置`。

- `GET /api/v1/assets?keyword=&status=&category=&department=`
- `POST /api/v1/assets`
- `PATCH /api/v1/assets/{id}`
- `DELETE /api/v1/assets/{id}`
- `GET /api/v1/assets/summary`

## 盘点

`InventoryTask`: `id`, `name`, `scope`, `owner`, `status`, `due_date`, `total_count`, `checked_count`, `exception_count`, `created_at`, `updated_at`。

状态：`草稿`、`进行中`、`已完成`。

- `GET /api/v1/assets/inventory-tasks`
- `POST /api/v1/assets/inventory-tasks`
- `PATCH /api/v1/assets/inventory-tasks/{id}`

## 异常

`AssetException`: `id`, `asset_id`, `asset_code`, `asset_name`, `department`, `type`, `description`, `status`, `resolution`, `resolved_by`, `resolved_at`, `created_at`。

状态：`待核实`、`处理中`、`已归档`。

- `GET /api/v1/assets/exceptions`
- `POST /api/v1/assets/exceptions/{id}/resolve`，请求体 `{ "resolution": "..." }`

## 招聘

`JobOpening`: `id`, `title`, `department`, `location`, `employment_type`, `description`, `requirements`, `status`, `created_at`, `updated_at`。

状态：`开放`、`暂停`。

- `GET /api/v1/recruitment/jobs?status=`
- `GET /api/v1/recruitment/jobs/{id}`
- `POST /api/v1/recruitment/jobs`
- `PATCH /api/v1/recruitment/jobs/{id}`

`CandidateApplication`: `id`, `job_id`, `job_title`, `name`, `email`, `phone`, `school`, `major`, `graduation_year`, `resume_text`, `cover_note`, `status`, `review_note`, `reviewed_by`, `reviewed_at`, `created_at`。

状态：`待初筛`、`待面试`、`已通过`、`不合适`。

- `POST /api/v1/recruitment/applications`
- `GET /api/v1/recruitment/applications?job_id=&status=`
- `GET /api/v1/recruitment/applications/{id}`
- `PATCH /api/v1/recruitment/applications/{id}/status`，请求体 `{ "status": "待面试", "review_note": "..." }`

## 约束

- 所有接口需要现有 Bearer 登录。
- 学生端只展示开放岗位。
- `asset_code` 重复返回 409。
- `(job_id, email)` 重复投递返回 409。
- 管理员状态更新自动记录当前登录人和时间。
