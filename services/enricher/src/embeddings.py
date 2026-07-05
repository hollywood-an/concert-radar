"""Genre-string embeddings via sentence-transformers/all-MiniLM-L6-v2.

The join format and normalization must stay byte-identical with the seed generator
(db/seeds/genres.sql) so seeded and enriched artists live in the same vector space.
"""

from functools import lru_cache
from typing import Any

from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model() -> Any:
    """Load the embedding model once per process (untyped upstream, hence Any)."""
    return SentenceTransformer(MODEL_NAME)


def embed_genres(genres: list[str]) -> list[float] | None:
    """Embed the joined genre string as a 384-dim vector; None when there are no genres."""
    if not genres:
        return None
    vector = _model().encode(", ".join(genres), normalize_embeddings=False)
    return [float(value) for value in vector]
