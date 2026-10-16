<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import axios from 'axios'
import { AlertOutlined, CheckCircleOutlined, ClockCircleOutlined, CustomerServiceOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import api from '@/api/client'
import { useAuthStore } from '@/stores/auth'

interface TicketEvent { id: number; kind: 'status' | 'comment'; actor_name: string; content: string; created_at: string }
interface Ticket {
  id: number
  ticket_no: string
  title: string
  description: string
  category: string
  priority: string
  status: string
  requester_id: string
  requester_name: string
  department: string
  contact: string | null
  assignee_id: string | null
  assignee_name: string | null
  asset_id: number | null
  asset_code: string | null
  asset_name: string | null
  resolution: string | null
  rating: number | null
  due_at: string
  overdue: boolean
  sla_state: '正常' | '即将超时' | '已超时' | '不计时'
  auto_close_at: string | null
  created_at: string
  available_actions?: string[]
  events?: TicketEvent[]
}
interface LinkableAsset { id: number; asset_code: string; name: string; owner: string; location: string }
interface Overview { can_handle: boolean; can_manage: boolean; total: number; open_count: number; overdue_count: number; warning_count: number; my_assigned_open: number; average_rating: number | null; status_counts: Record<string, number> }

const auth = useAuthStore()
const canHandle = computed(() => auth.can('service_desk:handle'))
const categories = ['账号权限', '硬件设备', '软件安装', '网络连接', '其他']
const priorities = ['低', '中', '高', '紧急']
const statusFilters = ['全部', '待受理', '处理中', '待补充', '已解决', '已关闭', '已取消', '超时']
const statusColor: Record<string, string> = { 待受理: 'orange', 处理中: 'processing', 待补充: 'purple', 已解决: 'green', 已关闭: 'default', 已取消: 'default' }
const slaColor: Record<string, string> = { 即将超时: 'orange', 已超时: 'red' }
const priorityColor: Record<string, string> = { 低: 'default', 中: 'blue', 高: 'orange', 紧急: 'red' }
const flow = ['提交工单', '接单派单', '处理与补充信息', '解决确认', '关闭评价']

const overview = ref<Overview | null>(null)
const tickets = ref<Ticket[]>([])
const agents = ref<{ id: string; display_name: string }[]>([])
const loading = ref(true)
const loadError = ref('')
const scope = ref<'mine' | 'all' | 'assigned' | 'pool'>(canHandle.value ? 'pool' : 'mine')
const statusFilter = ref('全部')
const keyword = ref('')
const ticketPage = reactive({ current: 1, pageSize: 10, total: 0 })

const createOpen = ref(false)
const saving = ref(false)
const form = reactive<{ title: string; description: string; category: string; priority: string; contact: string; asset_id: number | undefined }>({ title: '', description: '', category: '账号权限', priority: '中', contact: '', asset_id: undefined })
const assetOptions = ref<LinkableAsset[]>([])

const detail = ref<Ticket | null>(null)
const detailOpen = ref(false)
const acting = ref(false)
const comment = ref('')
const resolution = ref('')
const reason = ref('')
const infoText = ref('')
const rating = ref(5)
const assigneeId = ref<string | undefined>()

const can = (action: string) => Boolean(detail.value?.available_actions?.includes(action))
const transferTargets = computed(() => agents.value.filter((agent) => agent.id !== detail.value?.assignee_id))

function errorText(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const detailText = error.response?.data?.detail
    if (typeof detailText === 'string') return detailText
    if (Array.isArray(detailText)) return '请检查填写内容'
    return error.response?.data?.message || fallback
  }
  return fallback
}

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function loadTickets() {
  const params: Record<string, string | number> = { scope: scope.value, page: ticketPage.current, page_size: ticketPage.pageSize }
  if (statusFilter.value !== '全部') params.status = statusFilter.value
  if (keyword.value.trim()) params.keyword = keyword.value.trim()
  const body = (await api.get('/api/v1/service-desk/tickets', { params })).data
  ticketPage.total = body.pagination?.total ?? body.data.length
  // A page can empty out after a ticket changes status; step back to the last page.
  if (!body.data.length && ticketPage.current > 1 && ticketPage.total > 0) {
    ticketPage.current = Math.ceil(ticketPage.total / ticketPage.pageSize)
    return loadTickets()
  }
  tickets.value = body.data
}

