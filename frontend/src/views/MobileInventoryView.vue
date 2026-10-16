<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CameraOutlined, CheckCircleOutlined, InboxOutlined, LoginOutlined, QrcodeOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import api from '@/api/client'
import { useAuthStore } from '@/stores/auth'

interface Asset {
  id: number
  asset_uuid: string
  asset_code: string
  name: string
  department: string
  owner: string
  location: string
  status: string
}

interface ActiveRecord {
  id: number
  task_id: number
  task_name: string
  task_scope: string
  task_due_date?: string
  task_status?: string
  result: string
  actual_location?: string
  checked_at?: string
  photo_url?: string
  checked_by?: string
  locked?: boolean
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const asset = ref<Asset | null>(null)
const activeRecord = ref<ActiveRecord | null>(null)
const loading = ref(false)
const submitting = ref(false)
const locked = ref(false)
const noActiveTask = ref(false)
const loadMessage = ref('')
const actualLocation = ref('')
const currentOwner = ref('')
const result = ref<'正常' | '位置不符' | '盘亏' | '损坏'>('正常')
const remark = ref('')
const photoData = ref('')
const photoName = ref('')
const token = computed(() => String(route.query.token || ''))
const assetUuid = computed(() => String(route.query.asset_uuid || ''))
const taskName = computed(() => activeRecord.value?.task_name || '当前暂无盘点任务')
const canSubmit = computed(() => Boolean(asset.value && activeRecord.value && !locked.value && !noActiveTask.value))
const submitButtonText = computed(() => photoData.value ? '提交本次盘点' : '先拍照，再提交')
const completedAt = computed(() => activeRecord.value?.checked_at ? new Date(activeRecord.value.checked_at).toLocaleString() : '未记录')

async function loadAsset() {
  if (!auth.isAuthenticated || !assetUuid.value || !token.value) return
  loading.value = true
  noActiveTask.value = false
  locked.value = false
  loadMessage.value = ''
  try {
    const response = await api.get('/api/v1/assets/mobile-inventory/asset', {
      params: { asset_uuid: assetUuid.value, token: token.value },
    })
    asset.value = response.data.data.asset
    activeRecord.value = response.data.data.active_record
    locked.value = Boolean(response.data.data.locked)
    noActiveTask.value = !activeRecord.value
    loadMessage.value = response.data.data.message || ''
    actualLocation.value = activeRecord.value?.actual_location || asset.value?.location || ''
    currentOwner.value = auth.user?.display_name || asset.value?.owner || ''
    if (locked.value && activeRecord.value?.result && activeRecord.value.result !== '未盘点') {
      result.value = activeRecord.value.result as typeof result.value
      photoData.value = activeRecord.value.photo_url || ''
    }
  } catch (error: any) {
    message.error(error.response?.data?.detail || '资产二维码无效或已更新')
  } finally {
    loading.value = false
  }
}

function goLogin() {
  localStorage.setItem('enterprise_ai_post_login_redirect', route.fullPath)
  router.push('/login')
}

function readPhoto(file: File) {
  if (!file.type.startsWith('image/')) {
    message.warning('请选择图片文件')
    return
  }
  photoName.value = file.name || '现场照片'
  const reader = new FileReader()
  reader.onload = () => {
    photoData.value = String(reader.result || '')
  }
  reader.readAsDataURL(file)
}

function pickPhoto(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) readPhoto(file)
}

function handlePaste(event: ClipboardEvent) {
  const file = Array.from(event.clipboardData?.files || []).find((item) => item.type.startsWith('image/'))
  if (file) {
    event.preventDefault()
    readPhoto(file)
  }
}

