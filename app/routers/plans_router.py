"""Plans CRUD routes."""
import logging
from time import perf_counter
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import get_current_user, require_role, get_access_token
from app.config import ROLE_ADMIN, DEPARTMENT_ROLES
from app.services.plans_service import list_plans, get_plan, create_plan, update_plan, delete_plan
from app.services.departments_service import list_departments
from app.services.activities_service import list_activities_for_plan, get_plan_weeks

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, legal, landscape
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import xlsxwriter
import io
from datetime import date, timedelta
from calendar import monthrange

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_weeks_and_day_numbers(year: int, month: int):
    """Get ISO week numbers and day numbers matrix for a given month."""
    start = date(year, month, 1)
    _, last_day = monthrange(year, month)
    last_day_date = date(year, month, last_day)
    start_monday = start - timedelta(days=start.weekday())  # Monday = 0
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


def _get_department_logo_path(dept_code: str) -> str | None:
    """Get logo path for department code."""
    logo_map = {
        'FNMI': 'logo_fdnmi.png',
        'IMMUJER': 'logo_inmujer.png',
        'CMDNNA': 'logo_cmdnna.png',
        'CPNNA': 'logo_cpnna.png',
    }
    logo = logo_map.get(dept_code)
    if logo:
        return f"static/images/{logo}"
    return None


def _get_month_name(month: int) -> str:
    """Get month name in Spanish."""
    months = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]
    return months[month - 1]


def _get_user_department_id(auth):
    """Get department_id for filtering. None for admin = no filter."""
    profile = auth.get("profile") if auth else None
    if not profile:
        return None
    if profile.get("role") == ROLE_ADMIN:
        return None
    return profile.get("department_id")


def _render_plans_list_partial(request: Request, auth, plans):
    """Render the plans list partial for HTMX refreshes."""
    from app.templating import templates

    return templates.TemplateResponse(request, "plans/_plans_list.html", context={"request": request, "user": auth, "plans": plans})


def _record_stage(timings: list[tuple[str, float]], label: str, started_at: float) -> float:
    """Store elapsed milliseconds for a stage and return a fresh timer."""
    timings.append((label, (perf_counter() - started_at) * 1000))
    return perf_counter()


def _apply_timing_headers(request: Request, response, timings: list[tuple[str, float]], label: str):
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