function changeTicketPage(pagination: { current?: number; pageSize?: number }) {
  ticketPage.current = pagination.current ?? 1
  ticketPage.pageSize = pagination.pageSize ?? ticketPage.pageSize
  refreshList()
}

function searchTickets() {
  ticketPage.current = 1
  refreshList()
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    overview.value = (await api.get('/api/v1/service-desk/overview')).data.data
    await loadTickets()
    if (canHandle.value && !agents.value.length) agents.value = (await api.get('/api/v1/service-desk/agents')).data.data
  } catch (error) {
    loadError.value = errorText(error, '服务台数据加载失败')
  } finally {
    loading.value = false
  }
}

async function refreshList() {
  try {
    await loadTickets()
  } catch (error) {
    message.error(errorText(error, '工单列表加载失败'))
  }
}

watch([scope, statusFilter], searchTickets)

async function searchAssets(value = '') {
  try {
    assetOptions.value = (await api.get('/api/v1/service-desk/assets', { params: { keyword: value } })).data.data
  } catch {
    assetOptions.value = []
  }
}

function openCreate() {
  Object.assign(form, { title: '', description: '', category: '账号权限', priority: '中', contact: '', asset_id: undefined })
  createOpen.value = true
  searchAssets()
}

async function submitTicket() {
  if (form.title.trim().length < 2 || form.description.trim().length < 5) return message.warning('请填写标题和至少 5 个字的问题描述')
  saving.value = true
  try {
    const created = (await api.post('/api/v1/service-desk/tickets', { ...form, contact: form.contact.trim() || null, asset_id: form.asset_id ?? null })).data.data
    message.success(`工单 ${created.ticket_no} 已提交`)
    createOpen.value = false
    if (!canHandle.value) scope.value = 'mine'
    await load()
  } catch (error) {
    message.error(errorText(error, '工单提交失败'))
  } finally {
    saving.value = false
  }
}

async function openDetail(row: Ticket) {
  try {
    detail.value = (await api.get(`/api/v1/service-desk/tickets/${row.id}`)).data.data
    comment.value = ''
    resolution.value = ''
    reason.value = ''
    infoText.value = ''
    rating.value = 5
    assigneeId.value = undefined
    detailOpen.value = true
  } catch (error) {
    message.error(errorText(error, '工单详情加载失败'))
  }
}

async function act(action: string, body: Record<string, unknown>, success: string) {
  if (!detail.value) return
  acting.value = true
  try {
    await api.post(`/api/v1/service-desk/tickets/${detail.value.id}/${action}`, body)
    message.success(success)
    await openDetail(detail.value)
    await load()
  } catch (error) {
    message.error(errorText(error, '操作失败'))
  } finally {
    acting.value = false
  }
}

function requireText(value: string, hint: string) {
  if (value.trim().length < 2) {
    message.warning(hint)
    return false
  }
  return true
}

const claimTicket = () => act('assign', {}, '已接单，开始处理')
const assignTicket = () => (assigneeId.value ? act('assign', { assignee_id: assigneeId.value }, '工单已派发') : message.warning('请选择处理人'))
const transferTicket = () => (assigneeId.value ? act('assign', { assignee_id: assigneeId.value, reason: reason.value.trim() || null }, '工单已转派') : message.warning('请选择转派对象'))
const requestInfo = () => requireText(infoText.value, '请写明需要对方补充什么') && act('request-info', { content: infoText.value }, '已请提单人补充信息')
const replyInfo = () => requireText(infoText.value, '请填写补充的信息') && act('reply', { content: infoText.value }, '补充信息已提交，工单继续处理')
const resolveTicket = () => requireText(resolution.value, '请填写处理结果') && act('resolve', { resolution: resolution.value }, '已标记为已解决')
const closeTicket = () => act('close', { rating: rating.value }, '工单已关闭，感谢评价')
const reopenTicket = () => requireText(reason.value, '请说明未解决的原因') && act('reopen', { reason: reason.value }, '工单已重新打开')
const cancelTicket = () => requireText(reason.value, '请填写撤回原因') && act('cancel', { reason: reason.value }, '工单已撤回')
const sendComment = () => comment.value.trim() && act('comments', { content: comment.value }, '回复已发送')

onMounted(load)
</script>

