"""FastAPI application for SIPF."""
from time import perf_counter
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.routers import auth_router, plans_router, admin_router, activities_router, formats_router, stats_router
from app.auth.dependencies import require_role

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="SIPF - Plan de Acción", version="1.0.0")

app.mount("/static", StaticFiles(directory=BASE_DIR.parent / "static"), name="static")

app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(plans_router.router, prefix="/plans", tags=["plans"])
app.include_router(formats_router.router, prefix="/formats", tags=["formats"])
app.include_router(activities_router.router, tags=["activities"])
app.include_router(admin_router.router, prefix="/admin", tags=["admin"])
app.include_router(stats_router.router, prefix="/stats", tags=["stats"])


@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    """Expose end-to-end request timing for browser devtools."""
    started_at = perf_counter()
    response = await call_next(request)
    total_ms = (perf_counter() - started_at) * 1000
    existing_server_timing = response.headers.get("Server-Timing")
    total_metric = f'total;dur={total_ms:.1f}'
    response.headers["X-Process-Time"] = f"{total_ms:.1f}ms"
    response.headers["Server-Timing"] = (
        f"{existing_server_timing}, {total_metric}"
        if existing_server_timing
        else total_metric
    )
    return response


@app.get("/home")
async def home_redirect():
    """Legacy route support for home; redirect to formats."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/formats", status_code=302)


@app.get("/")
async def root(request: Request):
    """Redirect to login or role-based formats home."""
    from app.auth.dependencies import get_current_user_optional
    auth = await get_current_user_optional(request)
    if auth:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/formats", status_code=302)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/auth/login", status_code=302)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
