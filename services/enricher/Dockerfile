# syntax=docker/dockerfile:1.7
# Build: docker build -t concert-radar/enricher services/enricher

FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never HF_HOME=/srv/hf
# src/config.py resolves the repo root as parents[3], so the service must sit three
# directories deep (/srv/services/enricher/src) or importing the settings fails.
WORKDIR /srv/services/enricher
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev
# Bake the embedding model into the image so the container never needs the Hugging
# Face Hub at startup and every deploy embeds with exactly the same weights.
RUN .venv/bin/python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
COPY src ./src

FROM python:3.12-slim-bookworm
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /srv/services/enricher
COPY --from=builder /srv/hf /srv/hf
COPY --from=builder /srv/services/enricher /srv/services/enricher
ENV PATH="/srv/services/enricher/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    HF_HOME=/srv/hf HF_HUB_OFFLINE=1
USER app
CMD ["python", "-m", "src.main"]
