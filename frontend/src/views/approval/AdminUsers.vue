<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'

import api from '@/api/client'
import type { ApiEnvelope, ApprovalUser, ApprovalUserInput } from '@/types/approval'

type UserForm = ApprovalUserInput
type FieldError = { field: keyof UserForm; message: string }
type ApiErrorPayload = { detail?: unknown; message?: unknown }

const users = ref<ApprovalUser[]>([])
const loading = ref(true)
const failed = ref(false)
const search = ref('')
const activeFilter = ref<'all' | 'active' | 'inactive'>('all')
const modalOpen = ref(false)
const saving = ref(false)
const generalError = ref('')
const editing = ref<ApprovalUser | null>(null)
const formRef = ref<FormInstance>()
const formState = reactive<UserForm>(emptyForm())
const fieldErrors = reactive<Partial<Record<keyof UserForm, string>>>({})

const roleOptions = [
  { label: '平台管理员', value: 'platform_admin' },
  { label: '部门经理', value: 'department_manager' },
  { label: '分管领导', value: 'division_leader' },
  { label: 'HR', value: 'hr' },
  { label: '财务', value: 'finance' },
  { label: '分管副总', value: 'vp' },
  // Roles carried over from login accounts (see backend app/db/user_merge.py).
  { label: '招聘管理员', value: 'recruitment_admin' },
  { label: '资产管理员', value: 'asset_admin' },
  { label: 'IT运维', value: 'it_support' },
  { label: '员工', value: 'employee' },
]

const filteredUsers = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return users.value.filter((user) => {
    const matchesKeyword = !keyword || [user.display_name, user.email, user.department, user.position].some((value) => value.toLowerCase().includes(keyword))
    const matchesStatus = activeFilter.value === 'all' || (activeFilter.value === 'active' ? user.is_active : !user.is_active)
    return matchesKeyword && matchesStatus
  })
})

function emptyForm(): UserForm {
  return { display_name: '', email: '', department: '', position: '', role: 'department_manager', is_active: true }
}

function resetForm(value: Partial<UserForm> = {}) {
  Object.assign(formState, emptyForm(), value)
  generalError.value = ''
  Object.keys(fieldErrors).forEach((key) => { delete fieldErrors[key as keyof UserForm] })
  formRef.value?.clearValidate()
}

async function loadUsers() {
  loading.value = true
  failed.value = false
  try {
    const response = await api.get<ApiEnvelope<ApprovalUser[]>>('/api/v1/admin/users')
    users.value = response.data.data
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  resetForm()
  modalOpen.value = true
}

function openEdit(user: ApprovalUser) {
  editing.value = user
  resetForm({ ...user })
  modalOpen.value = true
}

function closeModal() {
  if (!saving.value) modalOpen.value = false
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function apiErrorMessage(error: unknown): string {
  if (!isRecord(error) || !isRecord(error.response)) return '保存失败，请稍后重试'
  const payload = error.response.data as unknown
  if (isRecord(payload) && typeof payload.message === 'string') return payload.message
  if (isRecord(payload) && typeof payload.detail === 'string') return payload.detail
  return '保存失败，请检查输入后重试'
}

function apiFieldErrors(error: unknown): FieldError[] {
  if (!isRecord(error) || !isRecord(error.response) || !isRecord(error.response.data)) return []
  const payload = error.response.data as ApiErrorPayload
  if (error.response.status === 409 && payload.detail === '邮箱已存在') return [{ field: 'email', message: '邮箱已存在' }]
  const detail = payload.detail
  if (!Array.isArray(detail)) return []
  return detail.flatMap((item): FieldError[] => {
    if (!isRecord(item) || !Array.isArray(item.loc) || typeof item.msg !== 'string') return []
    const field = item.loc.at(-1)
    return typeof field === 'string' && field in formState ? [{ field: field as keyof UserForm, message: item.msg }] : []
  })
}

async function saveUser() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const endpoint = editing.value ? `/api/v1/admin/users/${editing.value.id}` : '/api/v1/admin/users'
    const response = editing.value
      ? await api.put<ApiEnvelope<ApprovalUser>>(endpoint, formState)
      : await api.post<ApiEnvelope<ApprovalUser>>(endpoint, formState)
    const saved = response.data.data
    if (editing.value) users.value = users.value.map((user) => user.id === saved.id ? saved : user)
    else users.value = [...users.value, saved].sort((a, b) => a.display_name.localeCompare(b.display_name, 'zh-CN'))
    modalOpen.value = false
    message.success(editing.value ? '员工信息已更新' : '员工已创建')
  } catch (error: unknown) {
    const errors = apiFieldErrors(error)
    errors.forEach(({ field, message: errorMessage }) => { fieldErrors[field] = errorMessage })
    generalError.value = apiErrorMessage(error)
    message.error(generalError.value)
  } finally {
    saving.value = false
  }
}

