-- Canonical MPT video domain storage.
-- MPT owns writes through a server-side Supabase client. Blast/frontends may read
-- workspace-scoped history and artifacts, but actions should go through MPT APIs.

create or replace function public.try_cast_uuid(_text text)
returns uuid
language plpgsql
immutable
set search_path to 'public'
as $$
begin
  return _text::uuid;
exception when others then
  return null;
end;
$$;

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'mpt-videos',
  'mpt-videos',
  false,
  524288000,
  array[
    'video/mp4',
    'video/quicktime',
    'video/x-matroska',
    'video/x-msvideo',
    'audio/mpeg',
    'audio/mp4',
    'audio/aac',
    'audio/wav',
    'audio/x-wav',
    'audio/flac',
    'audio/ogg',
    'audio/opus',
    'image/jpeg',
    'image/png',
    'image/webp',
    'text/plain',
    'text/vtt',
    'application/json'
  ]::text[]
)
on conflict (id) do update
set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create table if not exists public.mpt_video_runs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  created_by uuid references auth.users(id) on delete set null,
  parent_run_id uuid references public.mpt_video_runs(id) on delete set null,
  request_id text,
  mpt_task_id text,
  status text not null default 'queued',
  title text not null default 'Video MPT',
  video_subject text not null,
  video_language text,
  video_aspect text,
  video_source text,
  voice_name text,
  bgm_type text,
  subtitle_enabled boolean,
  request_payload jsonb not null default '{}'::jsonb,
  effective_params jsonb not null default '{}'::jsonb,
  config_snapshot jsonb not null default '{}'::jsonb,
  capabilities_snapshot jsonb not null default '{}'::jsonb,
  generated_script text,
  generated_terms jsonb not null default '[]'::jsonb,
  progress integer not null default 0 check (progress >= 0 and progress <= 100),
  error_code text,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  deleted_at timestamptz,
  deleted_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint mpt_video_runs_status_check check (
    status in (
      'queued',
      'running',
      'completed',
      'completed_with_warnings',
      'failed',
      'cancelled',
      'deleted'
    )
  ),
  constraint mpt_video_runs_payload_object_check check (jsonb_typeof(request_payload) = 'object'),
  constraint mpt_video_runs_effective_params_object_check check (jsonb_typeof(effective_params) = 'object'),
  constraint mpt_video_runs_config_snapshot_object_check check (jsonb_typeof(config_snapshot) = 'object'),
  constraint mpt_video_runs_capabilities_snapshot_object_check check (jsonb_typeof(capabilities_snapshot) = 'object'),
  constraint mpt_video_runs_generated_terms_array_check check (jsonb_typeof(generated_terms) = 'array'),
  constraint mpt_video_runs_deleted_status_check check (
    (deleted_at is null and status <> 'deleted')
    or (deleted_at is not null)
  )
);

create unique index if not exists mpt_video_runs_mpt_task_id_idx
  on public.mpt_video_runs (mpt_task_id)
  where mpt_task_id is not null;

create index if not exists mpt_video_runs_workspace_user_updated_idx
  on public.mpt_video_runs (workspace_id, user_id, updated_at desc);

create index if not exists mpt_video_runs_workspace_status_updated_idx
  on public.mpt_video_runs (workspace_id, status, updated_at desc);

create index if not exists mpt_video_runs_parent_run_idx
  on public.mpt_video_runs (parent_run_id)
  where parent_run_id is not null;

create index if not exists mpt_video_runs_request_id_idx
  on public.mpt_video_runs (request_id)
  where request_id is not null;

