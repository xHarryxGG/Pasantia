"""FastAPI dependencies for authentication."""
from time import perf_counter
from fastapi import Request, HTTPException, status

from app.auth.supabase_auth import get_user_from_token
from app.services.supabase_client import get_async_supabase_client, get_supabase_client
from app.config import ROLE_ADMIN


async def get_access_token(request: Request) -> str | None:
    """Extract access token from cookie or Authorization header."""
    token = request.cookies.get("sb-access-token")
    if token:
        return token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


async def get_refresh_token(request: Request) -> str | None:
    """Extract refresh token from cookie."""
    return request.cookies.get("sb-refresh-token")


async def get_current_user(request: Request):
    """Get current authenticated user. Raises 401 if not authenticated."""
    auth_started_at = perf_counter()
    token = await get_access_token(request)
    refresh = await get_refresh_token(request)
    token_ms = (perf_counter() - auth_started_at) * 1000

    user_started_at = perf_counter()
    user = await get_user_from_token(token)
    user_ms = (perf_counter() - user_started_at) * 1000
    if not user:
        if request.headers.get("HX-Request"):
            raise HTTPException(status_code=401, detail="Sesión expirada. Recargue la página.")
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Not authenticated",
            headers={"Location": "/auth/login"},
        )
    # Fetch profile (role, department) - use service role
    profile_started_at = perf_counter()
    supabase = await get_async_supabase_client(use_service_role=True)
    profile_result = await supabase.table("profiles").select("*").eq("id", str(user.id)).execute()
    profile_data = profile_result.data[0] if profile_result.data else None

    # Si no tiene perfil (ej: usuario creado en Dashboard), crearlo
    if not profile_data:
        existing = await supabase.table("profiles").select("id").limit(1).execute()
        is_first_user = not (existing.data and len(existing.data) > 0)
        # Primer usuario del sistema = admin; resto = fundacion_nino
        default_role = ROLE_ADMIN if is_first_user else "fundacion_nino"
        full_name = getattr(user, "user_metadata", {}) or {}
        if isinstance(full_name, dict):
            full_name = full_name.get("full_name", "") or getattr(user, "email", "")
        await supabase.table("profiles").upsert({
            "id": str(user.id),
            "role": default_role,
            "full_name": full_name,
        }, on_conflict="id").execute()
        profile_data = {"id": str(user.id), "role": default_role, "full_name": full_name, "department_id": None}

    profile_ms = (perf_counter() - profile_started_at) * 1000
    request.state.auth_timing = {
        "auth_token": token_ms,
        "auth_user": user_ms,
        "auth_profile": profile_ms,
        "auth_total": token_ms + user_ms + profile_ms,
    }

    return {
        "user": user,
        "profile": profile_data,
        "access_token": token,
        "refresh_token": refresh or "",
    }


async def get_current_user_optional(request: Request):
    """Get current user if authenticated, else None."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


def require_role(allowed_roles: list[str]):
    """Dependency factory to require specific roles."""
    async def _require_role(request: Request):
        auth = await get_current_user(request)
        profile = auth.get("profile")
        role = profile.get("role", "unknown") if profile else "unknown"
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para acceder a este recurso.",
            )
        return auth
    return _require_role


def require_admin(request: Request):
    """Dependency for admin-only routes."""
    return require_role([ROLE_ADMIN])
