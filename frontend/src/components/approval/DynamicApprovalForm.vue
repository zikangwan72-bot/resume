<script setup lang="ts">
import { computed, ref } from 'vue'
import ApprovalFieldControl from '@/components/approval/ApprovalFieldControl.vue'
import type { DetailColumn, FormField, FormSchema } from '@/types/approval'

type Value = string | number | string[] | Record<string, unknown>[] | null
const props = withDefaults(defineProps<{ schema: FormSchema | Record<string, unknown> | null; modelValue: Record<string, Value>; applicant?: Record<string, unknown> | null; readonly?: boolean; preview?: boolean }>(), { applicant: null, readonly: false, preview: false })
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, Value>]; validationChange: [errors: Record<string, string>] }>()
const errors = ref<Record<string, string>>({})
const fields = computed(() => Array.isArray((props.schema as FormSchema | null)?.fields) ? (props.schema as FormSchema).fields : [])
const supported = new Set(['text', 'textarea', 'number', 'money', 'date', 'date_range', 'radio', 'checkbox', 'select', 'user', 'department', 'attachment', 'section', 'detail_table'])
const keyOf = (field: Pick<FormField, 'id' | 'key'>) => field.id || field.key

function setValue(key: string, value: Value) { emit('update:modelValue', { ...props.modelValue, [key]: value }); validate({ ...props.modelValue, [key]: value }) }
function isEmpty(value: unknown) { return value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0) }
function numberError(field: Pick<FormField, 'label' | 'min' | 'max' | 'precision'>, value: unknown) {
  if (typeof value !== 'number' || Number.isNaN(value)) return `${field.label}必须是数字`
  if (field.min != null && value < field.min) return `${field.label}不能小于最小值`
  if (field.max != null && value > field.max) return `${field.label}不能大于最大值`
  if (field.precision != null && String(value).split('.')[1]?.length > field.precision) return `${field.label}最多保留 ${field.precision} 位小数`
  return ''
}
function columnError(column: DetailColumn, value: unknown) {
  if (column.required && isEmpty(value)) return `请填写：${column.label}`
  if (!isEmpty(value) && (column.type === 'number' || column.type === 'money')) return numberError(column, value)
  if (!isEmpty(value) && column.type === 'select' && !column.options?.includes(value as string)) return `${column.label}选项无效`
  return ''
}
function validate(values = props.modelValue) {
  const next: Record<string, string> = {}
  for (const field of fields.value) {
    const key = keyOf(field); const value = values[key]
    if (field.type === 'section') continue
    if (!supported.has(field.type)) next[key] = `${field.label}字段类型不受支持`
    else if (field.required && isEmpty(value)) next[key] = `请填写：${field.label}`
    else if (!isEmpty(value) && (field.type === 'number' || field.type === 'money')) next[key] = numberError(field, value)
    else if (!isEmpty(value) && ['radio', 'select'].includes(field.type) && !field.options?.includes(value as string)) next[key] = `${field.label}选项无效`
    else if (field.type === 'detail_table' && Array.isArray(value)) value.forEach((row, index) => {
      const detailRow = row as Record<string, unknown>
      for (const column of field.columns || []) {
        const columnKey = column.id || column.key
        const result = columnError(column, detailRow[columnKey])
        if (result) next[`${key}.${index}.${columnKey}`] = result
      }
    })
  }
  errors.value = Object.fromEntries(Object.entries(next).filter(([, value]) => value))
  emit('validationChange', errors.value)
  return Object.keys(errors.value).length === 0
}

defineExpose({ validate, setErrors: (next: Record<string, string>) => { errors.value = next; emit('validationChange', next) } })
</script>

<template>
  <a-descriptions v-if="applicant" title="申请人信息" bordered :column="{ xs: 1, sm: 2 }" class="applicant-info">
    <a-descriptions-item label="姓名">{{ applicant.display_name || applicant.name }}</a-descriptions-item>
    <a-descriptions-item label="邮箱">{{ applicant.email }}</a-descriptions-item>
    <a-descriptions-item label="部门">{{ applicant.department }}</a-descriptions-item>
    <a-descriptions-item label="职位">{{ applicant.position }}</a-descriptions-item>
  </a-descriptions>
  <a-form layout="vertical" class="dynamic-form">
    <template v-for="field in fields" :key="keyOf(field)">
      <ApprovalFieldControl v-if="field.type === 'section'" :field="field" :readonly="readonly" :preview="preview" />
      <a-alert v-else-if="!supported.has(field.type)" type="warning" show-icon :message="`${field.label}字段类型不受支持`" />
      <a-form-item v-else :label="field.label" :required="field.required" :extra="field.help" :help="errors[keyOf(field)]" :validate-status="errors[keyOf(field)] ? 'error' : undefined">
        <ApprovalFieldControl
          :field="field"
          :model-value="modelValue[keyOf(field)]"
          :readonly="readonly"
          :preview="preview"
          @update:model-value="setValue(keyOf(field), $event)"
        />
      </a-form-item>
    </template>
  </a-form>
</template>

<style scoped>
.applicant-info { margin-bottom: 20px; }
</style>
