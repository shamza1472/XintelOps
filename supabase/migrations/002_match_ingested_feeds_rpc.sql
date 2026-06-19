-- RPC for semantic similarity search over ingested_raw_feeds
CREATE OR REPLACE FUNCTION match_ingested_feeds(
  query_embedding vector(1536),
  match_threshold float,
  match_count int,
  days_back int DEFAULT 7
)
RETURNS TABLE (
  id bigint,
  source text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    f.id,
    f.source,
    1 - (f.vector_embedding <=> query_embedding) AS similarity
  FROM ingested_raw_feeds f
  WHERE f.timestamp > NOW() - (days_back || ' days')::interval
    AND f.vector_embedding IS NOT NULL
    AND 1 - (f.vector_embedding <=> query_embedding) >= match_threshold
  ORDER BY f.vector_embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
