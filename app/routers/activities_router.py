"""Activities CRUD routes - used within plan detail."""
import logging
from datetime import date, timedelta
from time import perf_counter
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from calendar import monthrange

from app.auth.dependencies import require_role
from app.config import ROLE_ADMIN, DEPARTMENT_ROLES
from app.services.plans_service import get_plan
from app.services.activities_service import (
    list_activities_for_plan,
    create_activity,
    update_activity,
    delete_activity,
    upsert_activity_schedule,
    get_plan_weeks,
)
from app.services.supabase_client import get_supabase_client, get_async_supabase_client

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_weeks_and_day_numbers(year: int, month: int):
    """Get ISO week numbers and day numbers matrix for a given month."""
    start = date(year, month, 1)
    _, last_day = monthrange(year, month)
    last_day_date = date(year, month, last_day)
    start_monday = start - timedelta(days=start.weekday())
    weeks = []
    week_day_numbers = []

    week_start = start_monday
    while week_start <= last_day_date:
        weeks.append(week_start.isocalendar()[1])
        week_days = []
        for dow in range(7):
            day = week_start + timedelta(days=dow)
            week_days.append(day.day if day.month == month else "")
        week_day_numbers.append(week_days)
        week_start += timedelta(weeks=1)

    return weeks, week_day_numbers


def _record_stage(timings: list[tuple[str, float]], label: str, started_at: float) -> float:
    """Store elapsed milliseconds for a stage and return a fresh timer."""
    timings.append((label, (perf_counter() - started_at) * 1000))
    return perf_counter()


def _apply_timing_headers(request: Request, response: Response, timings: list[tuple[str, float]], label: str):
    """Attach timing information to the response and log it."""
    auth_timings = getattr(request.state, "auth_timing", {})
    combined = list(auth_timings.items()) + timings
    response.headers["X-Perf-Breakdown"] = ", ".join(
        f"{name}={value:.1f}ms" for name, value in combined
    )
    existing_server_timing = response.headers.get("Server-Timing")
    server_timing_parts = [f"{name};dur={value:.1f}" for name, value in combined]
    if existing_server_timing:
        server_timing_parts.insert(0, existing_server_timing)
    response.headers["Server-Timing"] = ", ".join(server_timing_parts)
    logger.info("%s timings: %s", label, response.headers["X-Perf-Breakdown"])


def _build_plan_context(
    plan_id: str,
    plan_year: int,
    plan_month: int,
    plan_goal: str | None,
    department_code: str | None,
    department_name: str | None,
):
    """Build the minimum plan payload required by the partial template."""
    return {
        "id": plan_id,
        "year": plan_year,
        "month": plan_month,
        "goal": plan_goal or "",
        "departments": {
            "code": department_code or "",
            "name": department_name or "",
        },
    }