@router.get("", response_class=HTMLResponse)
async def list_plans_view(
    request: Request,
    department_id: str | None = Query(default=None),
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    """List action plans for the user's department."""
    from app.templating import templates
    timings = []
    stage_started_at = perf_counter()
    token = auth.get("access_token")
    refresh = auth.get("refresh_token")
    dept_id = _get_user_department_id(auth)
    departments = await list_departments() if not dept_id else []
    selected_department = department_id
    if dept_id:
        selected_department = str(dept_id)
    plans = await list_plans(token, selected_department, refresh)
    plans = sorted(
        plans,
        key=lambda plan: (int(plan.get("year") or 0), int(plan.get("month") or 0)),
        reverse=True,
    )
    stage_started_at = _record_stage(timings, "list_plans", stage_started_at)
    response = templates.TemplateResponse(request, "plans/list.html", context={
            "request": request,
            "user": auth,
            "plans": plans,
            "departments": departments,
            "selected_department": selected_department,
        })
    _record_stage(timings, "render_page", stage_started_at)
    _apply_timing_headers(request, response, timings, "plans.list")
    return response


@router.get("/new", response_class=HTMLResponse)
async def new_plan_form(request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    """Show form to create new plan."""
    from app.templating import templates
    departments = await list_departments()
    user_dept = _get_user_department_id(auth)
    user_dept_obj = next((d for d in departments if str(d["id"]) == str(user_dept)), None) if user_dept else None
    return templates.TemplateResponse(request, "plans/form.html", context={
            "request": request,
            "user": auth,
            "plan": None,
            "current_year": datetime.now().year,
            "departments": departments,
            "user_department_id": str(user_dept) if user_dept else None,
            "user_department_name": user_dept_obj["name"] if user_dept_obj else None,
        })


@router.post("", response_class=RedirectResponse)
async def create_plan_submit(
    request: Request,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
    department_id: str = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    goal: str = Form(""),
):
    """Create a new plan."""
    timings = []
    stage_started_at = perf_counter()
    profile = auth.get("profile")
    if profile.get("role") != ROLE_ADMIN:
        # Department users can only create for their department
        if str(profile.get("department_id")) != department_id:
            from fastapi import HTTPException
            raise HTTPException(403, "No puede crear planes para otro departamento")
    stage_started_at = _record_stage(timings, "validate_role", stage_started_at)
    plan = await create_plan(
        department_id=department_id,
        month=month,
        year=year,
        goal=goal,
        created_by=str(auth["user"].id),
        access_token=auth.get("access_token"),
        refresh_token=auth.get("refresh_token"),
    )
    response = RedirectResponse(url=f"/plans/{plan['id']}", status_code=302)
    _record_stage(timings, "create_plan", stage_started_at)
    _apply_timing_headers(request, response, timings, "plans.create")
    return response


@router.get("/{plan_id}", response_class=HTMLResponse)
async def view_plan(request: Request, plan_id: str, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    """View and edit a plan with its activities."""
    from datetime import date
    from calendar import monthrange
    from app.templating import templates
    timings = []
    stage_started_at = perf_counter()
    plan = await get_plan(plan_id, auth.get("access_token"), auth.get("refresh_token"))
    stage_started_at = _record_stage(timings, "get_plan", stage_started_at)
    if not plan:
        from fastapi import HTTPException
        raise HTTPException(404, "Plan no encontrado")
    token, refresh = auth.get("access_token"), auth.get("refresh_token")
    activities = await list_activities_for_plan(plan_id, token, refresh)
    stage_started_at = _record_stage(timings, "list_activities", stage_started_at)

    # Show the calendar weeks (ISO weeks) that cover the month.
    # Use up to 5 weeks when the month stretches across 5 ISO weeks.
    from datetime import timedelta

    start = date(plan["year"], plan["month"], 1)
    _, last_day = monthrange(plan["year"], plan["month"])
    last_day_date = date(plan["year"], plan["month"], last_day)

    start_monday = start - timedelta(days=start.weekday())  # Monday = 0

    weeks = []
    week_day_numbers = []

    week_start = start_monday
    while week_start <= last_day_date:
        weeks.append(week_start.isocalendar()[1])

        week_days = []
        for dow in range(7):
            day = week_start + timedelta(days=dow)
            week_days.append(day.day if day.month == plan["month"] else "")
        week_day_numbers.append(week_days)

        week_start += timedelta(weeks=1)

    stage_started_at = _record_stage(timings, "build_calendar", stage_started_at)
    response = templates.TemplateResponse(request, "plans/detail.html", context={
            "request": request,
            "user": auth,
            "plan": plan,
            "plan_id": plan_id,
            "activities": activities,
            "weeks": weeks,
            "week_day_numbers": week_day_numbers,
        })
    _record_stage(timings, "render_page", stage_started_at)
    _apply_timing_headers(request, response, timings, "plans.view")
    return response


@router.post("/{plan_id}")
async def update_plan_submit(
    request: Request,
    plan_id: str,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
    month: int = Form(None),
    year: int = Form(None),
    goal: str = Form(None),
):
    """Update plan metadata."""
    timings = []
    stage_started_at = perf_counter()
    plan = await get_plan(plan_id, auth.get("access_token"), auth.get("refresh_token"))
    stage_started_at = _record_stage(timings, "get_plan", stage_started_at)
    if not plan:
        from fastapi import HTTPException
        raise HTTPException(404, "Plan no encontrado")
    updated = await update_plan(
        plan_id=plan_id,
        month=month,
        year=year,
        goal=goal,
        access_token=auth.get("access_token"),
        refresh_token=auth.get("refresh_token"),
    )
    from fastapi.responses import RedirectResponse
    response = RedirectResponse(url=f"/plans/{plan_id}", status_code=302)
    _record_stage(timings, "update_plan", stage_started_at)
    _apply_timing_headers(request, response, timings, "plans.update")
    return response


@router.delete("/{plan_id}")
async def delete_plan_route(
    request: Request,
    plan_id: str,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    """Delete a plan."""
    timings = []
    stage_started_at = perf_counter()
    plan = await get_plan(plan_id, auth.get("access_token"), auth.get("refresh_token"))
    stage_started_at = _record_stage(timings, "get_plan", stage_started_at)
    if not plan:
        from fastapi import HTTPException
        raise HTTPException(404, "Plan no encontrado")
    await delete_plan(plan_id, auth.get("access_token"), auth.get("refresh_token"))
    stage_started_at = _record_stage(timings, "delete_plan", stage_started_at)
    if request.headers.get("HX-Request"):
        token = auth.get("access_token")
        refresh = auth.get("refresh_token")
        dept_id = _get_user_department_id(auth)
        plans = await list_plans(token, str(dept_id) if dept_id else None, refresh)
        stage_started_at = _record_stage(timings, "list_plans", stage_started_at)
        response = _render_plans_list_partial(request, auth, plans)
        _record_stage(timings, "render_partial", stage_started_at)
        _apply_timing_headers(request, response, timings, "plans.delete")
        return response
    from fastapi.responses import RedirectResponse
    response = RedirectResponse(url="/plans", status_code=302)
    _apply_timing_headers(request, response, timings, "plans.delete")
    return response


@router.get("/{plan_id}/export/pdf")
async def export_plan_pdf(
    plan_id: str,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    """Export plan to PDF."""
    from fastapi import HTTPException
    from fastapi.responses import Response, PlainTextResponse
    try:
        plan = await get_plan(plan_id, auth.get("access_token"), auth.get("refresh_token"))
        if not plan:
            raise HTTPException(404, "Plan no encontrado")

        token, refresh = auth.get("access_token"), auth.get("refresh_token")
        activities = await list_activities_for_plan(plan_id, token, refresh)
        weeks, week_day_numbers = _get_weeks_and_day_numbers(plan["year"], plan["month"])

        days = ["L", "M", "M", "J", "V", "S", "D"]

        # Header with week spin. Remove metas column to fit page.
        header_row_0 = ["Ente Responsable", "Actividad", "Lugar", "Logística"]
        for w in weeks:
            header_row_0.extend([f"Semana {w}"] + ["", "", "", "", "", ""])

        header_row_1 = ["", "", "", ""]
        for _ in weeks:
            header_row_1.extend(days)

        header_row_2 = ["", "", "", ""]
        for day_numbers in week_day_numbers:
            header_row_2.extend([str(d) if d else "" for d in day_numbers])

        table_data = [header_row_0, header_row_1, header_row_2]

        if not activities:
            row = [
                plan.get("departments", {}).get("name", "") if plan.get("departments") else "",
                "",
                "",
                "",
            ]
            row.extend(["" for _ in range(len(weeks) * 7)])
            table_data.append(row)
        else:
            for activity in activities:
                row = [
                    plan.get("departments", {}).get("name", "") if plan.get("departments") else "",
                    activity.get("description", ""),
                    activity.get("location", ""),
                    activity.get("logistics", ""),
                ]
                for w in weeks:
                    schedule = next((s for s in (activity.get("activity_schedules") or []) if s.get("week_number") == w), None)
                    for day_flag in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                        row.append("X" if schedule and schedule.get(day_flag) else "")
                table_data.append(row)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(legal), leftMargin=18, rightMargin=18, topMargin=50, bottomMargin=12)
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='TableJustify', parent=styles['BodyText'], alignment=TA_JUSTIFY, fontSize=7, leading=8))

        # Header with logo and title
        dept_code = plan.get("departments", {}).get("code", "") if plan.get("departments") else ""
        logo_path = _get_department_logo_path(dept_code)
        title_text = f"PLAN DE ACCIÓN {_get_month_name(plan['month'])} {plan['year']}"
        title = Paragraph(title_text, styles["Title"])

        if logo_path:
            logo = Image(logo_path, width=100, height=60)
            header_table = Table([[logo, title]], colWidths=[80, None])
            header_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elems = [header_table, Spacer(1, 12)]
        else:
            elems = [title, Spacer(1, 12)]

        elems.append(Paragraph(f"Meta: {plan.get('goal', '')}", styles["Normal"]))
        elems.append(Spacer(1, 12))

        base_widths = [85, 150, 75, 75]
        # Fill most of legal-landscape width while adapting to 4-6 week months.
        page_width, _ = landscape(legal)
        available_width = page_width - doc.leftMargin - doc.rightMargin
        fixed_width = sum(base_widths)
        day_cols_count = max(1, len(weeks) * 7)
        day_col_width = max(13, (available_width - fixed_width) / day_cols_count)
        col_widths = base_widths + [day_col_width for _ in range(day_cols_count)]

        header_style = ParagraphStyle(
            name='Header',
            parent=styles['Heading5'],
            alignment=1,
            fontSize=7,
            leading=8,
            wordWrap='CJK',
            allowOrphans=0,
            allowWidows=0,
        )
        week_day_style = ParagraphStyle(
            name='WeekDay',
            parent=styles['BodyText'],
            alignment=1,
            fontSize=6,
            leading=7,
            wordWrap='CJK',
            allowOrphans=0,
            allowWidows=0,
        )

        prepared_data = []
        for idx, row in enumerate(table_data):
            if idx == 0:
                row_style = header_style
            elif idx in (1, 2):
                row_style = week_day_style
            else:
                row_style = styles['TableJustify']
            prepared_data.append([
                Paragraph(str(cell), row_style) if cell is not None else Paragraph('', row_style)
                for cell in row
            ])

        table = Table(prepared_data, colWidths=col_widths, repeatRows=3, splitByRow=1, hAlign='LEFT')

        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 2), 'CENTER'),
            ('ALIGN', (0, 3), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('WORDWRAP', (0, 0), (-1, -1), 'CJK'),
        ])

        # Merge each week header across its 7 day columns.
        for i, _ in enumerate(weeks):
            start_col = 4 + (i * 7)
            end_col = start_col + 6
            table_style.add('SPAN', (start_col, 0), (end_col, 0))


        table.setStyle(table_style)

        elems.append(table)
        doc.build(elems)
        buffer.seek(0)
        return Response(content=buffer.getvalue(), media_type='application/pdf', headers={"Content-Disposition": f"attachment; filename=plan_{plan_id}.pdf"})

    except Exception as err:
        import traceback
        traceback.print_exc()
        return PlainTextResponse(f"Error al generar PDF: {err}", status_code=500)


