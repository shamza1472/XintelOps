-- Active live event memory + recommendation cooldown tracking
CREATE TABLE IF NOT EXISTS public.active_live_events (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  normalized_event_key TEXT NOT NULL,
  title TEXT NOT NULL,
  actors JSONB DEFAULT '[]'::jsonb,
  regions JSONB DEFAULT '[]'::jsonb,
  themes JSONB DEFAULT '[]'::jsonb,
  first_detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  active_until TIMESTAMPTZ NOT NULL,
  live_event_score INT,
  momentum_score INT,
  crisis_flag BOOLEAN DEFAULT FALSE,
  source_urls JSONB DEFAULT '[]'::jsonb,
  current_status TEXT DEFAULT 'active',
  latest_update_summary TEXT,
  previous_action TEXT,
  last_recommended_at TIMESTAMPTZ,
  times_recommended INT DEFAULT 0,
  resolved BOOLEAN DEFAULT FALSE,
  scan_session TEXT,
  freshness_class TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS active_live_events_key_idx
  ON public.active_live_events (normalized_event_key);

CREATE INDEX IF NOT EXISTS active_live_events_active_until_idx
  ON public.active_live_events (active_until DESC)
  WHERE resolved = FALSE;

CREATE TABLE IF NOT EXISTS public.signal_recommendations (
  id BIGSERIAL PRIMARY KEY,
  normalized_event_key TEXT NOT NULL,
  title TEXT NOT NULL,
  freshness_class TEXT,
  recommended_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  scan_session TEXT,
  action TEXT,
  live_event_score INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS signal_recommendations_key_time_idx
  ON public.signal_recommendations (normalized_event_key, recommended_at DESC);
