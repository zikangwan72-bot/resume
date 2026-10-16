<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { DeleteOutlined, EditOutlined, PauseCircleOutlined, PlusOutlined, RobotOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import api from '@/api/client'
import PageBackButton from '@/components/PageBackButton.vue'

const jobs = ref<any[]>([])
const loading = ref(true)
const open = ref(false)
const editing = ref<any | null>(null)
const form = ref({
  name: '',
  description: '',
  required_skills: '',
  preferred_skills: '',
  rejection_conditions: '',
})
const selectedTags = ref<string[]>([])
const suggestedTags = ref<string[]>([])
const tagInput = ref('')
const tagLoading = ref(false)

function list(value: string) {
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function editJob(job?: any) {
  editing.value = job || null
  form.value = {
    name: job?.name || '',
    description: job?.description || '',
    required_skills: (job?.required_skills || []).join('\n'),
    preferred_skills: (job?.preferred_skills || []).join('\n'),
    rejection_conditions: (job?.rejection_conditions || []).join('\n'),
  }
  selectedTags.value = [...(job?.preferred_skills || [])]
  suggestedTags.value = []
  tagInput.value = ''
  open.value = true
}

async function generateTags() {
  if (!form.value.name.trim()) return message.warning('请先填写岗位名称')
  tagLoading.value = true
  try {
    const response = await api.post('/api/v1/screening/jobs/suggest-tags', {
      name: form.value.name,
      description: form.value.description,
      required_skills: list(form.value.required_skills),
    })
    suggestedTags.value = (response.data.data?.tags || []).filter((tag: string) => !selectedTags.value.includes(tag))
    if (!suggestedTags.value.length) message.info('AI 暂未生成新的岗位标签')
  } catch (error: any) {
    message.error(error.response?.data?.detail || 'AI 岗位标签生成失败，可继续手动添加标签')
  } finally {
    tagLoading.value = false
  }
}

function addTag(tag: string) {
  const value = tag.trim()
  if (value && !selectedTags.value.includes(value)) selectedTags.value.push(value)
  suggestedTags.value = suggestedTags.value.filter((item) => item !== value)
  tagInput.value = ''
}

function removeTag(tag: string) {
  selectedTags.value = selectedTags.value.filter((item) => item !== tag)
}

async function load() {
  loading.value = true
  try {
    jobs.value = (await api.get('/api/v1/screening/jobs')).data.data || []
  } catch (error: any) {
    message.error(error.response?.data?.detail || '岗位标准加载失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.name.trim()) return message.warning('请输入岗位名称')
  const payload = {
    ...form.value,
    required_skills: list(form.value.required_skills),
    preferred_skills: [...new Set([...list(form.value.preferred_skills), ...selectedTags.value])],
    rejection_conditions: list(form.value.rejection_conditions),
  }

  try {
    if (editing.value) await api.patch(`/api/v1/screening/jobs/${editing.value.id}`, payload)
    else await api.post('/api/v1/screening/jobs', payload)
    message.success(editing.value ? '岗位标准已更新' : '岗位标准已创建')
    open.value = false
    await load()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '保存失败')
  }
}

async function deactivate(job: any) {
  try {
    await api.patch(`/api/v1/screening/jobs/${job.id}`, { status: 'inactive' })
    message.success('岗位标准已停用')
    await load()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '停用失败')
  }
}

async function deleteJob(job: any) {
  try {
    await api.delete(`/api/v1/screening/jobs/${job.id}`)
    message.success('岗位标准已删除')
    await load()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="page-frame screening-jobs-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">SCREENING CONFIGURATION</p>
        <h1>岗位标准</h1>
        <p>把岗位要求结构化，作为每次 AI 筛选的统一依据。</p>
      </div>
      <div class="heading-actions">
        <PageBackButton fallback="/modules/resume-screening" />
        <a-button type="primary" @click="editJob()"><PlusOutlined />新建岗位标准</a-button>
      </div>
    </header>

    <a-card class="plain-panel" :bordered="false">
      <a-table
        :loading="loading"
        :data-source="jobs"
        row-key="id"
        :pagination="false"
        :scroll="{ x: 980 }"
        :columns="[
          { title: '岗位名称', dataIndex: 'name', width: 250 },
          { title: '必备技能', dataIndex: 'required_skills', width: 320 },
          { title: '岗位加分标签', dataIndex: 'preferred_skills', width: 300 },
          { title: '状态', dataIndex: 'status', width: 110 },
          { title: '操作', dataIndex: 'action', width: 300, align: 'right' },
        ]"
        class="data-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'required_skills' || column.dataIndex === 'preferred_skills'">
            <a-space wrap>
              <a-tag v-for="skill in record[column.dataIndex] || []" :key="skill">{{ skill }}</a-tag>
              <span v-if="!(record[column.dataIndex] || []).length">-</span>
            </a-space>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :color="record.status === 'active' || record.status === '启用' ? 'green' : 'default'">
              {{ record.status === 'active' ? '启用' : record.status === 'inactive' ? '停用' : record.status || '启用' }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'action'">
            <div class="job-action-grid">
              <span class="job-action-slot">
                <a-button size="small" @click="editJob(record)"><EditOutlined />编辑</a-button>
              </span>
              <span class="job-action-slot">
                <a-popconfirm v-if="record.status !== 'inactive' && record.status !== '停用'" title="确认停用该岗位标准？" @confirm="deactivate(record)">
                  <a-button size="small" danger><PauseCircleOutlined />停用</a-button>
                </a-popconfirm>
              </span>
              <span class="job-action-slot"><a-popconfirm
                title="确认删除该岗位标准？"
                description="删除后不可恢复；已有筛选结果的岗位只能停用。"
                ok-text="删除"
                cancel-text="取消"
                @confirm="deleteJob(record)"
              >
                <a-button size="small" danger>
                  <DeleteOutlined />删除
                </a-button>
              </a-popconfirm></span>
            </div>
          </template>
          <template v-else>{{ record[column.dataIndex] || '-' }}</template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="open"
      :title="editing ? '编辑岗位标准' : '新建岗位标准'"
      width="760px"
      :style="{ top: '24px' }"
      :body-style="{ maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', paddingRight: '20px' }"
      ok-text="保存"
      cancel-text="取消"
      @ok="save"
    >
      <a-form layout="vertical" class="job-standard-form">
        <section class="form-section">
          <div class="form-section-title">
            <strong>这个岗位要找什么样的人</strong>
            <span>按招聘经理能说清楚的方式填写</span>
          </div>
          <a-form-item label="岗位名称">
            <a-input v-model:value="form.name" placeholder="例如：高级产品经理" />
          </a-form-item>
          <a-form-item label="岗位画像">
            <a-textarea
              v-model:value="form.description"
              :rows="3"
              placeholder="例如：负责 AI 简历筛选产品，从需求分析到上线验收都能推进"
            />
          </a-form-item>
        </section>

        <section class="form-section required-skills-section">
          <a-form-item label="必须会什么">
            <a-textarea
              v-model:value="form.required_skills"
              placeholder="每行写一条：产品需求分析、原型设计、B端项目经验"
              :rows="4"
            />
          </a-form-item>
        </section>

        <section class="form-section tag-section">
          <div class="form-section-title"><div><strong>岗位加分标签</strong><span>由岗位名称和岗位画像生成，也可以手动添加</span></div><a-button size="small" :loading="tagLoading" @click="generateTags"><RobotOutlined />AI 生成岗位标签</a-button></div>
          <a-input v-model:value="tagInput" placeholder="输入标签后回车，例如：B 端产品经验" @press-enter="addTag(tagInput)"><template #suffix><a-button type="link" size="small" :disabled="!tagInput.trim()" @click="addTag(tagInput)">添加</a-button></template></a-input>
          <div v-if="selectedTags.length" class="tag-list selected-tag-list"><a-tag v-for="tag in selectedTags" :key="tag" closable color="blue" @close="removeTag(tag)">{{ tag }}</a-tag></div>
          <div v-if="suggestedTags.length" class="tag-suggestion-block"><span>建议标签</span><div class="tag-list"><a-tag v-for="tag in suggestedTags" :key="tag" class="suggested-tag" @click="addTag(tag)"><PlusOutlined />{{ tag }}</a-tag></div></div>
          <a-alert v-if="selectedTags.length" type="info" show-icon :message="`已选择 ${selectedTags.length} 个加分标签`" />
        </section>

        <section class="form-section">
          <a-form-item label="哪些情况直接不合适">
            <a-textarea
              v-model:value="form.rejection_conditions"
              placeholder="每行写一条：没有相关项目经验、只做过纯执行、简历信息严重不完整"
              :rows="3"
            />
          </a-form-item>
        </section>

      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.job-standard-form {
  display: grid;
  gap: 14px;
}

.form-section {
  padding: 14px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fff;
}

.form-section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.form-section-title strong {
  font-size: 15px;
}

.form-section-title span {
  color: #8c8c8c;
  font-size: 12px;
}

.required-skills-section :deep(.ant-form-item) {
  margin-bottom: 0;
}

.required-skills-section :deep(.ant-input) {
  width: 100%;
}

.job-action-grid {
  display: grid;
  grid-template-columns: repeat(3, 82px);
  gap: 8px;
  justify-content: end;
  align-items: center;
}

.job-action-slot {
  min-width: 82px;
  display: flex;
  justify-content: flex-end;
}

.job-action-slot :deep(.ant-btn) {
  width: 82px;
}

.tag-section .form-section-title > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.selected-tag-list {
  min-height: 32px;
  padding: 8px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafafa;
}

.tag-suggestion-block {
  margin-top: 12px;
  color: #8c8c8c;
  font-size: 12px;
}

.suggested-tag {
  cursor: pointer;
  color: #1677ff;
  border-style: dashed;
}

.tag-section .ant-alert {
  margin-top: 12px;
}

@media (max-width: 768px) {
  .job-action-grid {
    grid-template-columns: repeat(3, 74px);
  }

  .job-action-slot,
  .job-action-slot :deep(.ant-btn) {
    min-width: 74px;
    width: 74px;
  }
}
</style>