async function submitInventory() {
  if (!asset.value) return
  if (!activeRecord.value || noActiveTask.value) return message.warning('暂无进行中的盘点任务')
  if (locked.value) return message.warning('本次盘点任务已完成，不能重复提交')
  if (!actualLocation.value.trim()) return message.warning('请填写现场位置')
  if (!currentOwner.value.trim()) return message.warning('请填写现场使用人')
  if (!photoData.value) return message.warning('请上传或粘贴现场资产照片')
  submitting.value = true
  try {
    const response = await api.post('/api/v1/assets/mobile-inventory/scan', {
      asset_uuid: assetUuid.value,
      token: token.value,
      task_id: activeRecord.value?.task_id,
      result: result.value,
      actual_location: actualLocation.value,
      current_owner: currentOwner.value,
      remark: remark.value,
      photo_url: photoData.value,
    })
    activeRecord.value = { ...(activeRecord.value || {}), ...response.data.data, task_name: taskName.value, locked: true }
    locked.value = true
    message.success('盘点已提交')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '盘点提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadAsset)
</script>

<template>
  <main class="mobile-inventory-page" @paste="handlePaste">
    <section class="mobile-inventory-shell">
      <div class="mobile-inventory-brand"><span>EA</span> 员工自助盘点</div>
      <a-card :bordered="false" class="mobile-inventory-card">
        <a-spin :spinning="loading">
          <template v-if="!assetUuid || !token">
            <a-result status="warning" title="二维码参数不完整" sub-title="请重新扫描贴在资产上的二维码。" />
          </template>
          <template v-else-if="!auth.isAuthenticated">
            <a-result title="需要员工登录" sub-title="登录后会返回当前资产盘点页。">
              <template #icon><LoginOutlined /></template>
              <template #extra><a-button type="primary" @click="goLogin">去登录</a-button></template>
            </a-result>
          </template>
          <template v-else-if="asset">
            <div class="mobile-inventory-hero" :class="{ locked }">
              <QrcodeOutlined />
              <div>
                <span>{{ taskName }}</span>
                <h1>{{ asset.name }}</h1>
                <p>{{ asset.asset_code }} · {{ asset.department }}</p>
              </div>
              <a-tag :color="locked ? 'green' : noActiveTask ? 'default' : 'processing'">{{ locked ? '已完成' : noActiveTask ? '无任务' : '待盘点' }}</a-tag>
            </div>

            <a-alert v-if="noActiveTask" type="warning" show-icon :message="loadMessage || '暂无进行中的盘点任务'" description="请联系资产管理员发起并启动盘点任务后再扫码。" class="mobile-inventory-alert" />
            <a-alert v-else-if="locked" type="success" show-icon message="本次盘点任务已完成，不能重复提交。" description="下一次新的盘点任务启动后，扫描同一个资产二维码可重新盘点。" class="mobile-inventory-alert" />

            <section class="mobile-info-section">
              <h2>台账信息</h2>
              <div class="mobile-ledger-grid">
                <div><span>台账位置</span><strong>{{ asset.location }}</strong></div>
                <div><span>台账责任人</span><strong>{{ asset.owner }}</strong></div>
                <div><span>资产状态</span><strong>{{ asset.status }}</strong></div>
                <div><span>固定ID</span><strong>{{ asset.asset_uuid }}</strong></div>
              </div>
              <div v-if="activeRecord" class="mobile-task-strip">
                <span>任务范围</span>
                <strong>{{ activeRecord.task_scope || '未设置' }}</strong>
                <small v-if="activeRecord.task_due_date">截止：{{ activeRecord.task_due_date }}</small>
              </div>
            </section>

            <section v-if="locked && activeRecord" class="mobile-info-section">
              <h2>已提交结果</h2>
              <div class="mobile-result-card">
                <div><span>盘点结果</span><a-tag :color="activeRecord.result === '正常' ? 'green' : 'orange'">{{ activeRecord.result }}</a-tag></div>
                <div><span>现场位置</span><strong>{{ activeRecord.actual_location || '未填写' }}</strong></div>
                <div><span>提交人</span><strong>{{ activeRecord.checked_by || '未记录' }}</strong></div>
                <div><span>提交时间</span><strong>{{ completedAt }}</strong></div>
              </div>
              <img v-if="activeRecord.photo_url" class="inventory-photo-preview locked-preview" :src="activeRecord.photo_url" alt="已提交现场资产照片" />
            </section>

            <a-form v-if="canSubmit" layout="vertical" class="mobile-inventory-form">
              <section class="mobile-info-section">
                <h2>现场录入</h2>
                <a-form-item label="现场位置" required><a-input v-model:value="actualLocation" placeholder="例如：深圳办公室 3F 工位 A12" /></a-form-item>
                <a-form-item label="现场使用人" required><a-input v-model:value="currentOwner" placeholder="填写实际保管/使用人" /></a-form-item>
                <a-form-item label="资产盘点结果" required>
                  <a-segmented v-model:value="result" :options="['正常','位置不符','盘亏','损坏']" block />
                </a-form-item>
                <a-form-item label="盘点说明"><a-textarea v-model:value="remark" :rows="3" placeholder="如位置变化、资产外观、损坏情况等" /></a-form-item>
              </section>

              <section class="mobile-info-section">
                <h2>现场照片</h2>
                <div class="photo-paste-zone" :class="{ ready: photoData }" tabindex="0">
                  <InboxOutlined v-if="!photoData" />
                  <img v-else class="photo-inline-preview" :src="photoData" alt="现场资产照片预览" />
                  <strong>{{ photoData ? '照片已添加' : '拍照上传资产现场照片' }}</strong>
                  <span>{{ photoData ? photoName || '现场照片' : '拍清资产本体和周边位置，作为本次盘点凭证。' }}</span>
                  <label class="photo-upload-button">
                    <CameraOutlined /> {{ photoData ? '重新拍照' : '打开相机 / 选择照片' }}
                    <input type="file" accept="image/*" capture="environment" @change="pickPhoto" />
                  </label>
                </div>
              </section>

              <a-button type="primary" block size="large" :loading="submitting" :disabled="!photoData" class="mobile-submit-button" @click="submitInventory">
                <CheckCircleOutlined /> {{ submitButtonText }}
              </a-button>
            </a-form>
          </template>
        </a-spin>
      </a-card>
    </section>
  </main>
</template>
