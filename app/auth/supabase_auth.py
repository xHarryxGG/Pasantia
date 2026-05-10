"""Supabase Auth integration."""
from app.services.supabase_client import get_async_supabase_client, get_supabase_client


def sign_in(email: str, password: str):
    """Sign in with email and password."""
    supabase = get_supabase_client()
    return supabase.auth.sign_in_with_password({"email": email, "password": password})


def sign_out(access_token: str):
    """Sign out current session."""
    supabase = get_supabase_client()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass


async def get_user_from_token(access_token: str | None):
    """Get user object from access token."""
    if not access_token:
        return None
    supabase = await get_async_supabase_client()
    try:
        result = await supabase.auth.get_user(access_token)
        return result.user if result else None
    except Exception:
        return None
