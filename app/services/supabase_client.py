"""Supabase client initialization."""
from supabase import create_client, create_async_client, Client
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY

_SYNC_SUPABASE_CLIENTS: dict[str, Client] = {}
_ASYNC_SUPABASE_CLIENTS: dict[str, Client] = {}


def get_supabase_client(
    use_service_role: bool = False,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> Client:
    """Get Supabase client.
    - use_service_role: bypass RLS (admin operations)
    - access_token: user JWT for RLS-authenticated requests
    - refresh_token: required with access_token for set_session
    """
    key = SUPABASE_SERVICE_ROLE_KEY if use_service_role else SUPABASE_ANON_KEY
    if access_token and not use_service_role:
        client = create_client(SUPABASE_URL, key)
        client.auth.set_session(access_token, refresh_token or "dummy")
        return client

    if key not in _SYNC_SUPABASE_CLIENTS:
        _SYNC_SUPABASE_CLIENTS[key] = create_client(SUPABASE_URL, key)
    return _SYNC_SUPABASE_CLIENTS[key]


async def get_async_supabase_client(
    use_service_role: bool = False,
    access_token: str | None = None,
    refresh_token: str | None = None,
):
    """Get async Supabase client.
    - use_service_role: bypass RLS (admin operations)
    - access_token: user JWT for RLS-authenticated requests
    - refresh_token: required with access_token for set_session
    """
    key = SUPABASE_SERVICE_ROLE_KEY if use_service_role else SUPABASE_ANON_KEY
    if access_token and not use_service_role:
        client = await create_async_client(SUPABASE_URL, key)
        await client.auth.set_session(access_token, refresh_token or "dummy")
        return client

    if key not in _ASYNC_SUPABASE_CLIENTS:
        _ASYNC_SUPABASE_CLIENTS[key] = await create_async_client(SUPABASE_URL, key)
    return _ASYNC_SUPABASE_CLIENTS[key]
