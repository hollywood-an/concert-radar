CREATE OR REPLACE FUNCTION relevance_score(
    user_vec vector,
    artist_vec vector,
    show_date TIMESTAMPTZ
) RETURNS FLOAT AS $$
    SELECT
        CASE
            WHEN user_vec IS NULL OR artist_vec IS NULL THEN 0.5
            ELSE (1 - (user_vec <=> artist_vec)) * 0.7
                 + exp(-extract(epoch FROM (show_date - now())) / 2592000.0) * 0.3
        END
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION update_user_taste_embedding(p_user_id UUID)
RETURNS VOID AS $$
    UPDATE users
    SET taste_embedding = (
        SELECT avg(a.embedding)
        FROM follows f
        JOIN artists a ON a.id = f.artist_id
        WHERE f.user_id = p_user_id
          AND a.embedding IS NOT NULL
    ),
    updated_at = now()
    WHERE id = p_user_id;
$$ LANGUAGE sql;
