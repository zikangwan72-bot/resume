# 流程审批中心（approval-center）设计文档

> 版本：v1.0 | 日期：2026-07-21 | 基于原型图 + 脑暴讨论

---

## 一、需求摘要

在 enterprise-ai-suite 中实现第二个业务模块"流程审批中心"，支持员工发起审批申请、多级审批流程、会签、转审、撤回、催办，以及后台模板管理。

### 关键决策

| 决策点 | 结论 |
|--------|------|
| 审批人确定方式 | 流程模板中直接指定具体人（张三/李四等） |
| 数据库 | 独立 `approval.db`，与 `enterprise_ai.db` 物理隔离 |
| 表单模板 | 半动态：字段用 JSON 存库，管理员可配置，无拖拽设计器 |
| 审批类型 | 请假、报销、采购（3 种） |
| 功能范围 | 完整审批闭环 + 转审 + 撤回 + 催办 + 会签 + 后台管理 |
| UI | 轻度美化，参考原型图风格 |

---

## 二、审批流程

### 2.1 请假审批（三级串行）

```
员工提交
    │
    ▼
节点1：部门经理审批 — 审批人：张三
    ├── 同意 → 节点2
    ├── 驳回 → 退回申请人
    └── 转审 → 转给他人
    │
    ▼
节点2：分管领导审批 — 审批人：李四
    ├── 同意 → 节点3
    ├── 驳回 → 退回申请人
    └── 转审 → 转给他人
    │
    ▼
节点3：HR确认 — 审批人：王五
    ├── 同意 → 完成 ✅
    └── 驳回 → 退回申请人
```

### 2.2 报销审批（三级串行）

```
员工提交 → 张三（部门经理）→ 李四（分管领导）→ 赵六（财务）→ 完成
各节点均可：同意/驳回/转审
```

### 2.3 采购审批（会签 + 串行）

```
员工提交
    │
    ▼
节点1：部门经理审批 — 审批人：张三
    ├── 同意 → 节点2
    └── 驳回 → 退回申请人
    │
    ▼
节点2：领导会签 — 审批人：李四 + 孙七（两人同时审批）
    ├── 全部同意 → 节点3
    ├── 任一驳回 → 退回节点1（张三重新审批）
    └── 单人转审 → 替换该人
    │
    ▼
节点3：财务审批 — 审批人：赵六
    ├── 同意 → 完成 ✅
    └── 驳回 → 退回申请人
```

---

## 三、特殊操作逻辑

| 操作 | 规则 |
|------|------|
| **同意** | 若是最后节点 → 申请状态变 `approved`；否则 `current_node_index +1`，下一节点变 `pending` |
| **驳回** | 必须填原因。普通节点驳回：申请状态变 `rejected`；会签节点驳回：退回上一节点（上一节点的所有行重置为 `pending`），申请状态不变 |
| **转审** | 改当前节点的 `approver_id` 为新用户；写操作记录 |
| **撤回** | 仅当申请状态为 `pending`（第一个节点未操作）时可撤；状态变 `revoked` |
| **催办** | 向当前节点的所有审批人发通知；记录操作但不改变状态 |
| **会签推进** | 同一 `node_index` 下所有节点全部 `approved` 才算该节点通过，缺一不可 |
| **会签驳回** | 同一 `node_index` 下任一节点 `rejected`，该节点下所有关联行统一变 `rejected`，上一节点重置为 `pending` |

---

## 四、数据模型

### 4.1 新增用户（种子数据，存 approval.db）

| UUID | 姓名 | 角色 | 部门 |
|------|------|------|------|
| `44444444-4444-4444-4444-444444444444` | 张三 | 部门经理 | 产品研发部 |
| `55555555-5555-5555-5555-555555555555` | 李四 | 分管领导 | 产品研发部 |
| `66666666-6666-6666-6666-666666666666` | 王五 | HR | 人力资源部 |
| `77777777-7777-7777-7777-777777777777` | 赵六 | 财务 | 财务管理部 |
| `88888888-8888-8888-8888-888888888888` | 孙七 | 分管副总 | 产品研发部 |

### 4.2 审批类型（approval_types）

| id | 名称 | 表单模板 | 流程模板 |
|----|------|----------|----------|
| 1 | 请假申请 | 请假表单 | 三级审批（张三→李四→王五） |
| 2 | 报销申请 | 报销表单 | 三级审批（张三→李四→赵六） |
| 3 | 采购申请 | 采购表单 | 会签流程（张三→李四+孙七→赵六） |

### 4.3 表单模板预设

**请假表单（fields JSON）**：
```json
[
  {"key": "leave_type", "label": "请假类型", "type": "select", "required": true, "options": ["事假", "病假", "年假", "调休", "婚假"]},
  {"key": "start_date", "label": "开始日期", "type": "date", "required": true},
  {"key": "end_date", "label": "结束日期", "type": "date", "required": true},
  {"key": "days", "label": "天数", "type": "number", "required": true},
  {"key": "reason", "label": "请假事由", "type": "textarea", "required": true}
]
```

