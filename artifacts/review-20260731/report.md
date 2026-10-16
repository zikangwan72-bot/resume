# Enterprise AI Suite 整体 Debug / Code Review

日期：2026-07-31

范围：当前工作区前后端源码、运行中的 `5173/8000` 页面、平台管理员/招聘管理员/资产管理员/员工账号、桌面与 390px 移动端、主要业务路由和完整自动化测试。

## 阻塞问题

### [P0] 演示登录接口在生产环境可直接获取任意角色令牌

- 位置：`backend/app/api/v1/router.py:133`、`backend/app/api/v1/router.py:165`、`backend/app/core/config.py:8`
- 复现：不带认证请求 `GET /api/v1/auth/demo-accounts` 可得到全部账号和统一密码；随后 `POST /api/v1/auth/demo-login` 传入 `{"role":"platform_admin"}` 即可返回管理员 JWT。
- 影响：当前接口没有 `APP_ENV` 保护，也没有管理员授权。只要 API 可访问，外部用户可以直接获得平台管理员身份。生产上线前必须关闭演示账号接口或放到显式 demo 环境，并强制使用随机 JWT secret。

### [P1] 招聘 B/C 端前端不可达

- 位置：[frontend/src/router/index.ts:25](/C:/Users/%E4%B8%87%E5%B0%8F%E9%A5%B1/Desktop/pythoncode/enterprise-ai-suite/frontend/src/router/index.ts:25)
- 现状：`RecruitmentAdminView.vue` 和 `RecruitmentStudentView.vue` 存在，招聘 API 也存在，但路由表没有 `/recruitment/admin` 或 `/recruitment/student`。实际访问两者都落到“页面不存在”。仓库中的 UAT 仍直接访问 `/recruitment/admin`，见 [business-acceptance.spec.ts:23](/C:/Users/%E4%B8%87%E5%B0%8F%E9%A5%B1/Desktop/pythoncode/enterprise-ai-suite/frontend/tests/uat/business-acceptance.spec.ts:23)。
- 影响：之前要求的招聘管理端和候选人投递端目前无法从浏览器进入，岗位/候选人/投递闭环不能验收。

### [P1] 盘点任务状态不满足“按任务刷新”规则

- 位置：[backend/app/business/asset_router.py:72](/C:/Users/%E4%B8%87%E5%B0%8F%E9%A5%B1/Desktop/pythoncode/enterprise-ai-suite/backend/app/business/asset_router.py:72)
- 现状：找不到进行中任务时，`active_record_payload()` 会回退到历史已完成记录；扫码接口随后会把历史结果当成当前记录返回。实际云端数据还存在多个同时“进行中”的任务，二维码只能按记录 ID 选最新任务。
- 影响：没有新任务时员工可能看到旧任务“已完成”，多个进行中任务时员工无法明确当前盘点任务；这与“同一资产在新任务可重新盘点、旧任务不影响新任务”的规则冲突。

### [P1] Supabase 健康状态通过，但业务文件仍写本地磁盘/数据库

- 位置：[backend/app/screening/service.py:154](/C:/Users/%E4%B8%87%E5%B0%8F%E9%A5%B1/Desktop/pythoncode/enterprise-ai-suite/backend/app/screening/service.py:154)、[backend/app/api/v1/router.py:292](/C:/Users/%E4%B8%87%E5%B0%8F%E9%A5%B1/Desktop/pythoncode/enterprise-ai-suite/backend/app/api/v1/router.py:292)
- 现状：简历保存到后端 `uploads/resumes` 本地目录；通用文件上传接口固定返回 503 占位错误；移动盘点照片直接作为 `photo_url` 数据提交，未走 Storage。
- 影响：部署到多实例或容器后，简历/照片不可可靠共享；“Storage 已配置”的平台状态会误导验收。数据库当前是 PostgreSQL，但认证仍是本地用户表 + 自签 JWT，不是 Supabase Auth 登录。

## 非阻塞但应修

### [P2] 工作台对无审批权限账号显示不可用按钮

- 位置：[frontend/src/views/WorkbenchView.vue:44](/C:/Users/%E4%B8%87%E5%B0%8F%E9%A5%B1/Desktop/pythoncode/enterprise-ai-suite/frontend/src/views/WorkbenchView.vue:44)
- 招聘管理员点击“进入审批中心”后 URL 仍停在 `/dashboard`，因为路由守卫拒绝了 `approval:view`。按钮应按权限隐藏或改成当前账号可进入模块。

### [P2] 页面顶部空间名称在治理和个人资料页显示错误

- 位置：[frontend/src/layouts/AppLayout.vue:17](/C:/Users/%E4%B8%87%E5%B0%8F%E9%A5%B1/Desktop/pythoncode/enterprise-ai-suite/frontend/src/layouts/AppLayout.vue:17)
- `/notifications`、`/ai-runs`、`/audit-logs`、`/profile` 都落入默认值“AI 简历筛选管理端”，与当前页面不一致，破坏了统一导航口径。

### [P2] 企业 IT 服务台仍是静态说明页

- 位置：[frontend/src/views/ModuleView.vue:58](/C:/Users/%E4%B8%87%E5%B0%8F%E9%A5%B1/Desktop/pythoncode/enterprise-ai-suite/frontend/src/views/ModuleView.vue:58)
- 页面只有流程说明、已具备能力和“计划 AI 能力”，没有工单创建、查询、状态流转或知识检索控件。它可以保留为最后阶段，但当前不能按“业务可用”验收。

## 测试与运行记录

- 后端：`173 passed in 107.81s`
- 前端：`npm.cmd run typecheck` 通过；`npm.cmd run build` 通过。
- 前端 E2E：`58 passed / 1 failed`。失败在 `frontend/tests/e2e/process-monitor.spec.ts:114`，日期选择器硬编码 2026-07-20/24，当前日期跨到下个月后测试找不到日期。应改为固定测试时钟或从日期单元格动态选择。
- 运行中健康检查：数据库 PostgreSQL，Supabase 探针 configured，前端 `/login` 返回 200。
- 页面巡检：桌面和 390px 移动端主要页面未发现横向溢出；未观察到稳定的页面 JavaScript error。工作台首次冷加载约 5 秒后完成，属于明显的等待体验问题，但不是永久卡死。

## 结论

当前代码可以通过构建和大部分自动化测试，但还不能按生产系统验收。优先级顺序应是：先关闭生产环境演示登录漏洞，再恢复招聘 B/C 端路由，修正盘点任务唯一进行中规则和历史回退，最后完成 Supabase Storage/Auth 的真实业务接入；P2 项可随后统一处理。
