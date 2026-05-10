"""Admin routes for user management."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import require_role
from app.config import ROLE_ADMIN, ALL_ROLES
from app.services.users_service import list_users_with_profiles, create_user, update_user_profile, delete_user
from app.services.departments_service import list_departments

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
async def list_users_view(request: Request, auth=Depends(require_role([ROLE_ADMIN]))):
    """List all users (admin only)."""
    from app.templating import templates
    users = await list_users_with_profiles()
    departments = await list_departments()
    return templates.TemplateResponse(request, "admin/users.html", context={"request": request, "user": auth, "users": users, "departments": departments, "roles": ALL_ROLES})


@router.post("/users")
async def create_user_submit(
    request: Request,
    auth=Depends(require_role([ROLE_ADMIN])),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    role: str = Form(...),
    department_id: str = Form(""),
):
    """Create a new user."""
    try:
        await create_user(
            email=email,
            password=password,
            full_name=full_name,
            role=role,
            department_id=department_id if department_id else None,
        )
    except Exception as e:
        from app.templating import templates
        users = await list_users_with_profiles()
        departments = await list_departments()
        return templates.TemplateResponse(request, "admin/users.html", context={
                "request": request,
                "user": auth,
                "users": users,
                "departments": departments,
                "roles": ALL_ROLES,
                "error": str(e),
            })
    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}")
async def update_user_submit(
    request: Request,
    user_id: str,
    auth=Depends(require_role([ROLE_ADMIN])),
    full_name: str = Form(""),
    role: str = Form(""),
    department_id: str = Form(""),
):
    """Update a user's profile."""
    await update_user_profile(
        user_id=user_id,
        full_name=full_name or None,
        role=role or None,
        department_id=department_id if department_id else None,
    )
    if request.headers.get("HX-Request"):
        from app.templating import templates
        users = await list_users_with_profiles()
        departments = await list_departments()
        return templates.TemplateResponse(request, "admin/_users_table.html", context={"request": request, "users": users, "departments": departments, "roles": ALL_ROLES})
    return RedirectResponse(url="/admin/users", status_code=302)


@router.delete("/users/{user_id}")
async def delete_user_route(
    request: Request,
    user_id: str,
    auth=Depends(require_role([ROLE_ADMIN])),
):
    """Delete a user."""
    await delete_user(user_id)
    if request.headers.get("HX-Request"):
        from app.templating import templates
        users = await list_users_with_profiles()
        departments = await list_departments()
        return templates.TemplateResponse(request, "admin/_users_table.html", context={"request": request, "users": users, "departments": departments, "roles": ALL_ROLES})
    return RedirectResponse(url="/admin/users", status_code=302)