**报销表单（fields JSON）**：
```json
[
  {"key": "expense_type", "label": "报销类别", "type": "select", "required": true, "options": ["差旅费", "办公用品", "招待费", "交通费", "其他"]},
  {"key": "amount", "label": "报销金额（元）", "type": "number", "required": true},
  {"key": "expense_date", "label": "发生日期", "type": "date", "required": true},
  {"key": "description", "label": "费用说明", "type": "textarea", "required": true}
]
```

**采购表单（fields JSON）**：
```json
[
  {"key": "item_name", "label": "采购物品", "type": "text", "required": true},
  {"key": "quantity", "label": "数量", "type": "number", "required": true},
  {"key": "estimated_amount", "label": "预估金额（元）", "type": "number", "required": true},
  {"key": "purpose", "label": "采购用途", "type": "textarea", "required": true},
  {"key": "supplier", "label": "建议供应商", "type": "text", "required": false}
]
```

### 4.4 流程模板预设

**三级审批流程（请假用）**：
```json
[
  {"index": 0, "name": "部门经理审批", "type": "single", "approver_id": "44444444-4444-4444-4444-444444444444", "allow_transfer": true},
  {"index": 1, "name": "分管领导审批", "type": "single", "approver_id": "55555555-5555-5555-5555-555555555555", "allow_transfer": true},
  {"index": 2, "name": "HR确认", "type": "single", "approver_id": "66666666-6666-6666-6666-666666666666", "allow_transfer": false}
]
```

**三级审批流程（报销用）**：
```json
[
  {"index": 0, "name": "部门经理审批", "type": "single", "approver_id": "44444444-4444-4444-4444-444444444444", "allow_transfer": true},
  {"index": 1, "name": "分管领导审批", "type": "single", "approver_id": "55555555-5555-5555-5555-555555555555", "allow_transfer": true},
  {"index": 2, "name": "财务审批", "type": "single", "approver_id": "77777777-7777-7777-7777-777777777777", "allow_transfer": false}
]
```

**会签流程（采购用）**：
```json
[
  {"index": 0, "name": "部门经理审批", "type": "single", "approver_id": "44444444-4444-4444-4444-444444444444", "allow_transfer": true},
  {"index": 1, "name": "领导会签", "type": "counter_sign", "approver_ids": ["55555555-5555-5555-5555-555555555555", "88888888-8888-8888-8888-888888888888"], "allow_transfer": true},
  {"index": 2, "name": "财务审批", "type": "single", "approver_id": "77777777-7777-7777-7777-777777777777", "allow_transfer": false}
]
```

### 4.5 数据库表（全部存 approval.db）

```sql
-- 审批类型
CREATE TABLE approval_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    form_template_id INTEGER NOT NULL,
    flow_template_id INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 表单模板
CREATE TABLE form_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    fields JSON NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 流程模板
CREATE TABLE flow_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    nodes JSON NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 审批申请（核心表）
CREATE TABLE approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_id INTEGER NOT NULL,
    applicant_id VARCHAR(36) NOT NULL,
    applicant_name VARCHAR(100) NOT NULL,
    title VARCHAR(200) NOT NULL,
    form_data JSON NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    current_node_index INTEGER NOT NULL DEFAULT 0,
    flow_snapshot JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    submitted_at DATETIME,
    completed_at DATETIME
);

-- 审批节点实例（提交时从模板展开）
CREATE TABLE approval_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    node_index INTEGER NOT NULL,
    approver_id VARCHAR(36) NOT NULL,
    approver_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    comment TEXT,
    acted_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 审批操作记录
CREATE TABLE approval_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL,
    request_id INTEGER NOT NULL,
    actor_id VARCHAR(36) NOT NULL,
    actor_name VARCHAR(100) NOT NULL,
    action VARCHAR(20) NOT NULL,
    comment TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 审批用户
CREATE TABLE approval_users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 五、API 设计

### 5.1 审批申请

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/v1/approvals/types` | approval:view | 审批类型列表（含表单字段） |
| POST | `/api/v1/approvals/requests` | approval:view | 提交申请 |
| GET | `/api/v1/approvals/requests` | approval:view | 我的申请（支持 status 筛选） |
| GET | `/api/v1/approvals/requests/{id}` | approval:view | 申请详情（含节点列表 + 操作记录） |
| PUT | `/api/v1/approvals/requests/{id}/revoke` | approval:view | 撤回 |
| PUT | `/api/v1/approvals/requests/{id}/urge` | approval:view | 催办 |

