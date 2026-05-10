"""Service for departments."""
from datetime import datetime, timedelta

from app.services.supabase_client import get_async_supabase_client


_DEPARTMENTS_CACHE: list[dict] | None = None
_DEPARTMENTS_CACHE_EXPIRES_AT: datetime | None = None
_DEPARTMENTS_CACHE_TTL_SECONDS = 300


async def list_departments():
    """List all departments (no auth needed for this lookup)."""
    global _DEPARTMENTS_CACHE, _DEPARTMENTS_CACHE_EXPIRES_AT

    now = datetime.utcnow()
    if _DEPARTMENTS_CACHE is not None and _DEPARTMENTS_CACHE_EXPIRES_AT and now < _DEPARTMENTS_CACHE_EXPIRES_AT:
        return _DEPARTMENTS_CACHE

    supabase = await get_async_supabase_client(use_service_role=True)
    result = await supabase.table("departments").select("id, code, name").order("code").execute()
    _DEPARTMENTS_CACHE = result.data
    _DEPARTMENTS_CACHE_EXPIRES_AT = now + timedelta(seconds=_DEPARTMENTS_CACHE_TTL_SECONDS)
    return _DEPARTMENTS_CACHE
