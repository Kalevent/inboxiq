from typing import Any, Optional, TYPE_CHECKING

try:
    import boto3
except ImportError as exc:  # pragma: no cover - optional runtime dependency
    boto3 = None
    _import_error = exc
else:
    _import_error = None

if TYPE_CHECKING:
    from botocore.client import BaseClient  # pragma: no cover
else:
    BaseClient = Any  # type: ignore

from flask import current_app


_s3_client: Optional[BaseClient] = None


def _get_s3() -> BaseClient:
    """Return a cached boto3 S3 client."""
    if boto3 is None:
        raise RuntimeError("boto3 is required for uploads") from _import_error
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def build_public_url(key: str) -> str:
    """Build a public URL for an uploaded object using UPLOADS_HOST."""
    host = current_app.config.get("UPLOADS_HOST")
    if not host:
        raise RuntimeError("UPLOADS_HOST is not configured")
    key_part = key.lstrip("/")
    return f"{host.rstrip('/')}/{key_part}"


def upload_bytes(
    key: str,
    data: bytes,
    *,
    content_type: str = "application/octet-stream",
    content_disposition: str = "attachment",
) -> str:
    """
    Upload bytes to S3 and return the public URL.

    The object is stored privately; CloudFront serves it via the uploads host.
    """
    bucket = current_app.config.get("UPLOADS_BUCKET")
    if not bucket:
        raise RuntimeError("UPLOADS_BUCKET is not configured")
    if not data:
        raise ValueError("Cannot upload empty payload")

    _get_s3().put_object(
        Bucket=bucket,
        Key=key.lstrip("/"),
        Body=data,
        ContentType=content_type,
        ContentDisposition=content_disposition,
    )
    return build_public_url(key)