async function setActive(user: ApprovalUser, isActive: boolean) {
  try {
    const response = await api.put<ApiEnvelope<ApprovalUser>>(`/api/v1/admin/users/${user.id}`, { is_active: isActive, position: user.position })
    users.value = users.value.map((item) => item.id === user.id ? response.data.data : item)
    message.success(isActive ? '员工已启用' : '员工已停用')
  } catch (error: unknown) {
    message.error(apiErrorMessage(error))
  }
}

function toggleActive(user: ApprovalUser, checked: boolean) {
  if (checked) void setActive(user, true)
}

function roleLabel(role: string) {
  return roleOptions.find((option) => option.value === role)?.label || role
}

onMounted(loadUsers)
</script>

<template>
  <div class="page-frame admin-users-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">ADMINISTRATION</p>
        <h1>员工与审批角色</h1>
        <p>维护审批参与人、岗位和可用状态。</p>
      </div>
      <div class="heading-actions">
        <a-button aria-label="刷新员工列表" @click="loadUsers"><ReloadOutlined /> 刷新</a-button>
        <a-button type="primary" @click="openCreate"><PlusOutlined /> 新增员工</a-button>
      </div>
    </header>

    <a-alert v-if="failed" class="page-alert" type="error" show-icon message="员工列表加载失败" description="请检查服务连接后重试。">
      <template #action><a-button size="small" @click="loadUsers">重试</a-button></template>
    </a-alert>

    <a-card v-else :bordered="false" class="users-panel">
      <a-skeleton v-if="loading" active :paragraph="{ rows: 6 }" />
      <template v-else>
        <div class="users-toolbar">
          <a-input v-model:value="search" allow-clear placeholder="搜索姓名、邮箱、部门或职位" aria-label="搜索员工"><template #prefix><SearchOutlined /></template></a-input>
          <a-segmented v-model:value="activeFilter" :options="[{ label: '全部', value: 'all' }, { label: '启用中', value: 'active' }, { label: '已停用', value: 'inactive' }]" aria-label="员工状态筛选" />
        </div>
        <a-empty v-if="filteredUsers.length === 0" description="暂无匹配员工" />
        <a-table v-else class="users-table" :data-source="filteredUsers" row-key="id" :pagination="false" :scroll="{ x: 1040 }">
          <a-table-column title="姓名" data-index="display_name" :width="140" />
          <a-table-column title="邮箱" data-index="email" :width="220" />
          <a-table-column title="部门" data-index="department" :width="160" />
          <a-table-column title="职位" data-index="position" :width="140" />
          <a-table-column title="角色" :width="130"><template #default="{ record }"><a-tag>{{ roleLabel(record.role) }}</a-tag></template></a-table-column>
          <a-table-column title="状态" :width="100"><template #default="{ record }"><a-tag :color="record.is_active ? 'success' : 'default'">{{ record.is_active ? '启用' : '停用' }}</a-tag></template></a-table-column>
          <a-table-column title="操作" fixed="right" :width="150"><template #default="{ record }">
            <a-space>
              <a-button type="link" size="small" @click="openEdit(record)">编辑</a-button>
              <a-popconfirm v-if="record.is_active" title="停用这名员工？" ok-text="停用" cancel-text="取消" @confirm="setActive(record, false)">
                <a-switch :checked="record.is_active" size="small" :aria-label="`停用 ${record.display_name}`" />
              </a-popconfirm>
              <a-switch v-else :checked="record.is_active" size="small" :aria-label="`启用 ${record.display_name}`" @change="toggleActive(record, $event)" />
            </a-space>
          </template></a-table-column>
        </a-table>
        <a-list v-if="filteredUsers.length" class="user-mobile-list" :data-source="filteredUsers">
          <template #renderItem="{ item }">
            <a-list-item class="user-mobile-item">
              <div class="user-mobile-heading">
                <div><strong>{{ item.display_name }}</strong><small>{{ item.email }}</small></div>
                <a-tag :color="item.is_active ? 'success' : 'default'">{{ item.is_active ? '启用' : '停用' }}</a-tag>
              </div>
              <div class="user-mobile-meta">
                <span>{{ item.department }}</span>
                <span>{{ item.position }}</span>
                <a-tag>{{ roleLabel(item.role) }}</a-tag>
              </div>
              <div class="user-mobile-actions">
                <a-button size="small" @click="openEdit(item)">编辑</a-button>
                <a-popconfirm v-if="item.is_active" title="停用这名员工？" ok-text="停用" cancel-text="取消" @confirm="setActive(item, false)">
                  <a-switch :checked="item.is_active" size="small" :aria-label="`停用 ${item.display_name}`" />
                </a-popconfirm>
                <a-switch v-else :checked="item.is_active" size="small" :aria-label="`启用 ${item.display_name}`" @change="toggleActive(item, $event)" />
              </div>
            </a-list-item>
          </template>
        </a-list>
      </template>
    </a-card>

    <a-modal v-model:open="modalOpen" :title="editing ? '编辑员工' : '新增员工'" ok-text="保存" :ok-button-props="{ 'aria-label': '保存' }" cancel-text="取消" :confirm-loading="saving" @ok="saveUser" @cancel="closeModal">
      <a-alert v-if="!editing" class="modal-hint" type="info" show-icon message="职位是审批路由展示所必需的信息。" />
      <a-alert v-if="generalError" class="modal-hint" type="error" show-icon :message="generalError" />
      <a-form ref="formRef" :model="formState" layout="vertical">
        <a-form-item label="姓名" name="display_name" :help="fieldErrors.display_name" :validate-status="fieldErrors.display_name ? 'error' : undefined" :rules="[{ required: true, whitespace: true, message: '请输入姓名' }]">
          <a-input v-model:value="formState.display_name" autocomplete="name" />
        </a-form-item>
        <a-form-item label="邮箱" name="email" :help="fieldErrors.email" :validate-status="fieldErrors.email ? 'error' : undefined" :rules="[{ required: true, whitespace: true, message: '请输入邮箱' }, { type: 'email', message: '请输入有效邮箱' }]">
          <a-input v-model:value="formState.email" autocomplete="email" />
        </a-form-item>
        <a-form-item label="部门" name="department" :help="fieldErrors.department" :validate-status="fieldErrors.department ? 'error' : undefined" :rules="[{ required: true, whitespace: true, message: '请输入部门' }]">
          <a-input v-model:value="formState.department" />
        </a-form-item>
        <a-form-item label="职位" name="position" :help="fieldErrors.position" :validate-status="fieldErrors.position ? 'error' : undefined" :rules="[{ required: true, whitespace: true, message: '请输入职位' }]">
          <a-input v-model:value="formState.position" />
        </a-form-item>
        <a-form-item label="角色" name="role" :help="fieldErrors.role" :validate-status="fieldErrors.role ? 'error' : undefined" :rules="[{ required: true, message: '请选择角色' }]">
          <a-select v-model:value="formState.role" :options="roleOptions" />
        </a-form-item>
        <a-form-item label="状态" name="is_active">
          <a-switch v-model:checked="formState.is_active" checked-children="启用" un-checked-children="停用" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.users-panel { border: 1px solid #f0f0f0; }
.users-toolbar { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.users-toolbar .ant-input { max-width: 360px; }
.user-mobile-list { display: none; }
.modal-hint { margin-bottom: 16px; }
@media (max-width: 640px) {
  .users-toolbar { align-items: stretch; flex-direction: column; }
  .users-toolbar .ant-input { max-width: none; }
  .users-table { display: none; }
  .user-mobile-list { display: block; }
  .user-mobile-item { display: block !important; padding: 16px 0 !important; }
  .user-mobile-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .user-mobile-heading > div { display: grid; gap: 3px; min-width: 0; }
  .user-mobile-heading small { color: #8c8c8c; overflow-wrap: anywhere; }
  .user-mobile-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 10px; color: #595959; font-size: 13px; }
  .user-mobile-meta span + span::before { margin-right: 6px; color: #bfbfbf; content: '·'; }
  .user-mobile-actions { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
}
</style>