create table if not exists public.mpt_generation_events (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references public.mpt_video_runs(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  event_status text not null default 'succeeded',
  step_name text,
  provider text,
  model text,
  input_summary jsonb not null default '{}'::jsonb,
  output_summary jsonb not null default '{}'::jsonb,
  usage_json jsonb not null default '{}'::jsonb,
  estimated_cost_usd numeric(12, 6),
  latency_ms integer check (latency_ms is null or latency_ms >= 0),
  error_code text,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint mpt_generation_events_status_check check (
    event_status in ('started', 'succeeded', 'failed', 'skipped')
  ),
  constraint mpt_generation_events_input_summary_object_check check (jsonb_typeof(input_summary) = 'object'),
  constraint mpt_generation_events_output_summary_object_check check (jsonb_typeof(output_summary) = 'object'),
  constraint mpt_generation_events_usage_json_object_check check (jsonb_typeof(usage_json) = 'object')
);

create index if not exists mpt_generation_events_run_created_idx
  on public.mpt_generation_events (run_id, created_at desc);

create index if not exists mpt_generation_events_workspace_created_idx
  on public.mpt_generation_events (workspace_id, created_at desc);

create index if not exists mpt_generation_events_type_idx
  on public.mpt_generation_events (event_type, created_at desc);

create table if not exists public.mpt_video_artifacts (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.mpt_video_runs(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  artifact_type text not null,
  storage_bucket text not null default 'mpt-videos',
  storage_path text not null,
  original_url text,
  file_name text,
  content_type text,
  file_size_bytes bigint check (file_size_bytes is null or file_size_bytes >= 0),
  duration_seconds numeric(12, 3) check (duration_seconds is null or duration_seconds >= 0),
  width integer check (width is null or width > 0),
  height integer check (height is null or height > 0),
  checksum_sha256 text,
  metadata jsonb not null default '{}'::jsonb,
  deleted_at timestamptz,
  deleted_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint mpt_video_artifacts_type_check check (
    artifact_type in (
      'video',
      'combined_video',
      'audio',
      'subtitle',
      'thumbnail',
      'script',
      'keywords',
      'material',
      'preview_audio',
      'log',
      'other'
    )
  ),
  constraint mpt_video_artifacts_bucket_check check (storage_bucket = 'mpt-videos'),
  constraint mpt_video_artifacts_metadata_object_check check (jsonb_typeof(metadata) = 'object'),
  constraint mpt_video_artifacts_path_workspace_check check (
    public.try_cast_uuid((storage.foldername(storage_path))[1]) = workspace_id
  )
);

create unique index if not exists mpt_video_artifacts_storage_path_idx
  on public.mpt_video_artifacts (storage_bucket, storage_path);

create index if not exists mpt_video_artifacts_run_type_idx
  on public.mpt_video_artifacts (run_id, artifact_type, created_at desc);

create index if not exists mpt_video_artifacts_workspace_created_idx
  on public.mpt_video_artifacts (workspace_id, created_at desc);

create table if not exists public.mpt_assets (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  asset_type text not null,
  storage_bucket text not null default 'mpt-videos',
  storage_path text not null,
  original_filename text,
  content_type text,
  file_size_bytes bigint check (file_size_bytes is null or file_size_bytes >= 0),
  duration_seconds numeric(12, 3) check (duration_seconds is null or duration_seconds >= 0),
  checksum_sha256 text,
  metadata jsonb not null default '{}'::jsonb,
  deleted_at timestamptz,
  deleted_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint mpt_assets_type_check check (
    asset_type in ('music', 'voiceover', 'material', 'thumbnail', 'font', 'other')
  ),
  constraint mpt_assets_bucket_check check (storage_bucket = 'mpt-videos'),
  constraint mpt_assets_metadata_object_check check (jsonb_typeof(metadata) = 'object'),
  constraint mpt_assets_path_workspace_check check (
    public.try_cast_uuid((storage.foldername(storage_path))[1]) = workspace_id
  )
);

create unique index if not exists mpt_assets_storage_path_idx
  on public.mpt_assets (storage_bucket, storage_path);

create index if not exists mpt_assets_workspace_type_created_idx
  on public.mpt_assets (workspace_id, asset_type, created_at desc);

create index if not exists mpt_assets_user_created_idx
  on public.mpt_assets (workspace_id, user_id, created_at desc);

create table if not exists public.mpt_usage_records (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references public.mpt_video_runs(id) on delete cascade,
  event_id uuid references public.mpt_generation_events(id) on delete set null,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  operation text not null,
  provider text,
  model text,
  usage_source text not null default 'unknown',
  prompt_tokens integer check (prompt_tokens is null or prompt_tokens >= 0),
  completion_tokens integer check (completion_tokens is null or completion_tokens >= 0),
  total_tokens integer check (total_tokens is null or total_tokens >= 0),
  input_characters integer check (input_characters is null or input_characters >= 0),
  output_characters integer check (output_characters is null or output_characters >= 0),
  estimated_cost_usd numeric(12, 6),
  actual_cost_usd numeric(12, 6),
  currency text not null default 'USD',
  latency_ms integer check (latency_ms is null or latency_ms >= 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint mpt_usage_records_source_check check (
    usage_source in ('real', 'estimated', 'manual', 'unknown')
  ),
  constraint mpt_usage_records_currency_check check (char_length(currency) = 3),
  constraint mpt_usage_records_metadata_object_check check (jsonb_typeof(metadata) = 'object')
);

create index if not exists mpt_usage_records_run_created_idx
  on public.mpt_usage_records (run_id, created_at desc);

create index if not exists mpt_usage_records_workspace_created_idx
  on public.mpt_usage_records (workspace_id, created_at desc);

create index if not exists mpt_usage_records_provider_model_idx
  on public.mpt_usage_records (provider, model, created_at desc);

alter table public.mpt_video_runs enable row level security;
alter table public.mpt_generation_events enable row level security;
alter table public.mpt_video_artifacts enable row level security;
alter table public.mpt_assets enable row level security;
alter table public.mpt_usage_records enable row level security;

drop policy if exists "Workspace members can read MPT video runs" on public.mpt_video_runs;
create policy "Workspace members can read MPT video runs"
on public.mpt_video_runs
for select
to authenticated
using (
  public.has_role(auth.uid(), 'admin')
  or public.is_workspace_member(auth.uid(), workspace_id)
);

drop policy if exists "Workspace members can read MPT generation events" on public.mpt_generation_events;
create policy "Workspace members can read MPT generation events"
on public.mpt_generation_events
for select
to authenticated
using (
  public.has_role(auth.uid(), 'admin')
  or public.is_workspace_member(auth.uid(), workspace_id)
);

drop policy if exists "Workspace members can read MPT video artifacts" on public.mpt_video_artifacts;
create policy "Workspace members can read MPT video artifacts"
on public.mpt_video_artifacts
for select
to authenticated
using (
  public.has_role(auth.uid(), 'admin')
  or public.is_workspace_member(auth.uid(), workspace_id)
);

drop policy if exists "Workspace members can read MPT assets" on public.mpt_assets;
create policy "Workspace members can read MPT assets"
on public.mpt_assets
for select
to authenticated
using (
  public.has_role(auth.uid(), 'admin')
  or public.is_workspace_member(auth.uid(), workspace_id)
);

drop policy if exists "Workspace members can read MPT usage records" on public.mpt_usage_records;
create policy "Workspace members can read MPT usage records"
on public.mpt_usage_records
for select
to authenticated
using (
  public.has_role(auth.uid(), 'admin')
  or public.is_workspace_member(auth.uid(), workspace_id)
);

drop policy if exists "mpt-videos: workspace members can read" on storage.objects;
create policy "mpt-videos: workspace members can read"
on storage.objects
for select
to authenticated
using (
  bucket_id = 'mpt-videos'
  and (
    public.has_role(auth.uid(), 'admin')
    or public.is_workspace_member(auth.uid(), public.try_cast_uuid((storage.foldername(name))[1]))
  )
);

drop trigger if exists set_updated_at_mpt_video_runs on public.mpt_video_runs;
create trigger set_updated_at_mpt_video_runs
  before update on public.mpt_video_runs
  for each row execute function public.update_updated_at_column();

drop trigger if exists set_updated_at_mpt_video_artifacts on public.mpt_video_artifacts;
create trigger set_updated_at_mpt_video_artifacts
  before update on public.mpt_video_artifacts
  for each row execute function public.update_updated_at_column();

drop trigger if exists set_updated_at_mpt_assets on public.mpt_assets;
create trigger set_updated_at_mpt_assets
  before update on public.mpt_assets
  for each row execute function public.update_updated_at_column();
