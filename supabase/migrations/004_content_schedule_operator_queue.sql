-- Extend content_schedule as the operator content queue (no separate queue table)
ALTER TABLE public.content_schedule
  ADD COLUMN IF NOT EXISTS active_now_signal text,
  ADD COLUMN IF NOT EXISTS active_now_format text,
  ADD COLUMN IF NOT EXISTS active_now_draft text,
  ADD COLUMN IF NOT EXISTS active_now_deadline timestamptz,
  ADD COLUMN IF NOT EXISTS active_now_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS active_now_reason text,
  ADD COLUMN IF NOT EXISTS active_now_source_package jsonb,
  ADD COLUMN IF NOT EXISTS later_signal text,
  ADD COLUMN IF NOT EXISTS later_format text,
  ADD COLUMN IF NOT EXISTS later_draft text,
  ADD COLUMN IF NOT EXISTS later_active_from timestamptz,
  ADD COLUMN IF NOT EXISTS later_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS later_status text,
  ADD COLUMN IF NOT EXISTS later_replaced_by text,
  ADD COLUMN IF NOT EXISTS later_reason text,
  ADD COLUMN IF NOT EXISTS queue_status text,
  ADD COLUMN IF NOT EXISTS operator_action_summary text;
