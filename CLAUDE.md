# Concert Radar — Engineering Conventions

Full build specification: `CONCERT_RADAR_SPEC.md` (schemas, contracts, phase plan). This file
is the short version every change must obey.

## Languages and style
- Python 3.12, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, pytest. Line length 100.
  `ruff` for lint/format, `mypy --strict`, `uv` per-service dependency management.
- `structlog` for logging; every log line includes `trace_id`, `span_id`, `service_name`.
  Never `print()` in committed code.
- `httpx` for HTTP clients (async), never `requests`. `aiokafka` for Kafka.
- TypeScript strict mode, no `any`. Next.js 14 App Router, Tailwind, pnpm.

## Architecture rules
- Services communicate via gRPC (sync internal) or Kafka (async events). Never direct HTTP
  between backend services. REST only at the gateway ↔ frontend boundary.
- Every service has `/healthz` and `/readyz`.
- Protobuf in `proto/` is the source of truth for inter-service contracts.
- Database migrations in `db/migrations/` are append-only. Never edit an existing migration.
- UUID primary keys via `gen_random_uuid()`; all timestamps `timestamptz`.

## Code quality
- Prefer standard library and well-known libraries. No exotic dependencies without
  justification.
- Every public function gets a type signature and a one-line docstring.
- No TODO comments in committed code. File issues instead.
- If you would write a comment explaining *what* code does (not *why*), rewrite the code.
- No dead code, speculative abstractions, or premature generalization.
- Tests assert on observable behavior (DB state, HTTP response, Kafka message), never on
  mocks. Every Kafka consumer must be idempotent.
