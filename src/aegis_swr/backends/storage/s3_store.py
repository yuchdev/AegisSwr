"""S3 / MinIO storage backend.

Implements both ``RelationalStore`` (reports as JSON objects) and
``ObjectStore`` (raw binary artifacts) against an S3-compatible API.

Key layout::

    reports/{incident_id}.json      RCAReport JSON
    hash-index/{dump_hash}          content = incident_id (plain text)
    objects/{incident_id}/{name}    raw binary artifacts
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, Optional
from uuid import UUID

from botocore.exceptions import ClientError
from loguru import logger

from aegis_swr.backends.base import ObjectStore, RelationalStore
from aegis_swr.config.settings import StorageSettings
from aegis_swr.core.exceptions import IncidentNotFoundError, RelationalStoreError
from aegis_swr.core.schemas import RCAReport

_NO_SUCH_KEY = "NoSuchKey"


def _parse_bucket(url: str) -> str:
    """Extract bucket name from ``s3://bucket-name`` URL"""
    stripped = url.removeprefix("s3://").removeprefix("s3a://").split("/")[0]
    if not stripped:
        raise ValueError(f"Cannot parse bucket from URL: {url!r}")
    return stripped


class S3Store(RelationalStore, ObjectStore):
    """S3/MinIO backend; wraps sync boto3 calls in ``asyncio.to_thread``"""

    def __init__(self, settings: StorageSettings):
        """Build the boto3 S3 client and resolve the target bucket from settings.

        :param settings: storage configuration carrying the object-store URL,
            region, and optional S3 endpoint override.
        """
        import boto3

        self._bucket = _parse_bucket(settings.object_store_url)
        kwargs: dict[str, Any] = {"region_name": settings.object_store_region}
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        self._client: Any = boto3.client("s3", **kwargs)
        logger.debug(f"S3Store: bucket={self._bucket}")

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _put_text(self, key: str, text: str):
        """Store *text* as a UTF-8 JSON object at *key* in the bucket."""
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="application/json",
        )

    def _get_text(self, key: str) -> Optional[str]:
        """Read the object at *key* as UTF-8 text, or ``None`` if it is absent."""
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            raw: str = resp["Body"].read().decode("utf-8")
            return raw
        except ClientError as exc:
            if self._is_no_such_key(exc):
                return None
            raise

    @staticmethod
    def _is_no_such_key(exc: BaseException) -> bool:
        """Return True when *exc* is a boto ``NoSuchKey`` (missing object) error."""
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code: str = response.get("Error", {}).get("Code", "")
            return code == _NO_SUCH_KEY
        return False

    def _put_bytes(self, key: str, data: bytes):
        """Store raw *data* bytes at *key* in the bucket."""
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def _get_bytes(self, key: str) -> bytes:
        """Read raw bytes at *key*, raising ``IncidentNotFoundError`` if absent."""
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            data: bytes = resp["Body"].read()
            return data
        except ClientError as exc:
            if self._is_no_such_key(exc):
                raise IncidentNotFoundError(f"Object not found: {key}") from exc
            raise

    # ------------------------------------------------------------------
    # RelationalStore
    # ------------------------------------------------------------------

    async def save_report(self, report: RCAReport):
        """Persist *report* and its hash index off the event loop thread."""
        await asyncio.to_thread(self._sync_save_report, report)

    def _sync_save_report(self, report: RCAReport):
        """Write the report JSON and its dump-hash index synchronously."""
        try:
            self._put_text(f"reports/{report.incident_id}.json", report.model_dump_json())
            if report.dump_hash:
                self._put_text(f"hash-index/{report.dump_hash}", str(report.incident_id))
        except ClientError as exc:
            raise RelationalStoreError(f"S3 save_report failed: {exc}") from exc
        logger.debug(f"S3Store: saved report {report.incident_id}")

    async def get_report(self, incident_id: UUID) -> Optional[RCAReport]:
        """Load the report for *incident_id* off the event loop thread."""
        return await asyncio.to_thread(self._sync_get_report, incident_id)

    def _sync_get_report(self, incident_id: UUID) -> Optional[RCAReport]:
        """Read and validate the report JSON for *incident_id*, or ``None``."""
        text = self._get_text(f"reports/{incident_id}.json")
        return RCAReport.model_validate_json(text) if text else None

    async def find_by_hash(self, dump_hash: str) -> Optional[RCAReport]:
        """Look up a cached report by *dump_hash* off the event loop thread."""
        return await asyncio.to_thread(self._sync_find_by_hash, dump_hash)

    def _sync_find_by_hash(self, dump_hash: str) -> Optional[RCAReport]:
        """Resolve the hash index to an incident id, then load that report."""
        incident_id_text = self._get_text(f"hash-index/{dump_hash}")
        if not incident_id_text:
            return None
        return self._sync_get_report(UUID(incident_id_text.strip()))

    async def update_hitl_response(
        self,
        incident_id: UUID,
        response: dict[str, object],
    ):
        """Merge a HITL *response* into the stored report off the event loop thread."""
        await asyncio.to_thread(self._sync_update_hitl, incident_id, response)

    def _sync_update_hitl(
        self,
        incident_id: UUID,
        response: dict[str, object],
    ):
        """Read the report JSON, set its ``hitl_request``, and write it back."""
        key = f"reports/{incident_id}.json"
        text = self._get_text(key)
        if text is None:
            raise IncidentNotFoundError(f"Report not found: {incident_id}")
        data = json.loads(text)
        data["hitl_request"] = response
        self._put_text(key, json.dumps(data))

    # ------------------------------------------------------------------
    # ObjectStore
    # ------------------------------------------------------------------

    async def load_recent(self, limit: int = 100) -> list[RCAReport]:
        """Load the most recent reports (up to *limit*) off the event loop thread."""
        return await asyncio.to_thread(self._sync_load_recent, limit)

    def _sync_load_recent(self, limit: int) -> list[RCAReport]:
        """Page the report prefix, sort newest-first, and validate up to *limit*."""
        try:
            keys: list[str] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix="reports/"):
                for obj in page.get("Contents", []):
                    key: str = obj["Key"]
                    if key.endswith(".json"):
                        keys.append(key)
            keys.sort(reverse=True)
            if limit > 0:
                keys = keys[:limit]
            reports: list[RCAReport] = []
            for key in keys:
                text = self._get_text(key)
                if text:
                    with contextlib.suppress(Exception):
                        reports.append(RCAReport.model_validate_json(text))
        except ClientError as exc:
            raise RelationalStoreError(f"S3 load_recent failed: {exc}") from exc
        return reports

    async def upload_raw(
        self,
        incident_id: UUID,
        filename: str,
        data: bytes,
    ) -> str:
        """Upload raw artifact *data* under the incident, returning its object key.

        :param incident_id: the incident the artifact belongs to.
        :param filename: the artifact file name within the incident namespace.
        :param data: the raw bytes to store.
        :return: the ``{incident_id}/{filename}`` object key for later retrieval.
        """
        key = f"objects/{incident_id}/{filename}"
        await asyncio.to_thread(self._put_bytes, key, data)
        return f"{incident_id}/{filename}"

    async def get_raw(self, object_key: str) -> bytes:
        """Fetch the raw artifact bytes for *object_key* off the event loop thread."""
        return await asyncio.to_thread(self._get_bytes, f"objects/{object_key}")