<template>
  <div class="page-frame business-page service-desk-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">SERVICE DESK</p>
        <h1>企业IT服务台</h1>
        <p>员工提交 IT 问题，IT 运维接单或由主管派单，处理中可请提单人补充信息或转派，解决后由提单人确认评价，72 小时未反馈自动关闭。每一步都会留痕并通知相关人。</p>
      </div>
      <div class="heading-actions">
        <a-button type="primary" @click="openCreate"><PlusOutlined /> 提交工单</a-button>
      </div>
    </header>

    <a-skeleton v-if="loading && !overview" active :paragraph="{ rows: 8 }" />
    <a-result v-else-if="loadError" status="error" title="服务台加载失败" :sub-title="loadError">
      <template #extra><a-button type="primary" @click="load">重试</a-button></template>
    </a-result>
    <template v-else-if="overview">
      <section class="metric-grid">
        <a-card class="metric-card" :bordered="false"><CustomerServiceOutlined /><span>{{ overview.can_handle ? '全部工单' : '我的工单' }}</span><strong>{{ overview.total }}</strong></a-card>
        <a-card class="metric-card" :bordered="false"><ClockCircleOutlined /><span>未完成（含待补充）</span><strong>{{ overview.open_count }}</strong></a-card>
        <a-card class="metric-card" :bordered="false"><AlertOutlined /><span>已超时 / 即将超时</span><strong>{{ overview.overdue_count }} / {{ overview.warning_count }}</strong></a-card>
        <a-card class="metric-card" :bordered="false"><CheckCircleOutlined /><span>{{ overview.can_handle ? '我负责的未完成' : '平均满意度' }}</span><strong>{{ overview.can_handle ? overview.my_assigned_open : overview.average_rating ?? '-' }}</strong></a-card>
      </section>

      <a-card class="plain-panel service-flow" :bordered="false">
        <div class="flow-track">
          <template v-for="(step, index) in flow" :key="step">
            <div class="flow-step"><span>{{ index + 1 }}</span><strong>{{ step }}</strong></div>
            <div v-if="index < flow.length - 1" class="flow-line"></div>
          </template>
        </div>
      </a-card>

      <a-card class="plain-panel service-ticket-panel" :bordered="false">
        <div class="section-title service-ticket-toolbar">
          <a-radio-group v-if="canHandle" v-model:value="scope" button-style="solid" size="small">
            <a-radio-button value="pool">工单池</a-radio-button>
            <a-radio-button value="assigned">我负责的</a-radio-button>
            <a-radio-button value="all">全部工单</a-radio-button>
            <a-radio-button value="mine">我提交的</a-radio-button>
          </a-radio-group>
          <h2 v-else>我的工单</h2>
          <a-space wrap>
            <a-input-search v-model:value="keyword" allow-clear placeholder="搜索标题、单号、提单人" style="width:220px" @search="searchTickets" />
            <a-select v-model:value="statusFilter" :options="statusFilters.map((value) => ({ label: value, value }))" style="width:110px" />
          </a-space>
        </div>
        <a-table
          v-if="tickets.length"
          class="service-ticket-table"
          size="small"
          row-key="id"
          :loading="loading"
          :pagination="{ current: ticketPage.current, pageSize: ticketPage.pageSize, total: ticketPage.total, showSizeChanger: false, showTotal: (total: number) => `共 ${total} 张` }"
          :scroll="{ x: 760 }"
          :data-source="tickets"
          @change="changeTicketPage"
          :custom-row="(record: Ticket) => ({ onClick: () => openDetail(record), style: 'cursor:pointer' })"
          :columns="[
            { title: '工单', dataIndex: 'title', width: '36%' },
            { title: '优先级', dataIndex: 'priority', width: '10%' },
            { title: '状态', dataIndex: 'status', width: '16%' },
            { title: '提单人', dataIndex: 'requester_name', width: '14%' },
            { title: '处理人', dataIndex: 'assignee_name', width: '12%' },
            { title: '提交时间', dataIndex: 'created_at', width: '12%' },
          ]"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'title'">
              <strong>{{ record.title }}</strong>
              <span class="table-subline">{{ record.ticket_no }} · {{ record.category }}</span>
            </template>
            <template v-if="column.dataIndex === 'priority'"><a-tag :color="priorityColor[record.priority]">{{ record.priority }}</a-tag></template>
            <template v-if="column.dataIndex === 'status'">
              <a-tag :color="statusColor[record.status]">{{ record.status }}</a-tag>
              <a-tag v-if="slaColor[record.sla_state]" :color="slaColor[record.sla_state]">{{ record.sla_state }}</a-tag>
            </template>
            <template v-if="column.dataIndex === 'requester_name'">
              <span>{{ record.requester_name }}</span>
              <span class="table-subline">{{ record.department }}</span>
            </template>
            <template v-if="column.dataIndex === 'assignee_name'">{{ record.assignee_name || '未派单' }}</template>
            <template v-if="column.dataIndex === 'created_at'">{{ formatTime(record.created_at) }}</template>
          </template>
        </a-table>
        <a-empty v-else description="暂无工单">
          <a-button type="primary" @click="openCreate"><PlusOutlined /> 提交第一张工单</a-button>
        </a-empty>
      </a-card>
    </template>

    <a-modal v-model:open="createOpen" title="提交 IT 工单" ok-text="提交" :confirm-loading="saving" @ok="submitTicket">
      <a-form layout="vertical">
        <a-form-item label="问题标题" required><a-input v-model:value="form.title" :maxlength="160" placeholder="例如：VPN 连上后无法访问内网" /></a-form-item>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="问题分类" required><a-select v-model:value="form.category" :options="categories.map((value) => ({ label: value, value }))" /></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="紧急程度" required><a-select v-model:value="form.priority" :options="priorities.map((value) => ({ label: value, value }))" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="问题描述" required><a-textarea v-model:value="form.description" :rows="5" :maxlength="4000" show-count placeholder="发生了什么、什么时候开始、已经尝试过什么" /></a-form-item>
        <a-form-item label="关联设备（选填）">
          <a-select
            v-model:value="form.asset_id"
            allow-clear
            show-search
            :filter-option="false"
            placeholder="输入资产编号或名称搜索"
            :options="assetOptions.map((item) => ({ label: `${item.asset_code} · ${item.name}（${item.owner}）`, value: item.id }))"
            @search="searchAssets"
          />
        </a-form-item>
        <a-form-item label="联系方式"><a-input v-model:value="form.contact" :maxlength="120" placeholder="分机或手机号（选填）" /></a-form-item>
      </a-form>
    </a-modal>

    <a-drawer v-model:open="detailOpen" :title="detail?.ticket_no" width="560" class="service-ticket-drawer">
      <template v-if="detail">
        <h2 class="service-ticket-title">{{ detail.title }}</h2>
        <a-space wrap class="service-ticket-tags">
          <a-tag :color="statusColor[detail.status]">{{ detail.status }}</a-tag>
          <a-tag :color="priorityColor[detail.priority]">{{ detail.priority }}优先级</a-tag>
          <a-tag>{{ detail.category }}</a-tag>
          <a-tag v-if="slaColor[detail.sla_state]" :color="slaColor[detail.sla_state]">{{ detail.sla_state }}</a-tag>
        </a-space>
        <a-descriptions :column="2" size="small" bordered>
          <a-descriptions-item label="提单人">{{ detail.requester_name }}</a-descriptions-item>
          <a-descriptions-item label="部门">{{ detail.department || '-' }}</a-descriptions-item>
          <a-descriptions-item label="处理人">{{ detail.assignee_name || '未派单' }}</a-descriptions-item>
          <a-descriptions-item label="解决时限">{{ formatTime(detail.due_at) }}</a-descriptions-item>
          <a-descriptions-item v-if="detail.asset_code" label="关联设备" :span="2">{{ detail.asset_code }} · {{ detail.asset_name }}</a-descriptions-item>
          <a-descriptions-item v-if="detail.auto_close_at" label="自动关闭" :span="2">{{ formatTime(detail.auto_close_at) }} 前未确认将自动关闭</a-descriptions-item>
          <a-descriptions-item v-if="detail.contact" label="联系方式" :span="2">{{ detail.contact }}</a-descriptions-item>
          <a-descriptions-item label="问题描述" :span="2"><span class="pre-wrap">{{ detail.description }}</span></a-descriptions-item>
          <a-descriptions-item v-if="detail.resolution" label="处理结果" :span="2"><span class="pre-wrap">{{ detail.resolution }}</span></a-descriptions-item>
          <a-descriptions-item v-if="detail.rating" label="满意度" :span="2"><a-rate :value="detail.rating" disabled /></a-descriptions-item>
        </a-descriptions>

        <section v-if="can('claim') || can('assign')" class="service-action-block">
          <h3>接单与派单</h3>
          <a-space wrap>
            <a-button v-if="can('claim')" type="primary" :loading="acting" @click="claimTicket">我来接单</a-button>
            <template v-if="can('assign')">
              <a-select v-model:value="assigneeId" placeholder="选择处理人" :options="agents.map((agent) => ({ label: agent.display_name, value: agent.id }))" style="width:160px" />
              <a-button :loading="acting" @click="assignTicket">派单</a-button>
            </template>
          </a-space>
        </section>

        <section v-if="can('resolve')" class="service-action-block">
          <h3>处理工单</h3>
          <a-textarea v-model:value="resolution" :rows="3" placeholder="处理结果，提单人会收到通知并确认" class="service-action-input" />
          <a-button type="primary" :loading="acting" @click="resolveTicket">标记已解决</a-button>
          <a-textarea v-model:value="infoText" :rows="2" placeholder="需要提单人补充什么？例如：报错截图、设备编号" class="service-action-input" />
          <a-button :loading="acting" @click="requestInfo">请提单人补充信息</a-button>
        </section>

        <section v-if="can('transfer')" class="service-action-block">
          <h3>转派</h3>
          <a-space wrap>
            <a-select v-model:value="assigneeId" placeholder="转给谁" :options="transferTargets.map((agent) => ({ label: agent.display_name, value: agent.id }))" style="width:160px" />
            <a-input v-model:value="reason" :maxlength="500" placeholder="转派原因（选填）" style="width:220px" />
            <a-button :loading="acting" @click="transferTicket">转派</a-button>
          </a-space>
        </section>

        <section v-if="can('reply')" class="service-action-block">
          <h3>处理人需要你补充信息</h3>
          <a-textarea v-model:value="infoText" :rows="3" placeholder="按处理人的要求补充说明" class="service-action-input" />
          <a-button type="primary" :loading="acting" @click="replyInfo">提交补充信息</a-button>
        </section>

        <section v-if="can('close')" class="service-action-block">
          <h3>确认处理结果</h3>
          <div class="service-rating"><span>满意度</span><a-rate v-model:value="rating" /></div>
          <a-space wrap>
            <a-button type="primary" :loading="acting" @click="closeTicket">确认解决并关闭</a-button>
          </a-space>
          <a-textarea v-model:value="reason" :rows="2" placeholder="如果问题仍存在，请说明原因后重新打开" class="service-action-input" />
          <a-button :loading="acting" @click="reopenTicket">问题未解决，重新打开</a-button>
        </section>

        <section v-if="can('cancel')" class="service-action-block">
          <h3>撤回工单</h3>
          <a-textarea v-model:value="reason" :rows="2" placeholder="撤回原因，例如问题已自行解决" class="service-action-input" />
          <a-button danger :loading="acting" @click="cancelTicket">撤回工单</a-button>
        </section>

        <section class="service-action-block">
          <h3>处理记录</h3>
          <a-timeline>
            <a-timeline-item v-for="item in detail.events" :key="item.id" :color="item.kind === 'comment' ? 'gray' : 'blue'">
              <div class="service-event-head"><strong>{{ item.actor_name }}</strong><small>{{ formatTime(item.created_at) }}</small></div>
              <p class="pre-wrap">{{ item.content }}</p>
            </a-timeline-item>
          </a-timeline>
          <template v-if="can('comment')">
            <a-textarea v-model:value="comment" :rows="2" :maxlength="2000" placeholder="补充信息或回复对方" class="service-action-input" />
            <a-button :loading="acting" :disabled="!comment.trim()" @click="sendComment">发送回复</a-button>
          </template>
        </section>
      </template>
    </a-drawer>
  </div>
</template>

<style scoped>
.service-flow { margin-bottom: 16px; }
.service-ticket-toolbar { flex-wrap: wrap; gap: 12px; }
.service-ticket-title { margin: 0 0 10px; font-size: 18px; font-weight: 600; }
.service-ticket-tags { margin-bottom: 14px; }
.service-action-block { margin-top: 20px; padding-top: 16px; border-top: 1px solid #f0f0f0; }
.service-action-block h3 { margin: 0 0 10px; font-size: 14px; font-weight: 600; }
.service-action-input { margin: 10px 0 8px; }
.service-rating { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; color: #595959; }
.service-event-head { display: flex; gap: 8px; align-items: baseline; }
.service-event-head small { color: #8c8c8c; }
.service-action-block p { margin: 4px 0 0; color: #434343; }
.pre-wrap { white-space: pre-wrap; }
@media (max-width: 720px) {
  .service-ticket-toolbar { align-items: stretch; flex-direction: column; }
  .page-frame .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
