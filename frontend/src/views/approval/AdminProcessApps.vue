<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { CopyOutlined, EyeOutlined, MoreOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'

import api from '@/api/client'
import ProcessStatusTag from '@/components/approval/ProcessStatusTag.vue'
import type { ApiEnvelope, ProcessApp, ProcessAppStatus } from '@/types/approval'
import { useRouter } from 'vue-router'

const router = useRouter()
const apps = ref<ProcessApp[]>([])
const loading = ref(true)
const failed = ref(false)
const search = ref('')
const statusFilter = ref<'all' | ProcessAppStatus>('all')
const categoryFilter = ref('all')
const previewApp = ref<ProcessApp | null>(null)
const actionLoading = ref<number | null>(null)

const categories = computed(() => [...new Set(apps.value.map((app) => app.category))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
const filteredApps = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return apps.value.filter((app) => {
    const matchesSearch = !keyword || [app.name, app.code, app.category, app.description || ''].some((value) => value.toLowerCase().includes(keyword))
    const matchesStatus = statusFilter.value === 'all' || app.status === statusFilter.value
    const matchesCategory = categoryFilter.value === 'all' || app.category === categoryFilter.value
    return matchesSearch && matchesStatus && matchesCategory
  })
})

async function loadApps() {
  loading.value = true
  failed.value = false
  try {
    const response = await api.get<ApiEnvelope<ProcessApp[]>>('/api/v1/admin/process-apps')
    apps.value = response.data.data
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

function apiErrorMessage(error: unknown) {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: unknown } }).response
    const data = response?.data
    if (typeof data === 'object' && data !== null && 'detail' in data && typeof data.detail === 'string') return data.detail
    if (typeof data === 'object' && data !== null && 'message' in data && typeof data.message === 'string') return data.message
  }
  return '操作失败，请稍后重试'
}

function openPreview(app: ProcessApp) {
  previewApp.value = app
}

function editApp(app: ProcessApp) {
  void router.push(`/admin/process-apps/${app.id}/edit`)
}

async function copyApp(app: ProcessApp) {
  actionLoading.value = app.id
  try {
    const response = await api.post<ApiEnvelope<ProcessApp>>(`/api/v1/admin/process-apps/${app.id}/copy`)
    const copy = response.data.data
    apps.value = [copy, ...apps.value]
    message.success('流程应用已复制')
    await router.push(`/admin/process-apps/${copy.id}/edit`)
  } catch (error: unknown) {
    message.error(apiErrorMessage(error))
  } finally {
    actionLoading.value = null
  }
}

function confirmDeactivate(app: ProcessApp) {
  Modal.confirm({
    title: '停用流程应用？',
    content: `停用后员工不能发起新的${app.name}，历史记录仍可查看。`,
    okText: '停用',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: () => deactivateApp(app),
  })
}

async function deactivateApp(app: ProcessApp) {
  actionLoading.value = app.id
  try {
    const response = await api.post<ApiEnvelope<ProcessApp>>(`/api/v1/admin/process-apps/${app.id}/deactivate`)
    apps.value = apps.value.map((item) => item.id === app.id ? response.data.data : item)
    message.success('流程应用已停用')
  } catch (error: unknown) {
    message.error(apiErrorMessage(error))
  } finally {
    actionLoading.value = null
  }
}

function formatDate(value: string) {
  return value ? value.slice(0, 16).replace('T', ' ') : '-'
}

onMounted(loadApps)
</script>

