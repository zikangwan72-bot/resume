-- Cloud-ready schema additions for identity, assets, inventory and recruitment AI.

insert into public.roles (code, name) values
  ('platform_admin', '平台管理员'),
  ('recruitment_admin', '招聘管理员'),
  ('asset_admin', '资产管理员'),
  ('department_manager', '部门经理'),
  ('approval_finance', '财务审批'),
  ('employee', '员工')
on conflict (code) do update set name = excluded.name;

insert into public.permissions (code, name, module) values
  ('resume:manage', '管理招聘与AI筛选', 'resume'),
  ('recruitment:manage', '管理招聘流程', 'resume'),
  ('asset:manage', '管理资产台账', 'asset'),
  ('inventory:manage', '管理资产盘点', 'asset'),
  ('inventory:self_check', '员工自助盘点', 'asset'),
  ('inventory:review', '盘点差异复核', 'asset'),
  ('approval:review', '审批复核', 'approval'),
  ('approval:finance', '财务审批', 'approval')
on conflict (code) do update set name = excluded.name, module = excluded.module;

create table if not exists public.assets (
  id uuid primary key default gen_random_uuid(),
  asset_uuid uuid not null unique default gen_random_uuid(),
  qr_secret text not null default encode(gen_random_bytes(24), 'base64'),
  asset_code text not null unique,
  name text not null,
  category text not null,
  department text not null,
  owner text not null,
  location text not null,
  status text not null default '在用',
  purchase_date date,
  value numeric(14,2) not null default 0,
  last_inventory_at date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.inventory_tasks (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  scope text not null,
  owner text not null,
  status text not null default '草稿',
  due_date date,
  total_count integer not null default 0,
  checked_count integer not null default 0,
  exception_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.inventory_records (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.inventory_tasks(id) on delete cascade,
  asset_id uuid not null references public.assets(id) on delete cascade,
  result text not null default '未盘点',
  actual_location text,
  remark text,
  photo_url text,
  checked_by text,
  checked_at timestamptz
);

create table if not exists public.job_openings (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  department text not null,
  location text not null,
  employment_type text not null default '实习',
  description text not null,
  requirements text not null,
  status text not null default '开放',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.candidate_applications (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.job_openings(id) on delete cascade,
  name text not null,
  email text not null,
  phone text,
  school text,
  major text,
  graduation_year integer,
  resume_text text not null default '',
  cover_note text,
  status text not null default '待初筛',
  ai_status text not null default '未筛选',
  ai_score numeric(5,2),
  ai_summary text,
  ai_evidence jsonb,
  review_note text,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  unique(job_id, email)
);

alter table public.assets enable row level security;
alter table public.inventory_tasks enable row level security;
alter table public.inventory_records enable row level security;
alter table public.job_openings enable row level security;
alter table public.candidate_applications enable row level security;