@router.get("/plans/{plan_id}/activities")
async def list_activities(
    request: Request,
    plan_id: str,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    """Get activities for a plan (HTMX partial)."""
    from app.templating import templates
    timings = []
    stage_started_at = perf_counter()
    supabase = get_supabase_client(
        access_token=auth.get("access_token"),
        refresh_token=auth.get("refresh_token"),
    )
    stage_started_at = _record_stage(timings, "build_client", stage_started_at)
    plan = await get_plan(plan_id, auth.get("access_token"), auth.get("refresh_token"), supabase=supabase)
    stage_started_at = _record_stage(timings, "get_plan", stage_started_at)
    if not plan:
        from fastapi import HTTPException
        raise HTTPException(404, "Plan no encontrado")
    token, refresh = auth.get("access_token"), auth.get("refresh_token")
    activities = await list_activities_for_plan(plan_id, token, refresh, supabase=supabase)
    stage_started_at = _record_stage(timings, "list_activities", stage_started_at)

    weeks, week_day_numbers = _get_weeks_and_day_numbers(plan["year"], plan["month"])
    stage_started_at = _record_stage(timings, "build_calendar", stage_started_at)

    response = templates.TemplateResponse(
        "plans/_activities_table.html",
        {
            "request": request,
            "plan": plan,
            "activities": activities,
            "weeks": weeks,
            "week_day_numbers": week_day_numbers,
        },
    )
    _record_stage(timings, "render_partial", stage_started_at)
    _apply_timing_headers(request, response, timings, "activities.list")
    return response


@router.post("/plans/{plan_id}/activities")
async def create_activity_route(
    request: Request,
    plan_id: str,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
    description: str = Form(""),
    location: str = Form(""),
    logistics: str = Form(""),
    plan_month: int | None = Form(None),
    plan_year: int | None = Form(None),
    plan_goal: str | None = Form(None),
    department_code: str | None = Form(None),
    department_name: str | None = Form(None),
):
    """Create a new activity in a plan."""
    timings = []
    stage_started_at = perf_counter()
    supabase = await get_async_supabase_client(
        access_token=auth.get("access_token"),
        refresh_token=auth.get("refresh_token"),
    )
    stage_started_at = _record_stage(timings, "build_client", stage_started_at)
    await create_activity(
        plan_id=plan_id,
        description=description,
        location=location,
        logistics=logistics,
        access_token=auth.get("access_token"),
        refresh_token=auth.get("refresh_token"),
        supabase=supabase,
    )
    stage_started_at = _record_stage(timings, "create_activity", stage_started_at)
    if request.headers.get("HX-Request"):
        token, refresh = auth.get("access_token"), auth.get("refresh_token")
        activities = await list_activities_for_plan(plan_id, token, refresh, supabase=supabase)
        stage_started_at = _record_stage(timings, "list_activities", stage_started_at)

        if plan_year is None or plan_month is None:
            plan = await get_plan(plan_id, token, refresh, supabase=supabase)
            stage_started_at = _record_stage(timings, "get_plan", stage_started_at)
            if not plan:
                from fastapi import HTTPException
                raise HTTPException(404, "Plan no encontrado")
            plan_year = plan["year"]
            plan_month = plan["month"]
        else:
            plan = _build_plan_context(
                plan_id,
                plan_year,
                plan_month,
                plan_goal,
                department_code,
                department_name,
            )

        weeks, week_day_numbers = _get_weeks_and_day_numbers(plan_year, plan_month)
        stage_started_at = _record_stage(timings, "build_calendar", stage_started_at)

        from app.templating import templates
        response = templates.TemplateResponse(
            "plans/_activities_table.html",
            {
                "request": request,
                "plan": plan,
                "activities": activities,
                "weeks": weeks,
                "week_day_numbers": week_day_numbers,
            },
        )
        _record_stage(timings, "render_partial", stage_started_at)
        _apply_timing_headers(request, response, timings, "activities.create")
        return response
    return RedirectResponse(url=f"/plans/{plan_id}", status_code=302)


@router.patch("/plans/{plan_id}/activities/{activity_id}")
async def update_activity_route(
    request: Request,
    plan_id: str,
    activity_id: str,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
    description: str = Form(None),
    location: str = Form(None),
    logistics: str = Form(None),
):
    """Update an activity."""
    timings = []
    stage_started_at = perf_counter()
    supabase = await get_async_supabase_client(
        access_token=auth.get("access_token"),
        refresh_token=auth.get("refresh_token"),
    )
    stage_started_at = _record_stage(timings, "build_client", stage_started_at)
    await update_activity(
        activity_id=activity_id,
        description=description,
        location=location,
        logistics=logistics,
        access_token=auth.get("access_token"),
        refresh_token=auth.get("refresh_token"),
        supabase=supabase,
    )
    _record_stage(timings, "update_activity", stage_started_at)
    if request.headers.get("HX-Request"):
        response = Response(status_code=200)
        _apply_timing_headers(request, response, timings, "activities.update")
        return response
    return RedirectResponse(url=f"/plans/{plan_id}", status_code=302)


@router.delete("/plans/{plan_id}/activities/{activity_id}")
async def delete_activity_route(
    request: Request,
    plan_id: str,
    activity_id: str,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
    plan_month: int | None = Form(None),
    plan_year: int | None = Form(None),
    plan_goal: str | None = Form(None),
    department_code: str | None = Form(None),
    department_name: str | None = Form(None),
):
    """Delete an activity."""
    from app.templating import templates
    timings = []
    stage_started_at = perf_counter()
    token, refresh = auth.get("access_token"), auth.get("refresh_token")
    supabase = await get_async_supabase_client(access_token=token, refresh_token=refresh)
    stage_started_at = _record_stage(timings, "build_client", stage_started_at)
    await delete_activity(activity_id, token, refresh, supabase=supabase)
    stage_started_at = _record_stage(timings, "delete_activity", stage_started_at)
    if request.headers.get("HX-Request"):
        activities = await list_activities_for_plan(plan_id, token, refresh, supabase=supabase)
        stage_started_at = _record_stage(timings, "list_activities", stage_started_at)

        if plan_year is None or plan_month is None:
            plan = await get_plan(plan_id, token, refresh, supabase=supabase)
            stage_started_at = _record_stage(timings, "get_plan", stage_started_at)
            if not plan:
                from fastapi import HTTPException
                raise HTTPException(404, "Plan no encontrado")
            plan_year = plan["year"]
            plan_month = plan["month"]
        else:
            plan = _build_plan_context(
                plan_id,
                plan_year,
                plan_month,
                plan_goal,
                department_code,
                department_name,
            )

        weeks, week_day_numbers = _get_weeks_and_day_numbers(plan_year, plan_month)
        stage_started_at = _record_stage(timings, "build_calendar", stage_started_at)

        response = templates.TemplateResponse(
            "plans/_activities_table.html",
            {
                "request": request,
                "plan": plan,
                "activities": activities,
                "weeks": weeks,
                "week_day_numbers": week_day_numbers,
            },
        )
        _record_stage(timings, "render_partial", stage_started_at)
        _apply_timing_headers(request, response, timings, "activities.delete")
        return response
    return RedirectResponse(url=f"/plans/{plan_id}", status_code=302)


def _parse_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "on", "yes")


@router.post("/plans/{plan_id}/activities/{activity_id}/schedule/{week_number}")
async def update_schedule_route(
    request: Request,
    plan_id: str,
    activity_id: str,
    week_number: int,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
    monday: str = Form("false"),
    tuesday: str = Form("false"),
    wednesday: str = Form("false"),
    thursday: str = Form("false"),
    friday: str = Form("false"),
    saturday: str = Form("false"),
    sunday: str = Form("false"),
):
    """Update activity schedule for a week (HTMX)."""
    timings = []
    stage_started_at = perf_counter()
    supabase = await get_async_supabase_client(
        access_token=auth.get("access_token"),
        refresh_token=auth.get("refresh_token"),
    )
    stage_started_at = _record_stage(timings, "build_client", stage_started_at)
    await upsert_activity_schedule(
        activity_id=activity_id,
        week_number=week_number,
        monday=_parse_bool(monday),
        tuesday=_parse_bool(tuesday),
        wednesday=_parse_bool(wednesday),
        thursday=_parse_bool(thursday),
        friday=_parse_bool(friday),
        saturday=_parse_bool(saturday),
        sunday=_parse_bool(sunday),
        access_token=auth.get("access_token"),
        refresh_token=auth.get("refresh_token"),
        supabase=supabase,
    )
    response = Response(status_code=200)
    _record_stage(timings, "upsert_schedule", stage_started_at)
    _apply_timing_headers(request, response, timings, "activities.schedule")
    return response
