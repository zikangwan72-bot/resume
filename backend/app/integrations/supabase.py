from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import monotonic

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class SupabaseStatus:
    configured: bool
    url: str | None
    auth_mode: str
    storage_mode: str
    database: bool
    auth: bool
    storage: bool
    message: str


_CACHE_TTL_SECONDS = 60
_cached_status: tuple[float, tuple[str | None, str | None], SupabaseStatus] | None = None


def get_supabase_status() -> SupabaseStatus:
    global _cached_status
    cache_key = (settings.supabase_url or None, settings.supabase_service_role_key or None)
    if _cached_status is not None:
        checked_at, cached_key, status = _cached_status
        if cached_key == cache_key and monotonic() - checked_at < _CACHE_TTL_SECONDS:
            return status

    if not (settings.supabase_url and settings.supabase_service_role_key):
        status = SupabaseStatus(
            configured=False,
            url=settings.supabase_url or None,
            auth_mode="local_email_password",
            storage_mode="local_or_disabled",
            database=False,
            auth=False,
            storage=False,
            message="Supabase probes skipped: URL or service role key is missing.",
        )
        _cached_status = (monotonic(), cache_key, status)
        return status
    base_url = settings.supabase_url.rstrip("/")
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    probes = {
        "database": f"{base_url}/rest/v1/users?select=id&limit=1",
        "auth": f"{base_url}/auth/v1/admin/users?per_page=1&page=1",
        "storage": f"{base_url}/storage/v1/bucket",
    }
    def probe(item: tuple[str, str]) -> tuple[str, bool]:
        name, url = item
        try:
            response = httpx.get(url, headers=headers, timeout=2)
            return name, 200 <= response.status_code < 300
        except httpx.HTTPError:
            return name, False

    with ThreadPoolExecutor(max_workers=len(probes)) as executor:
        results = dict(executor.map(probe, probes.items()))

    configured = all(results.values())
    status = SupabaseStatus(
        configured=configured,
        url=settings.supabase_url,
        # The application currently verifies its local user table. Supabase Auth
        # is probed for service health, but must not be reported as the login path.
        auth_mode="local_email_password",
        storage_mode="supabase" if results["storage"] else "local_or_disabled",
        database=results["database"],
        auth=results["auth"],
        storage=results["storage"],
        message="All Supabase probes passed." if configured else "One or more Supabase probes failed.",
    )
    _cached_status = (monotonic(), cache_key, status)
    return status
