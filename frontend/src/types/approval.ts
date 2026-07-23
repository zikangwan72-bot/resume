export type ApprovalUserRole = string
export type ProcessAppStatus = 'draft' | 'published' | 'inactive'
export type ProcessVersionStatus = 'draft' | 'published'
export type ApprovalRequestStatus = 'pending' | 'approved' | 'rejected' | 'revoked'
export type ApprovalNodeStatus = 'pending' | 'approved' | 'rejected'
export type MonitorStatus = ApprovalRequestStatus
export type FlowNodeType = 'start' | 'approval' | 'countersign' | 'condition' | 'end'
export type ApprovalMode = 'single' | 'counter_sign'

export interface ApiEnvelope<T> { data: T }

export interface ApprovalUser {
  id: string
  email: string
  display_name: string
  department: string
  position: string
  role: ApprovalUserRole
  is_active: boolean
  created_at: string
}

export interface ApprovalUserInput {
  display_name: string
  email: string
  department: string
  position: string
  role: ApprovalUserRole
  is_active: boolean
}

export interface FormField {
  id: string
  key: string
  label: string
  type: 'text' | 'textarea' | 'number' | 'money' | 'date' | 'date_range' | 'radio' | 'checkbox' | 'select' | 'user' | 'department' | 'attachment' | 'section' | 'detail_table'
  required: boolean
  options?: string[]
  placeholder?: string
  help?: string
  min?: number
  max?: number
  precision?: number
  columns?: DetailColumn[]
}

export interface FormSchema { fields: FormField[] }

export type DetailColumnType = 'text' | 'number' | 'money' | 'date' | 'select'

export interface DetailColumn {
  id: string
  label: string
  type: DetailColumnType
  required: boolean
  options?: string[]
}

export interface ProcessAppDraft {
  id?: number
  code: string
  name: string
  category: string
  description: string
  form_schema: FormSchema
  flow_schema: FlowSchema
}

export interface FlowNodeDef {
  id: string
  index: number
  type: FlowNodeType
  name?: string
  label?: string
  approval_type?: ApprovalMode
  approver_id?: string
  approver_ids?: string[]
  allow_transfer?: boolean
  require_attachment?: boolean
  attachment_types?: string[]
  timeout_hours?: number
}

export interface FlowNodeSchema {
  id: string
  type: FlowNodeType
  name?: string
  label?: string
  approval_type?: ApprovalMode
  approver_id?: string
  approver_ids?: string[]
  [key: string]: unknown
}

export interface FlowEdgeSchema {
  source: string
  target: string
  condition?: Record<string, unknown>
  default?: boolean
}

export interface FlowSchema {
  nodes: FlowNodeSchema[]
  edges: FlowEdgeSchema[]
}

export interface ProcessVersion {
  id: number
  process_app_id: number
  version_number: number
  status: ProcessVersionStatus
  form_schema: FormSchema
  flow_schema: FlowSchema
  published_at: string | null
  created_at: string
}

export interface ProcessApp {
  id: number
  code: string
  name: string
  category: string
  description: string | null
  status: ProcessAppStatus
  version_id: number
  version_number: number | null
  version_status: ProcessVersionStatus | null
  current_version_id: number | null
  draft_version_number: number | null
  has_draft: boolean
  field_count: number
  approval_node_count: number
  form_schema: FormSchema
  flow_schema: FlowSchema
  published_at: string | null
  created_at: string
  updated_at: string
}

export interface ApprovalNode {
  id: number
  node_index: number
  node_key: string | null
  timeout_hours: number
  approver_id: string
  approver_name: string
  status: ApprovalNodeStatus
  comment: string | null
  acted_at: string | null
}

export interface ApprovalAction {
  id: number
  node_id: number
  actor_id: string
  actor_name: string
  action: string
  comment: string | null
  created_at: string
}

export interface ApprovalRequestDetail {
  id: number
  type_id: number | null
  process_app_id: number | null
  process_version_id: number | null
  applicant_id: string
  applicant_name: string
  applicant_snapshot: Record<string, unknown> | null
  title: string
  form_data: Record<string, unknown>
  form_schema_snapshot: FormSchema | Record<string, unknown> | null
  idempotency_key: string | null
  status: ApprovalRequestStatus
  current_node_index: number
  flow_snapshot: FlowNodeDef[]
  nodes: ApprovalNode[]
  actions: ApprovalAction[]
  created_at: string
  updated_at: string
  submitted_at: string | null
  completed_at: string | null
}

export interface MonitorSummary {
  total: number
  pending: number
  approved: number
  rejected: number
  revoked: number
  overdue: number
}

export interface MonitorPerson {
  id: string
  name: string
  email: string | null
  department: string | null
  position: string | null
}

export interface MonitorProcess {
  id: number | null
  code: string | null
  name: string | null
  version_id: number | null
  version_number: number | null
}

export interface MonitorCurrentNode {
  id: number | null
  node_index: number
  node_key: string | null | undefined
  name: string | null | undefined
  status: ApprovalNodeStatus | null
  timeout_hours: number
  created_at: string | null
}

export interface MonitorRequestItem {
  id: number
  title: string
  status: ApprovalRequestStatus
  submitted_at: string | null
  created_at: string
  process_app: MonitorProcess
  applicant: MonitorPerson
  current_node: MonitorCurrentNode
  current_approvers: MonitorPerson[]
  current_approver: MonitorPerson | null
  overdue: boolean
}

export interface MonitorRequestPage {
  items: MonitorRequestItem[]
  total: number
  page: number
  page_size: number
}

export interface ApprovalType {
  id: number
  name: string
  description: string | null
  is_active: boolean
  form_template: { id: number; name: string; fields: FormField[] } | null
}