@router.get("/{plan_id}/export/excel")
async def export_plan_excel(
    plan_id: str,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    """Export plan to Excel."""
    from fastapi import HTTPException
    from fastapi.responses import Response, PlainTextResponse
    try:
        plan = await get_plan(plan_id, auth.get("access_token"), auth.get("refresh_token"))
        if not plan:
            raise HTTPException(404, "Plan no encontrado")
        token, refresh = auth.get("access_token"), auth.get("refresh_token")
        activities = await list_activities_for_plan(plan_id, token, refresh)
        weeks, week_day_numbers = _get_weeks_and_day_numbers(plan["year"], plan["month"])

        days = ["L", "M", "M", "J", "V", "S", "D"]

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Plan')

        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1, 'align': 'center'})
        wrap_format = workbook.add_format({'text_wrap': True, 'border': 1, 'align': 'left', 'valign': 'top'})

        # Title
        title_text = f"PLAN DE ACCIÓN {_get_month_name(plan['month'])} {plan['year']}"
        worksheet.merge_range(0, 0, 0, 4, title_text, workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'}))
        row_idx = 2  # Start after title

        # Header rows to mirror app: meta/ente/actividad/lugar/logística, then week and day letters/numbers
        header_row_1 = ["Metas", "Ente Responsable", "Actividad", "Lugar", "Logística"]
        for w in weeks:
            header_row_1.extend([f"Semana {w}"] + ["", "", "", "", "", ""])

        header_row_2 = ["", "", "", "", ""]
        for _ in weeks:
            header_row_2.extend(days)

        header_row_3 = ["", "", "", "", ""]
        for week_days in week_day_numbers:
            header_row_3.extend([str(d) if d else "" for d in week_days])

        for col, value in enumerate(header_row_1):
            worksheet.write(row_idx, col, value, header_format)
            worksheet.set_column(col, col, 18 if col < 5 else 10)

        # Merge week headers in row 2 (current row_idx)
        for i, w in enumerate(weeks):
            start_col = 5 + i * 7
            end_col = start_col + 6
            worksheet.merge_range(row_idx, start_col, row_idx, end_col, f"Semana {w}", header_format)
        row_idx += 1

        for col, value in enumerate(header_row_2):
            worksheet.write(row_idx, col, value, header_format)
        row_idx += 1

        for col, value in enumerate(header_row_3):
            worksheet.write(row_idx, col, value, header_format)
        row_idx += 1
        if not activities:
            row = [
                plan.get('goal', ''),
                plan.get('departments', {}).get('name', '') if plan.get('departments') else '',
                '',
                '',
                '',
            ]
            row.extend(['' for _ in range(len(weeks) * 7)])
            for col, value in enumerate(row):
                worksheet.write(row_idx, col, value, wrap_format)
        else:
            for act in activities:
                row = [
                    plan.get('goal', ''),
                    plan.get('departments', {}).get('name', '') if plan.get('departments') else '',
                    act.get('description', ''),
                    act.get('location', ''),
                    act.get('logistics', ''),
                ]
                for w in weeks:
                    schedule = next((s for s in (act.get('activity_schedules') or []) if s.get('week_number') == w), None)
                    for day_flag in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                        row.append('X' if schedule and schedule.get(day_flag) else '')
                for col, value in enumerate(row):
                    worksheet.write(row_idx, col, value, wrap_format)
                row_idx += 1

        workbook.close()
        output.seek(0)
        return Response(content=output.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={"Content-Disposition": f"attachment; filename=plan_{plan_id}.xlsx"})

    except Exception as err:
        import traceback
        traceback.print_exc()
        return PlainTextResponse(f"Error al generar Excel: {err}", status_code=500)
