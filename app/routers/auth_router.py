"""Authentication routes."""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse

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
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        context={"request": request},
    )


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
        # Traducir mensajes de Supabase al español
        raw = str(e).lower()
        if "invalid login credentials" in raw or "invalid_credentials" in raw:
            error_msg = "Correo electrónico o contraseña incorrectos."
        elif "email not confirmed" in raw:
            error_msg = "La cuenta no ha sido confirmada. Revise su correo electrónico."
        elif "user not found" in raw:
            error_msg = "No existe una cuenta con ese correo electrónico."
        elif "too many requests" in raw or "rate limit" in raw:
            error_msg = "Demasiados intentos fallidos. Espere unos minutos e intente de nuevo."
        elif "network" in raw or "connection" in raw:
            error_msg = "Error de conexión. Verifique su internet e intente de nuevo."
        else:
            error_msg = "No se pudo iniciar sesión. Verifique sus credenciales e intente de nuevo."
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            context={"request": request, "error": error_msg},
        )
    from app.templating import templates
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        context={"request": request, "error": "Error al iniciar sesión"},
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