<template>
  <div class="page-frame process-apps-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">PROCESS ADMINISTRATION</p>
        <h1>流程应用</h1>
        <p>统一管理表单、审批节点和发布版本。</p>
      </div>
      <div class="heading-actions">
        <a-button aria-label="刷新流程应用列表" @click="loadApps"><ReloadOutlined /> 刷新</a-button>
        <a-button type="primary" @click="router.push('/admin/process-apps/new')"><PlusOutlined /> 新建流程应用</a-button>
      </div>
    </header>

    <a-alert v-if="failed" class="page-alert" type="error" show-icon message="流程应用列表加载失败" description="请检查服务连接后重试。">
      <template #action><a-button size="small" @click="loadApps">重试</a-button></template>
    </a-alert>

    <a-card v-else :bordered="false" class="process-apps-panel">
      <a-skeleton v-if="loading" active :paragraph="{ rows: 7 }" />
      <template v-else>
        <div class="process-apps-toolbar">
          <a-input v-model:value="search" allow-clear placeholder="搜索名称、编号或分类" aria-label="搜索流程应用">
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-segmented v-model:value="statusFilter" aria-label="流程状态筛选" :options="[{ label: '全部', value: 'all' }, { label: '草稿', value: 'draft' }, { label: '已发布', value: 'published' }, { label: '已停用', value: 'inactive' }]" />
          <a-select v-model:value="categoryFilter" aria-label="流程分类筛选" :options="[{ label: '全部分类', value: 'all' }, ...categories.map((category) => ({ label: category, value: category }))]" />
        </div>

        <a-empty v-if="filteredApps.length === 0" description="暂无流程应用" />
        <a-table v-else class="process-apps-table" :data-source="filteredApps" row-key="id" :pagination="false" :scroll="{ x: 1040 }">
          <a-table-column title="流程应用" :width="220">
            <template #default="{ record }"><strong>{{ record.name }}</strong><span class="code-label">{{ record.code }}</span></template>
          </a-table-column>
          <a-table-column title="分类" data-index="category" :width="120" />
          <a-table-column title="字段数" data-index="field_count" :width="90" />
          <a-table-column title="审批节点数" data-index="approval_node_count" :width="120" />
          <a-table-column title="当前版本" :width="130"><template #default="{ record }"><span>{{ record.version_number ? 'v' + record.version_number : '暂无发布版本' }}</span><a-tag v-if="record.has_draft" color="warning" class="draft-tag">有草稿</a-tag></template></a-table-column>
          <a-table-column title="状态" :width="110"><template #default="{ record }"><ProcessStatusTag :status="record.status" /></template></a-table-column>
          <a-table-column title="更新时间" :width="170"><template #default="{ record }">{{ formatDate(record.updated_at) }}</template></a-table-column>
          <a-table-column title="操作" fixed="right" :width="96">
            <template #default="{ record }">
              <a-dropdown :trigger="['click']">
                <a-button type="text" aria-label="更多操作"><MoreOutlined /></a-button>
                <template #overlay>
                  <a-menu>
                    <a-menu-item key="preview" @click="openPreview(record)"><EyeOutlined /> 预览</a-menu-item>
                    <a-menu-item key="edit" @click="editApp(record)">编辑</a-menu-item>
                    <a-menu-item key="copy" :disabled="actionLoading === record.id" @click="copyApp(record)"><CopyOutlined /> 复制</a-menu-item>
                    <a-menu-divider />
                    <a-menu-item v-if="record.status !== 'inactive'" key="deactivate" danger @click="confirmDeactivate(record)">停用</a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </template>
          </a-table-column>
        </a-table>
        <a-list v-if="filteredApps.length" class="process-app-mobile-list" :data-source="filteredApps">
          <template #renderItem="{ item }">
            <a-list-item class="process-app-mobile-item">
              <div class="process-app-mobile-heading">
                <div><strong>{{ item.name }}</strong><small>{{ item.code }}</small></div>
                <ProcessStatusTag :status="item.status" />
              </div>
              <div class="process-app-mobile-meta">
                <a-tag>{{ item.category }}</a-tag>
                <span>{{ item.field_count }} 个字段</span>
                <span>{{ item.approval_node_count }} 个审批节点</span>
                <span>{{ item.version_number ? 'v' + item.version_number : '暂无发布版本' }}</span>
                <a-tag v-if="item.has_draft" color="warning">有草稿</a-tag>
              </div>
              <div class="process-app-mobile-footer">
                <small>更新于 {{ formatDate(item.updated_at) }}</small>
                <a-dropdown :trigger="['click']">
                  <a-button type="text" aria-label="更多操作"><MoreOutlined /></a-button>
                  <template #overlay>
                    <a-menu>
                      <a-menu-item key="preview" @click="openPreview(item)"><EyeOutlined /> 预览</a-menu-item>
                      <a-menu-item key="edit" @click="editApp(item)">编辑</a-menu-item>
                      <a-menu-item key="copy" :disabled="actionLoading === item.id" @click="copyApp(item)"><CopyOutlined /> 复制</a-menu-item>
                      <a-menu-divider />
                      <a-menu-item v-if="item.status !== 'inactive'" key="deactivate" danger @click="confirmDeactivate(item)">停用</a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </div>
            </a-list-item>
          </template>
        </a-list>
      </template>
    </a-card>

    <a-modal v-if="previewApp" :open="true" :title="`${previewApp.name} · 预览`" :footer="null" @cancel="previewApp = null">
      <a-descriptions bordered :column="1" size="small">
        <a-descriptions-item label="分类">{{ previewApp.category }}</a-descriptions-item>
        <a-descriptions-item label="字段数">{{ previewApp.field_count }}</a-descriptions-item>
        <a-descriptions-item label="审批节点数">{{ previewApp.approval_node_count }}</a-descriptions-item>
        <a-descriptions-item label="版本">v{{ previewApp.version_number }}</a-descriptions-item>
        <a-descriptions-item label="说明">{{ previewApp.description || '暂无说明' }}</a-descriptions-item>
      </a-descriptions>
    </a-modal>
  </div>
</template>

<style scoped>
.process-apps-panel { border: 1px solid #f0f0f0; }
.process-apps-toolbar { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.process-apps-toolbar .ant-input { width: min(360px, 100%); }
.process-apps-toolbar .ant-select { min-width: 140px; }
.code-label { display: block; color: #8c8c8c; font-size: 12px; font-weight: 400; margin-top: 3px; }
.process-app-mobile-list { display: none; }
@media (max-width: 720px) {
  .process-apps-toolbar { align-items: stretch; flex-direction: column; }
  .process-apps-toolbar .ant-input, .process-apps-toolbar .ant-select { width: 100%; }
  .process-apps-toolbar .ant-segmented { width: 100%; overflow-x: auto; }
  .process-apps-table { display: none; }
  .process-app-mobile-list { display: block; }
  .process-app-mobile-item { display: block !important; padding: 16px 0 !important; }
  .process-app-mobile-heading, .process-app-mobile-footer { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .process-app-mobile-heading > div { display: grid; gap: 3px; min-width: 0; }
  .process-app-mobile-heading small, .process-app-mobile-footer small { color: #8c8c8c; }
  .process-app-mobile-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 10px; color: #595959; font-size: 12px; }
  .process-app-mobile-footer { align-items: center; margin-top: 10px; }
}
</style>
