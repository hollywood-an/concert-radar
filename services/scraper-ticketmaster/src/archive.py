"""Archive raw Discovery API pages to S3 so every scrape can be audited or replayed."""

import asyncio
import gzip
import json
from datetime import UTC, datetime
from typing import Any

import boto3
from opentelemetry import trace

tracer = trace.get_tracer("scraper-ticketmaster")


class RawPageArchive:
    """Writes one scrape run's pages as gzipped JSON under Hive-style partitioned keys."""

    def __init__(
        self,
        bucket: str,
        dma_id: int,
        endpoint_url: str | None = None,
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        """Stamp the run's start time and build an S3 client; empty keys use the default chain."""
        started_at = datetime.now(UTC)
        self._bucket = bucket
        self._prefix = (
            f"raw/ticketmaster/dma={dma_id}/dt={started_at:%Y-%m-%d}"
            f"/run={started_at:%Y%m%dT%H%M%SZ}"
        )
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )

    async def put_page(self, page_number: int, payload: dict[str, Any]) -> str:
        """Upload one page tagged with the current trace id and return its object key."""
        key = f"{self._prefix}/page-{page_number}.json.gz"
        body = gzip.compress(json.dumps(payload).encode())
        with tracer.start_as_current_span(
            "archive.put", attributes={"aws.s3.bucket": self._bucket, "aws.s3.key": key}
        ) as span:
            trace_id = format(span.get_span_context().trace_id, "032x")
            await asyncio.to_thread(
                self._s3.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                ContentEncoding="gzip",
                Metadata={"trace-id": trace_id},
            )
        return key
