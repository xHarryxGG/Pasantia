"""Service for activities and activity schedules CRUD."""
from app.services.supabase_client import get_async_supabase_client


async def list_activities_for_plan(
    plan_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
    supabase=None,
):
    """List all activities for a plan with their schedules."""
    supabase = supabase or await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    result = await supabase.table("activities").select(
        "*, activity_schedules(*)"
    ).eq("plan_id", plan_id).order("created_at").execute()
    return result.data


async def get_activity(
    activity_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
    supabase=None,
) -> dict | None:
    """Get a single activity with schedules."""
    supabase = supabase or await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    result = await supabase.table("activities").select(
        "*, activity_schedules(*)"
    ).eq("id", activity_id).execute()
    return result.data[0] if result.data else None


async def create_activity(
    plan_id: str,
    description: str,
    location: str,
    logistics: str,
    access_token: str | None,
    refresh_token: str | None = None,
    supabase=None,
):
    """Create a new activity."""
    supabase = supabase or await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    data = {
        "plan_id": plan_id,
        "description": description or "",
        "location": location or "",
        "logistics": logistics or "",
    }
    result = await supabase.table("activities").insert(data).execute()
    return result.data[0] if result.data else None


async def update_activity(
    activity_id: str,
    description: str | None = None,
    location: str | None = None,
    logistics: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    supabase=None,
):
    """Update an activity."""
    supabase = supabase or await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    data = {}
    if description is not None:
        data["description"] = description
    if location is not None:
        data["location"] = location
    if logistics is not None:
        data["logistics"] = logistics
    if not data:
        return await get_activity(activity_id, access_token, refresh_token, supabase=supabase)
    result = await supabase.table("activities").update(data).eq("id", activity_id).execute()
    return result.data[0] if result.data else None


async def delete_activity(
    activity_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
    supabase=None,
):
    """Delete an activity (cascades to schedules)."""
    supabase = supabase or await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    await supabase.table("activities").delete().eq("id", activity_id).execute()


async def upsert_activity_schedule(
    activity_id: str,
    week_number: int,
    monday: bool = False,
    tuesday: bool = False,
    wednesday: bool = False,
    thursday: bool = False,
    friday: bool = False,
    saturday: bool = False,
    sunday: bool = False,
    access_token: str | None = None,
    refresh_token: str | None = None,
    supabase=None,
):
    """Create or update an activity schedule for a week."""
    supabase = supabase or await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    data = {
        "activity_id": activity_id,
        "week_number": week_number,
        "monday": monday,
        "tuesday": tuesday,
        "wednesday": wednesday,
        "thursday": thursday,
        "friday": friday,
        "saturday": saturday,
        "sunday": sunday,
    }
    result = await supabase.table("activity_schedules").upsert(
        data,
        on_conflict="activity_id,week_number",
    ).execute()
    return result.data[0] if result.data else None


async def get_plan_weeks(
    plan_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
    supabase=None,
) -> list[int]:
    """Get distinct week numbers used in a plan's activities."""
    activities = await list_activities_for_plan(plan_id, access_token, refresh_token, supabase=supabase)
    weeks = set()
    for a in activities:
        for s in (a.get("activity_schedules") or []):
            weeks.add(s["week_number"])
    return sorted(weeks) if weeks else []
