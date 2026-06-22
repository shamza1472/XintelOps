-- Runtime proof: which branch/commit generated each scan
ALTER TABLE public.pipeline_log
  ADD COLUMN IF NOT EXISTS runtime_branch text,
  ADD COLUMN IF NOT EXISTS runtime_commit_sha text,
  ADD COLUMN IF NOT EXISTS scan_runtime_started_at timestamptz;