### 5.2 审批处理

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/v1/approvals/pending` | approval:view | 待我审批 |
| GET | `/api/v1/approvals/handled` | approval:view | 我已审批 |
| POST | `/api/v1/approvals/nodes/{id}/approve` | approval:view | 同意 |
| POST | `/api/v1/approvals/nodes/{id}/reject` | approval:view | 驳回 |
| POST | `/api/v1/approvals/nodes/{id}/transfer` | approval:view | 转审（body: target_user_id） |
| GET | `/api/v1/approvals/cc` | approval:view | 抄送我的（本期：已完成的审批） |

### 5.3 后台管理

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET/POST | `/api/v1/admin/approval-types` | approval:manage | 类型列表 / 新建 |
| PUT/DELETE | `/api/v1/admin/approval-types/{id}` | approval:manage | 编辑 / 删除 |
| GET/POST | `/api/v1/admin/form-templates` | approval:manage | 表单模板列表 / 新建 |
| PUT/DELETE | `/api/v1/admin/form-templates/{id}` | approval:manage | 编辑 / 删除 |
| GET/POST | `/api/v1/admin/flow-templates` | approval:manage | 流程模板列表 / 新建 |
| PUT/DELETE | `/api/v1/admin/flow-templates/{id}` | approval:manage | 编辑 / 删除 |
| GET | `/api/v1/admin/users` | approval:manage | 审批用户列表（配置时选人） |
| GET | `/api/v1/admin/logs` | approval:manage | 审批日志 |

### 5.4 响应格式

统一 `{"data": ...}` 格式，与现有项目一致。

---

## 六、前端页面

### 6.1 路由

```
/modules/approval-center/          → 审批首页
/modules/approval-center/requests  → 我的申请
/modules/approval-center/new       → 发起申请
/modules/approval-center/:id       → 审批详情
/modules/approval-center/pending   → 待我审批
/modules/approval-center/handled   → 我已审批
/admin/approval-types              → 审批类型管理
/admin/form-templates              → 表单模板管理
/admin/flow-templates              → 流程模板管理
/admin/approval-logs               → 审批日志
```

### 6.2 页面说明

| 页面 | 内容 |
|------|------|
| **审批首页** | 统计卡片（待审批数/已审批数），待审批列表（最近 5 条），发起申请入口 |
| **发起申请** | 选审批类型 → 动态表单（根据 fields JSON 渲染）→ 提交 |
| **审批详情** | 表单只读展示 + 审批进度（节点列表：审批人头像/姓名/状态/时间）+ 操作区（同意/驳回/转审 + 意见输入） |
| **我的申请** | Tab（全部/审批中/已通过/已驳回）+ 列表 |
| **待我审批** | 列表 + 同意/驳回/转审操作 |
| **后台管理** | 表格 + 新增/编辑弹窗，表单模板用 JSON 编辑区 |

### 6.3 UI 风格

- 复用 AppLayout 布局框架
- 统计卡片使用原型图风格（浅色背景 + 数字 + 标签）
- 审批节点进度使用步骤条可视化展示
- 操作记录用时间线组件

---

## 七、权限控制

`seed.py` 中 `platform_admin` 新增权限点：
- `approval:manage`（后台管理）

`product_demo_user` 已有 `approval:view`，可正常使用审批功能。

新增的 5 个审批用户（张三/李四/王五/赵六/孙七）不通过 JWT 登录，仅作为审批流程中的人员引用。

---

## 八、目录结构

```
backend/
├── approval.db                    # 新增：审批专用数据库
├── app/
│   ├── approval/                  # 新增：审批模块
│   │   ├── __init__.py
│   │   ├── database.py            # 审批引擎 + Session
│   │   ├── models.py              # 7 张表 ORM
│   │   ├── seed.py                # 种子数据
│   │   └── router.py              # 审批 API（~20 个端点）
│   └── main.py                    # 修改：注册审批路由 + 初始化审批DB

frontend/
├── src/
│   ├── router/index.ts            # 修改：新增审批路由
│   ├── views/
│   │   └── approval/              # 新增
│   │       ├── ApprovalHome.vue          # 审批首页
│   │       ├── ApprovalNew.vue           # 发起申请
│   │       ├── ApprovalDetail.vue        # 审批详情
│   │       ├── ApprovalMyRequests.vue    # 我的申请
│   │       ├── ApprovalPending.vue       # 待我审批
│   │       └── ApprovalHandled.vue       # 我已审批
│   └── layouts/
│       └── AppLayout.vue          # 修改：导航新增审批子菜单
```

---

## 九、非功能要求

- 审批操作幂等：同一节点不能被同一个人审批两次
- 流程快照：提交时保存完整流程定义，修改模板不影响已提交的申请
- 会签原子性：同一 node_index 下的多个节点操作需检查关联行状态
- 操作日志：每次审批操作写入 approval_actions
