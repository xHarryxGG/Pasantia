"""Service for statistics and analytics aggregation."""
from app.services.supabase_client import get_async_supabase_client


async def get_stats_data(
    access_token: str | None = None,
    refresh_token: str | None = None,
    department_id: str | None = None,
    year: int | None = None,
    use_service_role: bool = False,
) -> dict:
    """Aggregate statistics for plans, activities, and schedules.

    Args:
        access_token: User JWT (for RLS-filtered queries).
        refresh_token: Refresh token for session.
        department_id: Optional department filter. None = all (admin).
        year: Optional year filter. None = all years.
        use_service_role: If True, bypass RLS (admin viewing all departments).

    Returns:
        dict with keys: plans, activities, schedules_summary,
        plans_by_month, activities_by_department, year_over_year.
    """
    if use_service_role:
        supabase = await get_async_supabase_client(use_service_role=True)
    else:
        supabase = await get_async_supabase_client(
            access_token=access_token, refresh_token=refresh_token
        )

    # ── Fetch plans ──────────────────────────────────────────────────
    plans_query = supabase.table("action_plans").select(
        "id, department_id, month, year, goal, departments(code, name)"
    )
    if department_id:
        plans_query = plans_query.eq("department_id", department_id)
    if year:
        plans_query = plans_query.eq("year", year)
    plans_result = await plans_query.order("year", desc=True).order("month", desc=True).execute()
    plans = plans_result.data or []

    # ── Fetch activities for those plans ─────────────────────────────
    plan_ids = [p["id"] for p in plans]
    activities: list[dict] = []
    if plan_ids:
        # Supabase IN filter with list
        activities_query = supabase.table("activities").select(
            "id, plan_id, description, activity_schedules(week_number, monday, tuesday, wednesday, thursday, friday, saturday, sunday)"
        ).in_("plan_id", plan_ids)
        activities_result = await activities_query.execute()
        activities = activities_result.data or []

    # ── Also fetch plans for ALL years (for year-over-year) ──────────
    yoy_plans: list[dict] = []
    yoy_activities: list[dict] = []
    if year:
        yoy_query = supabase.table("action_plans").select(
            "id, department_id, month, year, departments(code, name)"
        )
        if department_id:
            yoy_query = yoy_query.eq("department_id", department_id)
        yoy_result = await yoy_query.order("year").order("month").execute()
        yoy_plans = yoy_result.data or []

        yoy_plan_ids = [p["id"] for p in yoy_plans]
        if yoy_plan_ids:
            yoy_act_query = supabase.table("activities").select(
                "id, plan_id"
            ).in_("plan_id", yoy_plan_ids)
            yoy_act_result = await yoy_act_query.execute()
            yoy_activities = yoy_act_result.data or []
    else:
        yoy_plans = plans
        yoy_activities = [{"id": a["id"], "plan_id": a["plan_id"]} for a in activities]

    # ── Build aggregations ───────────────────────────────────────────
    # Map plan_id → plan data
    plan_map = {p["id"]: p for p in plans}

    # Activities per plan
    activities_per_plan: dict[str, int] = {}
    for act in activities:
        pid = act["plan_id"]
        activities_per_plan[pid] = activities_per_plan.get(pid, 0) + 1

    # Plans by month (1-12)
    plans_by_month = {m: 0 for m in range(1, 13)}
    for p in plans:
        m = p.get("month")
        if m and 1 <= m <= 12:
            plans_by_month[m] += 1

    # Activities by month
    activities_by_month = {m: 0 for m in range(1, 13)}
    for act in activities:
        plan = plan_map.get(act["plan_id"])
        if plan:
            m = plan.get("month")
            if m and 1 <= m <= 12:
                activities_by_month[m] += 1

    # Schedule day distribution
    day_keys = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day_counts = {d: 0 for d in day_keys}
    for act in activities:
        for sched in (act.get("activity_schedules") or []):
            for day in day_keys:
                if sched.get(day):
                    day_counts[day] += 1

    # Activities by department (for admin views)
    dept_plan_count: dict[str, int] = {}
    dept_act_count: dict[str, int] = {}
    dept_names: dict[str, str] = {}
    for p in plans:
        dept_id = p.get("department_id", "")
        dept_info = p.get("departments") or {}
        dept_names[dept_id] = dept_info.get("name", dept_info.get("code", "?"))
        dept_plan_count[dept_id] = dept_plan_count.get(dept_id, 0) + 1

    for act in activities:
        plan = plan_map.get(act["plan_id"])
        if plan:
            dept_id = plan.get("department_id", "")
            dept_act_count[dept_id] = dept_act_count.get(dept_id, 0) + 1

    departments_stats = []
    for did in dept_names:
        departments_stats.append({
            "department_id": did,
            "name": dept_names[did],
            "plans_count": dept_plan_count.get(did, 0),
            "activities_count": dept_act_count.get(did, 0),
        })

    # ── Year over year ───────────────────────────────────────────────
    yoy_plan_map = {p["id"]: p for p in yoy_plans}
    # Group by year: {year: {month: activity_count}}
    yoy_data: dict[int, dict[int, int]] = {}
    # Also count plans per year
    yoy_plans_per_year: dict[int, int] = {}
    for p in yoy_plans:
        y = p.get("year")
        if y:
            yoy_plans_per_year[y] = yoy_plans_per_year.get(y, 0) + 1
            if y not in yoy_data:
                yoy_data[y] = {m: 0 for m in range(1, 13)}

    for act in yoy_activities:
        plan = yoy_plan_map.get(act["plan_id"])
        if plan:
            y = plan.get("year")
            m = plan.get("month")
            if y and m and y in yoy_data:
                yoy_data[y][m] = yoy_data[y].get(m, 0) + 1

    year_over_year = []
    for y in sorted(yoy_data.keys()):
        year_over_year.append({
            "year": y,
            "total_plans": yoy_plans_per_year.get(y, 0),
            "months": [yoy_data[y].get(m, 0) for m in range(1, 13)],
        })

    # ── KPIs ─────────────────────────────────────────────────────────
    total_plans = len(plans)
    total_activities = len(activities)
    avg_activities = round(total_activities / total_plans, 1) if total_plans else 0

    # Plan labels for activities_per_plan chart
    plan_labels = []
    plan_activity_counts = []
    for p in plans:
        dept = p.get("departments") or {}
        month_names = [
            "Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"
        ]
        month_label = month_names[p["month"] - 1] if p.get("month") else "?"
        label = f"{dept.get('code', '?')} {month_label} {p.get('year', '')}"
        plan_labels.append(label)
        plan_activity_counts.append(activities_per_plan.get(p["id"], 0))

    return {
        "kpi": {
            "total_plans": total_plans,
            "total_activities": total_activities,
            "avg_activities_per_plan": avg_activities,
        },
        "plans_by_month": [plans_by_month.get(m, 0) for m in range(1, 13)],
        "activities_by_month": [activities_by_month.get(m, 0) for m in range(1, 13)],
        "plan_labels": plan_labels,
        "plan_activity_counts": plan_activity_counts,
        "day_distribution": [day_counts[d] for d in day_keys],
        "departments_stats": departments_stats,
        "year_over_year": year_over_year,
    }
