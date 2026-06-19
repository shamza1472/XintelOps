-- XIntelOps vector schema and journalist engagement targets
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS trusted_sources (
  source_name TEXT PRIMARY KEY,
  reliability_score NUMERIC(3,2) DEFAULT 0.80,
  layer TEXT,
  domain TEXT
);

CREATE TABLE IF NOT EXISTS ingested_raw_feeds (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  raw_text TEXT NOT NULL,
  title TEXT,
  url TEXT,
  source_type TEXT DEFAULT 'news',
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  vector_embedding vector(1536),
  is_duplicate BOOLEAN DEFAULT FALSE,
  similarity_score NUMERIC(5,4)
);

CREATE TABLE IF NOT EXISTS synthesized_intelligence (
  id BIGSERIAL PRIMARY KEY,
  feed_ids BIGINT[],
  core_anomaly TEXT,
  red_team_analysis TEXT,
  strategist_implication TEXT,
  status TEXT DEFAULT 'pending_review',
  x_post TEXT,
  internal_brief TEXT,
  crisis_flag BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS journalist_engagement_targets (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  handle TEXT NOT NULL UNIQUE,
  outlet TEXT,
  category CHAR(1) NOT NULL,
  focus TEXT,
  region TEXT,
  profile_url TEXT,
  roster_tier TEXT NOT NULL,
  engagement_day TEXT,
  trust_level TEXT DEFAULT 'High',
  reliability_score NUMERIC(3,2) DEFAULT 0.85
);

CREATE INDEX IF NOT EXISTS ingested_raw_feeds_vector_idx
  ON ingested_raw_feeds
  USING ivfflat (vector_embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX IF NOT EXISTS ingested_raw_feeds_timestamp_idx
  ON ingested_raw_feeds (timestamp DESC);

CREATE INDEX IF NOT EXISTS journalist_engagement_targets_category_idx
  ON journalist_engagement_targets (category, roster_tier);
