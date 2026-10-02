"""Raw-page archive tests: a fixture run leaves its page in a real MinIO bucket."""

import gzip
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client
from opentelemetry import trace
from testcontainers.minio import MinioContainer

from src.config import Settings
from src.main import run
from tests.conftest import FIXTURE_PATH, consume_discovered

# minio/minio is no longer pullable from Docker Hub; pgsty/minio is its maintained community fork.
MINIO_IMAGE = "pgsty/minio:RELEASE.2026-08-04T00-00-00Z"
BUCKET = "raw-archive"
DMA_ID = 259
PREFIX = f"raw/ticketmaster/dma={DMA_ID}/"
KEY_PATTERN = re.compile(
    re.escape(PREFIX) + r"dt=(?P<dt>\d{4}-\d{2}-\d{2})/run=(?P<run>\d{8}T\d{6}Z)/page-0\.json\.gz"
)


@pytest.fixture(scope="module")
def minio() -> Iterator[MinioContainer]:
    """Start MinIO in a container for the module's archive tests."""
    with MinioContainer(MINIO_IMAGE) as container:
        yield container


@pytest.fixture
def s3(minio: MinioContainer) -> S3Client:
    """Return a boto3 client for the MinIO container."""
    config = minio.get_config()
    return boto3.client(
        "s3",
        endpoint_url=f"http://{config['endpoint']}",
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
    )


@pytest.fixture
def scraper_env(monkeypatch: pytest.MonkeyPatch, kafka_bootstrap: str) -> pytest.MonkeyPatch:
    """Point the scraper at the test broker and a fixed DMA; return monkeypatch for more env."""
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", kafka_bootstrap)
    monkeypatch.setenv("TICKETMASTER_DMA_ID", str(DMA_ID))
    return monkeypatch


@pytest.fixture
def minio_env(scraper_env: pytest.MonkeyPatch, minio: MinioContainer) -> pytest.MonkeyPatch:
    """Also point the scraper's S3 endpoint and keys at the MinIO container."""
    config = minio.get_config()
    scraper_env.setenv("S3_ENDPOINT_URL", f"http://{config['endpoint']}")
    scraper_env.setenv("S3_ACCESS_KEY", config["access_key"])
    scraper_env.setenv("S3_SECRET_KEY", config["secret_key"])
    return scraper_env


async def _traced_run() -> tuple[int, str]:
    """Run the fixture scrape under a test span; return its exit code and trace id."""
    with trace.get_tracer("test").start_as_current_span("test run") as span:
        exit_code = await run(FIXTURE_PATH)
    return exit_code, format(span.get_span_context().trace_id, "032x")


async def test_fixture_run_archives_raw_page(
    minio_env: pytest.MonkeyPatch, s3: S3Client, payload: dict[str, Any]
) -> None:
    """A fixture run stores one gzipped copy of its page, keyed by run time and trace-tagged."""
    s3.create_bucket(Bucket=BUCKET)
    minio_env.setenv("S3_BUCKET", BUCKET)

    started = datetime.now(UTC).replace(microsecond=0)
    exit_code, trace_id = await _traced_run()
    finished = datetime.now(UTC)
    assert exit_code == 0

    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX)
    keys = [obj["Key"] for obj in listing.get("Contents", [])]
    assert len(keys) == 1
    match = KEY_PATTERN.fullmatch(keys[0])
    assert match is not None, keys[0]
    run_at = datetime.strptime(match["run"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    assert started <= run_at <= finished
    assert match["dt"] == run_at.date().isoformat()

    archived = s3.get_object(Bucket=BUCKET, Key=keys[0])
    assert archived["ContentType"] == "application/json"
    assert archived["ContentEncoding"] == "gzip"
    assert archived["Metadata"]["trace-id"] == trace_id
    assert json.loads(gzip.decompress(archived["Body"].read())) == payload


async def test_failed_upload_fails_the_run(minio_env: pytest.MonkeyPatch) -> None:
    """A page that cannot be archived makes the run raise rather than carry on."""
    minio_env.setenv("S3_BUCKET", "no-such-bucket")

    with pytest.raises(ClientError, match="NoSuchBucket"):
        await run(FIXTURE_PATH)


async def test_run_without_bucket_skips_archive(
    scraper_env: pytest.MonkeyPatch, kafka_bootstrap: str
) -> None:
    """With S3_BUCKET empty the run needs no S3 at all and still publishes every event."""
    scraper_env.setenv("S3_BUCKET", "")

    exit_code, trace_id = await _traced_run()

    assert exit_code == 0
    assert len(await consume_discovered(kafka_bootstrap, trace_id, 9)) == 9


def test_blank_or_placeholder_s3_settings_are_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank or `<...>` S3 values fall back to AWS defaults instead of being sent to boto3."""
    monkeypatch.setenv("S3_BUCKET", "<your bucket>")
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("S3_ACCESS_KEY", "<your access key>")
    monkeypatch.setenv("S3_SECRET_KEY", "<your secret key>")

    settings = Settings()

    assert settings.s3_bucket == ""
    assert settings.s3_endpoint_url is None
    assert settings.s3_access_key == ""
    assert settings.s3_secret_key == ""
