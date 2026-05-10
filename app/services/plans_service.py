"""Service for action plans CRUD."""
from uuid import UUID
from app.services.supabase_client import get_async_supabase_client


async def list_plans(
    access_token: str | None,
    department_id: str | None = None,
    refresh_token: str | None = None,
    supabase=None,
):
    """List action plans. RLS filters by department for non-admins."""
    supabase = supabase or await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    query = supabase.table("action_plans").select(
        "id, department_id, month, year, goal, departments(code, name)"
    ).order("year", desc=True).order("month", desc=True)
    if department_id:
        query = query.eq("department_id", department_id)
    result = await query.execute()
    return result.data


async def get_plan(
    plan_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
    supabase=None,
) -> dict | None:
    """Get a single plan by ID."""
    supabase = supabase or await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    result = await supabase.table("action_plans").select(
        "*, departments(code, name)"
    ).eq("id", plan_id).execute()
    return result.data[0] if result.data else None


async def create_plan(
    department_id: str, month: int, year: int, goal: str,
    created_by: str, access_token: str | None, refresh_token: str | None = None
):
    """Create a new action plan."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    data = {
        "department_id": department_id,
        "month": month,
        "year": year,
        "goal": goal or "",
        "created_by": created_by,
    }
    result = await supabase.table("action_plans").insert(data).execute()
    return result.data[0] if result.data else None


async def update_plan(plan_id: str, month: int | None, year: int | None, goal: str | None, access_token: str | None, refresh_token: str | None = None):
    """Update an action plan."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    data = {}
    if month is not None:
        data["month"] = month
    if year is not None:
        data["year"] = year
    if goal is not None:
        data["goal"] = goal
    if not data:
        return await get_plan(plan_id, access_token, refresh_token)
    result = await supabase.table("action_plans").update(data).eq("id", plan_id).execute()
    return result.data[0] if result.data else None


async def delete_plan(plan_id: str, access_token: str | None, refresh_token: str | None = None):
    """Delete an action plan."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    await supabase.table("action_plans").delete().eq("id", plan_id).execute()
