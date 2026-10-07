# ADR 007: JSON messages with Pydantic contracts on Kafka

## Status

Accepted. Departs from the spec's plan for protobuf in `proto/` as the source of truth for
every inter-service contract.

## Context

Seven topics carry small messages (an event id with a few fields, a user id with a list of
artist ids). Protobuf would add a schema directory, code generation in every service's build,
and generated code to keep out of linting, before there is a second language or an external
consumer that needs it.

## Decision

Messages are JSON. Each consumer declares the shape it reads as a Pydantic model in its own
`src/schemas.py` and validates every message (`model_validate_json`); a message that fails
validation is logged and skipped so it cannot wedge a partition. Producers serialize their own
Pydantic models. Every message carries W3C trace context in Kafka headers.

## Consequences

- Contracts are readable in the code that uses them, and adding an optional field does not
  break older consumers.
- Nothing enforces that producer and consumer models match: the pipeline tests (real broker,
  real producer payloads) are what catch drift, so each contract change ships with a test on
  both sides.
- If a contract needs strict cross-language guarantees (a non-Python consumer, or a schema
  registry), protobuf or JSON Schema can be introduced per topic without changing the others.
