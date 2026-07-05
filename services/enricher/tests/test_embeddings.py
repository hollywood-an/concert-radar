"""Embedding tests: shape, determinism, and the no-genre case."""

from src.embeddings import embed_genres


def test_embedding_is_384_dimensional() -> None:
    """The MiniLM vector matches the artists.embedding column dimension."""
    vector = embed_genres(["indie rock", "shoegaze", "dream pop"])
    assert vector is not None
    assert len(vector) == 384


def test_embedding_is_deterministic() -> None:
    """The same genre list embeds to the same vector."""
    first = embed_genres(["hardcore punk", "post-hardcore"])
    second = embed_genres(["hardcore punk", "post-hardcore"])
    assert first == second


def test_no_genres_yields_no_embedding() -> None:
    """An artist without genres gets no embedding (feed falls back to the 0.5 score)."""
    assert embed_genres([]) is None
