from __future__ import annotations

from urllib.parse import quote

import httpx

from app.core.config import settings


class StorageUploadError(RuntimeError):
    pass


def _object_url(path: str) -> str:
    bucket = quote(settings.supabase_storage_bucket.strip(), safe="")
    object_path = quote(path.replace("\\", "/").strip("/"), safe="/")
    return f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"


def _headers(content_type: str) -> dict[str, str]:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }


def _public_url(path: str) -> str:
    bucket = quote(settings.supabase_storage_bucket.strip(), safe="")
    object_path = quote(path.replace("\\", "/").strip("/"), safe="/")
    return f"{settings.supabase_url.rstrip('/')}/storage/v1/object/public/{bucket}/{object_path}"


def upload_bytes(path: str, content: bytes, content_type: str) -> str | None:
    """Upload to Supabase Storage when configured; return None for local fallback."""
    if not (settings.supabase_url and settings.supabase_service_role_key):
        return None
    try:
        response = httpx.post(
            _object_url(path),
            content=content,
            headers=_headers(content_type),
            timeout=30,
        )
        if response.status_code == 404:
            bucket_url = f"{settings.supabase_url.rstrip('/')}/storage/v1/bucket"
            bucket_response = httpx.post(
                bucket_url,
                json={
                    "id": settings.supabase_storage_bucket,
                    "name": settings.supabase_storage_bucket,
                    "public": True,
                },
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                },
                timeout=15,
            )
            if bucket_response.status_code not in {200, 201, 409}:
                raise StorageUploadError("Supabase Storage bucket creation failed")
            response = httpx.post(
                _object_url(path),
                content=content,
                headers=_headers(content_type),
                timeout=30,
            )
        if response.status_code not in {200, 201}:
            raise StorageUploadError(f"Supabase Storage upload failed: HTTP {response.status_code}")
    except (httpx.HTTPError, StorageUploadError) as exc:
        if isinstance(exc, StorageUploadError):
            raise
        raise StorageUploadError("Supabase Storage is unreachable") from exc
    return _public_url(path)
