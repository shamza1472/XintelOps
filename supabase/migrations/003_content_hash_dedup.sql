-- Hash-based dedup for Cursor-native mode (no OpenAI embeddings required)
ALTER TABLE ingested_raw_feeds
  ADD COLUMN IF NOT EXISTS content_hash TEXT;

CREATE INDEX IF NOT EXISTS ingested_raw_feeds_content_hash_idx
  ON ingested_raw_feeds (content_hash, timestamp DESC);
