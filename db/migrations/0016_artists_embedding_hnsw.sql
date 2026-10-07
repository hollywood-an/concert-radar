-- 0002 built idx_artists_embedding as ivfflat (lists = 100) on an empty table. IVFFlat
-- picks its list centroids from the rows present at build time, so those lists carry no
-- information and nearest-artist queries probe the wrong ones and miss close matches.
-- HNSW needs no training data and keeps its recall as artists are inserted.
DROP INDEX idx_artists_embedding;
CREATE INDEX idx_artists_embedding_hnsw ON artists USING hnsw (embedding vector_cosine_ops);
