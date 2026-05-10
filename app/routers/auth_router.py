"""Authentication routes."""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.templating import _TemplateResponse

from app.auth.supabase_auth import sign_in, sign_out
from app.auth.dependencies import get_current_user_optional, get_access_token

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render login page."""
    from app.templating import templates
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/formats", status_code=302)
    return templates.TemplateResponse(request, "auth/login.html", context={})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    """Handle login form submission."""
    try:
        response = sign_in(email, password)
        if response.user and response.session:
            redirect = RedirectResponse(url="/formats", status_code=302)
            redirect.set_cookie(
                key="sb-access-token",
                value=response.session.access_token,
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,  # 7 days
            )
            redirect.set_cookie(
                key="sb-refresh-token",
                value=response.session.refresh_token,
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 30,  # 30 days
            )
            return redirect
    except Exception as e:
        from app.templating import templates
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": str(e)},
        )
    from app.templating import templates
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "error": "Error al iniciar sesión"},
    )


@router.get("/logout")
async def logout(request: Request):
    """Handle logout."""
    token = await get_access_token(request)
    if token:
        try:
            sign_out(token)
        except Exception:
            pass
    redirect = RedirectResponse(url="/auth/login", status_code=302)
    redirect.delete_cookie("sb-access-token")
    redirect.delete_cookie("sb-refresh-token")
    return redirect
