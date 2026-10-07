# ADR 001: Run Redpanda as the Kafka broker

## Status

Accepted.

## Context

The pipeline is event-driven: six services exchange messages over nine topics, consumers
commit offsets after each message, and replays must be safe. That calls for Kafka semantics
(partitioned, ordered per key, durable, consumer groups). It also has to run on a laptop, in
CI test containers, and on a single small production host. Apache Kafka needs a JVM, more
memory than the rest of the stack combined, and (before KRaft became the default) ZooKeeper.
A managed broker (Amazon MSK) starts around $0.75 an hour for the smallest cluster, more than
the entire demo host.

## Decision

Use Redpanda, a single-binary, Kafka-API-compatible broker, everywhere: docker-compose for
development, `testcontainers.kafka.RedpandaContainer` in tests, and one container capped at
512 MB in production. Services speak plain Kafka through `aiokafka`, with no Redpanda-specific
APIs.

## Consequences

- Starting the broker takes seconds, so every pipeline test runs against a real broker
  instead of a mock.
- Production memory for the broker is about 650 MB, which leaves room on a 4 GB host.
- Because only the Kafka protocol is used, moving to Apache Kafka or MSK later is a
  configuration change (`KAFKA_BOOTSTRAP_SERVERS`), not a code change.
- One broker means no replication: losing the host loses unconsumed messages. Acceptable
  for a demo whose source of truth is Postgres and whose input can be re-scraped.
