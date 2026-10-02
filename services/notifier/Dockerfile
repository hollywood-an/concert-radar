# syntax=docker/dockerfile:1.7
# Build: docker build -t concert-radar/notifier services/notifier

FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# src/config.py resolves the repo root as parents[3], so the service must sit three
# directories deep (/srv/services/notifier/src) or importing the settings fails.
WORKDIR /srv/services/notifier
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev
COPY src ./src

FROM python:3.12-slim-bookworm
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /srv/services/notifier
COPY --from=builder /srv/services/notifier /srv/services/notifier
ENV PATH="/srv/services/notifier/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
CMD ["python", "-m", "src.main"]
