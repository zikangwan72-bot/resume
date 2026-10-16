-- Common PostgreSQL foundation for Enterprise AI Suite.
-- Run in a dedicated Supabase project after reviewing the RLS policies.

create extension if not exists "pgcrypto";

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '',
  department text not null default '',
  status text not null default 'active' check (status in ('active', 'disabled')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.roles (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.permissions (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  module text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.user_roles (
  user_id uuid not null references public.profiles(id) on delete cascade,
  role_id uuid not null references public.roles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, role_id)
);

create table if not exists public.role_permissions (
  role_id uuid not null references public.roles(id) on delete cascade,
  permission_id uuid not null references public.permissions(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (role_id, permission_id)
);

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  title text not null,
  content text not null,
  category text not null default 'system',
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.file_objects (
  id uuid primary key default gen_random_uuid(),
  bucket text not null,
  path text not null unique,
  owner_id uuid not null references public.profiles(id),
  mime_type text,
  size_bytes bigint,
  created_at timestamptz not null default now()
);

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid references public.profiles(id),
  action text not null,
  resource text not null,
  result text not null default 'success',
  request_id uuid not null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.ai_runs (
  id uuid primary key default gen_random_uuid(),
  module text not null,
  task_type text not null,
  model text not null,
  status text not null,
  latency_ms integer,
  estimated_cost numeric(12, 6),
  human_review boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.ai_feedback (
  id uuid primary key default gen_random_uuid(),
  ai_run_id uuid not null references public.ai_runs(id) on delete cascade,
  user_id uuid not null references public.profiles(id),
  rating smallint check (rating between 1 and 5),
  corrected_output text,
  created_at timestamptz not null default now()
);

create index if not exists idx_notifications_user_created on public.notifications(user_id, created_at desc);
create index if not exists idx_audit_resource_created on public.audit_logs(resource, created_at desc);
create index if not exists idx_ai_runs_module_created on public.ai_runs(module, created_at desc);

alter table public.profiles enable row level security;
alter table public.notifications enable row level security;
alter table public.file_objects enable row level security;
alter table public.ai_feedback enable row level security;

create policy "users read own profile" on public.profiles
  for select using (auth.uid() = id);
create policy "users read own notifications" on public.notifications
  for select using (auth.uid() = user_id);
create policy "users update own notifications" on public.notifications
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "users read own files" on public.file_objects
  for select using (auth.uid() = owner_id);
create policy "users create own feedback" on public.ai_feedback
  for insert with check (auth.uid() = user_id);

insert into public.roles (code, name) values
  ('platform_admin', '平台管理员'),
  ('recruitment_admin', '招聘管理员'),
  ('asset_admin', '资产管理员'),
  ('department_manager', '部门经理'),
  ('approval_finance', '财务审批'),
  ('employee', '员工')
on conflict (code) do nothing;

insert into public.permissions (code, name, module) values
  ('dashboard:view', '查看工作台', 'platform'),
  ('resume:view', '查看AI简历筛选', 'resume'),
  ('approval:view', '查看流程审批中心', 'approval'),
  ('asset:view', '查看全资产管理', 'asset'),
  ('service_desk:view', '查看IT服务台', 'service_desk'),
  ('notification:view', '查看通知', 'platform'),
  ('audit:view', '查看审计日志', 'governance'),
  ('ai_run:view', '查看AI运行记录', 'governance'),
  ('platform:manage', '管理平台', 'platform'),
  ('approval:manage', '管理审批流程', 'approval'),
  ('resume:manage', '管理招聘与AI筛选', 'resume'),
  ('recruitment:manage', '管理招聘流程', 'resume'),
  ('asset:manage', '管理资产台账', 'asset'),
  ('inventory:manage', '管理资产盘点', 'asset'),
  ('inventory:self_check', '员工自助盘点', 'asset'),
  ('inventory:review', '盘点差异复核', 'asset'),
  ('approval:review', '审批复核', 'approval'),
  ('approval:finance', '财务审批', 'approval')
on conflict (code) do nothing;
