"""Statistics routes for plans and activities analytics."""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.auth.dependencies import require_role
from app.config import ROLE_ADMIN, DEPARTMENT_ROLES
from app.services.departments_service import list_departments
from app.services.stats_service import get_stats_data

router = APIRouter()
logger = logging.getLogger(__name__)


def _is_admin(auth) -> bool:
    profile = auth.get("profile") if auth else None
    return bool(profile and profile.get("role") == ROLE_ADMIN)


def _user_department_id(auth) -> str | None:
    profile = auth.get("profile") if auth else None
    if not profile:
        return None
    dept = profile.get("department_id")
    return str(dept) if dept else None


@router.get("", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    """Render the statistics dashboard page."""
    from app.templating import templates

    is_admin = _is_admin(auth)
    departments = await list_departments() if is_admin else []
    user_dept_id = _user_department_id(auth)

    current_year = datetime.now().year
    # Build a range of years for the selector (current year ± 5)
    years = list(range(current_year - 5, current_year + 2))

    return templates.TemplateResponse(request, "stats/stats.html", context={
            "request": request,
            "user": auth,
            "is_admin": is_admin,
            "departments": departments,
            "user_department_id": user_dept_id,
            "current_year": current_year,
            "years": years,
        })


@router.get("/api/data", response_class=JSONResponse)
async def stats_api_data(
    request: Request,
    year: int | None = Query(default=None),
    department_id: str | None = Query(default=None),
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    """JSON endpoint returning aggregated statistics data for Chart.js."""
    is_admin = _is_admin(auth)
    user_dept_id = _user_department_id(auth)

    # Non-admins can only see their own department
    if not is_admin:
        department_id = user_dept_id

    # Admin viewing all departments uses service_role to bypass RLS
    use_service_role = is_admin
    effective_dept = department_id if department_id else None

    try:
        data = await get_stats_data(
            access_token=auth.get("access_token"),
            refresh_token=auth.get("refresh_token"),
            department_id=effective_dept,
            year=year,
            use_service_role=use_service_role,
        )
        return JSONResponse(content=data)
    except Exception as err:
        logger.exception("Error fetching stats data")
        return JSONResponse(
            content={"error": f"Error al obtener estadísticas: {err}"},
            status_code=500,
        )
