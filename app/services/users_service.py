"""Service for user management (admin only)."""
from app.services.supabase_client import get_async_supabase_client
from app.config import ROLE_ADMIN


def _user_to_dict(u) -> dict:
    """Normalize user object to dict."""
    if isinstance(u, dict):
        return u
    return {
        "id": str(getattr(u, "id", u)),
        "email": getattr(u, "email", ""),
        "user_metadata": getattr(u, "user_metadata", {}),
    }


async def list_users_with_profiles():
    """List all auth users with their profiles."""
    supabase = await get_async_supabase_client(use_service_role=True)
    users_response = await supabase.auth.admin.list_users()
    users = []
    if isinstance(users_response, list):
        users = [_user_to_dict(u) for u in users_response]
    elif hasattr(users_response, "users"):
        users = [_user_to_dict(u) for u in users_response.users]
    elif hasattr(users_response, "parsed") and isinstance(users_response.parsed, dict):
        users = [_user_to_dict(u) for u in users_response.parsed.get("users", [])]
    elif hasattr(users_response, "model_dump"):
        users = [_user_to_dict(u) for u in users_response.model_dump().get("users", [])]
    # Get profiles
    profiles_result = await supabase.table("profiles").select("id, role, department_id, full_name").execute()
    profiles_by_id = {str(p["id"]): p for p in (profiles_result.data or [])}
    # Merge
    result = []
    for u in users:
        uid = u.get("id", "")
        profile = profiles_by_id.get(uid, {})
        meta = u.get("user_metadata") or {}
        result.append({
            "id": uid,
            "email": u.get("email", ""),
            "full_name": profile.get("full_name") or meta.get("full_name", ""),
            "role": profile.get("role", "fundacion_nino"),
            "department_id": profile.get("department_id"),
        })
    return result


async def create_user(email: str, password: str, full_name: str, role: str, department_id: str | None):
    """Create a new user via admin API and set profile."""
    supabase = await get_async_supabase_client(use_service_role=True)
    create_params = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"full_name": full_name},
    }
    response = await supabase.auth.admin.create_user(create_params)
    user = response.user if hasattr(response, "user") else response
    user_dict = _user_to_dict(user)
    user_id = user_dict.get("id", "")
    # Create profile (admin has no department)
    profile_data = {"id": user_id, "full_name": full_name, "role": role}
    if department_id and role != ROLE_ADMIN:
        profile_data["department_id"] = department_id
    await supabase.table("profiles").upsert(profile_data, on_conflict="id").execute()
    return user_dict


async def update_user_profile(user_id: str, full_name: str | None, role: str | None, department_id: str | None):
    """Update a user's profile."""
    supabase = await get_async_supabase_client(use_service_role=True)
    data = {}
    if full_name is not None:
        data["full_name"] = full_name
    if role is not None:
        data["role"] = role
    if department_id is not None:
        data["department_id"] = department_id
    if data:
        await supabase.table("profiles").update(data).eq("id", user_id).execute()


async def delete_user(user_id: str):
    """Delete a user (auth + profile cascades)."""
    supabase = await get_async_supabase_client(use_service_role=True)
    await supabase.auth.admin.delete_user(user_id)
