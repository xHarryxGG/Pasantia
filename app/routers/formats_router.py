"""Formats routes by department."""

import io
import logging
from datetime import datetime
from pathlib import Path

import xlsxwriter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.auth.dependencies import require_role
from app.config import DEPARTMENT_ROLES, ROLE_ADMIN
from app.services.cmdnna_defenders_service import (
    create_cmdnna_defender,
    delete_cmdnna_defender,
    get_cmdnna_defender,
    list_cmdnna_defenders,
    update_cmdnna_defender,
)
from app.services.departments_service import list_departments
from app.services.fnmi_psicopedagogia_service import (
    create_fnmi_psicopedagogia_form,
    delete_fnmi_psicopedagogia_form,
    get_fnmi_psicopedagogia_form,
    list_fnmi_psicopedagogia_forms,
    update_fnmi_psicopedagogia_form,
)

router = APIRouter()
logger = logging.getLogger(__name__)

CMDNNA_DEFENDER_FIELDS = [
    "apellidos",
    "nombres",
    "cedula",
    "registro_asignado",
    "condicion",
    "tipo_defensor",
    "fecha_entrada",
    "fecha_vencimiento",
]

CMDNNA_CONDICIONES = ["ACTIVO", "NO ACTIVO", "RENUNCIO"]
CMDNNA_TIPOS_DEFENSOR = ["NNA", "EDUC."]

FNMI_PSICOPEDAGOGIA_FIELDS = [
    "nombre_apellido",
    "lugar_nacimiento",
    "colegio_estudio",
    "fecha_evaluacion",
    "aspecto_fisico",
    "motricidad_gruesa",
    "motricidad_fina",
    "esquema_corporal",
    "orientacion_temporo_espacial",
    "memoria",
    "atencion_concentracion",
    "lenguaje",
    "aspecto_social",
    "aspecto_escolar_lectura",
    "escritura",
    "pre_calculo",
    "recomendaciones",
]


def _is_admin(auth) -> bool:
    profile = auth.get("profile") if auth else None
    return bool(profile and profile.get("role") == ROLE_ADMIN)


def _user_department_id(auth) -> str | None:
    profile = auth.get("profile") if auth else None
    if not profile:
        return None
    dept = profile.get("department_id")
    return str(dept) if dept else None


def _validate_department_access(auth, department_id: str) -> bool:
    """Return True for admin and validate regular user's department access."""
    is_admin = _is_admin(auth)
    if not is_admin and _user_department_id(auth) != str(department_id):
        raise HTTPException(403, "No tiene permisos para ver los formatos de este departamento")
    return is_admin


async def _get_department_or_404(department_id: str) -> dict:
    departments = await list_departments()
    selected_department = next((d for d in departments if str(d["id"]) == str(department_id)), None)
    if not selected_department:
        raise HTTPException(404, "Departamento no encontrado")
    return selected_department


def _friendly_cmdnna_error_message(err: Exception) -> str:
    """Build a user-facing message for CMDNNA defenders errors."""
    text = str(err).lower()
    if "cmdnna_defenders" in text and ("does not exist" in text or "relation" in text):
        return "La tabla de defensores CMDNNA no existe en Supabase. Ejecute el script actualizado de schema.sql."
    return "No se pudo procesar el listado de defensores CMDNNA. Revise la configuracion de Supabase."


def _friendly_fnmi_error_message(err: Exception) -> str:
    """Build a user-facing message for FNMI psicopedagogia errors."""
    text = str(err).lower()
    if "fnmi_psicopedagogia_forms" in text and ("does not exist" in text or "relation" in text):
        return "La tabla de fichas psicopedagogicas FNMI no existe en Supabase. Ejecute el script actualizado de schema.sql."
    if "invalid input syntax" in text and "date" in text:
        return "El campo Fecha de evaluación no tiene un formato válido. Use AAAA-MM-DD."
    return "No se pudo procesar la ficha psicopedagogica FNMI. Revise la configuracion de Supabase."


def _normalize_fnmi_date(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _extract_fnmi_payload(form_data) -> dict:
    payload = {}
    for field in FNMI_PSICOPEDAGOGIA_FIELDS:
        payload[field] = str(form_data.get(field, "")).strip()

    payload["fecha_evaluacion"] = _normalize_fnmi_date(payload.get("fecha_evaluacion"))
    payload["nombre_apellido"] = payload["nombre_apellido"].upper()
    return payload


def _empty_fnmi_payload() -> dict:
    return {field: "" for field in FNMI_PSICOPEDAGOGIA_FIELDS}


def _normalize_fnmi_rows(rows: list[dict]) -> list[dict]:
    normalized = []
    for idx, row in enumerate(rows, start=1):
        item = dict(row)
        item["row_number"] = idx
        item["nombre_apellido"] = str(item.get("nombre_apellido", "")).upper()
        item["fecha_evaluacion_fmt"] = _fmt_cmdnna_date(item.get("fecha_evaluacion"))
        normalized.append(item)
    return normalized


def _split_text_for_width(pdf, text: str, width: float, max_lines: int) -> list[str]:
    words = str(text or "").replace("\r", "").split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if pdf.stringWidth(candidate, "Helvetica", 8) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                return lines
    lines.append(current)
    return lines[:max_lines]


def _draw_fnmi_pdf_header(pdf, page_w: float, page_h: float):
    assets_dir = Path(__file__).resolve().parents[2] / "static" / "images"
    left_logo_path = assets_dir / "logo_fdnmi.png"

    if left_logo_path.exists():
        pdf.drawImage(str(left_logo_path), 42, page_h - 78, width=85, height=44, preserveAspectRatio=True, mask="auto")

    pdf.setFont("Helvetica", 10)
    center_x = page_w / 2
    header_lines = [
        "REPUBLICA BOLIVARIANA DE VENEZUELA",
        "SISTEMA INTEGRAL DE PROTECCION DE LA FAMILIA",
        "FUNDACION DEL NINO, NINA Y ADOLESCENTES",
        "CIUDAD ORINOCO - ESTADO ANZOATEGUI",
    ]
    y = page_h - 50
    for line in header_lines:
        pdf.drawCentredString(center_x, y, line)
        y -= 12


def _draw_fnmi_meta_line(pdf, y: float, label: str, value: str) -> float:
    pdf.setFont("Helvetica", 10)
    pdf.drawString(58, y, f"{label}: {value or ''}")
    return y - 15


def _draw_fnmi_lined_block(pdf, y: float, label: str, value: str, line_count: int, line_gap: int = 13) -> float:
    left = 58
    right = 554
    first_line_y = y - 14

    if label:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left, y, f"{label}:")

    for idx in range(line_count):
        line_y = first_line_y - (idx * line_gap)
        pdf.line(left, line_y, right, line_y)

    wrapped_lines = _split_text_for_width(pdf, value or "", right - left - 6, line_count)
    pdf.setFont("Helvetica", 10)
    for idx, line in enumerate(wrapped_lines):
        line_y = first_line_y - (idx * line_gap)
        pdf.drawString(left + 3, line_y + 4, line)

    return first_line_y - (line_count * line_gap) - 10


def _build_fnmi_psicopedagogia_pdf_bytes(data: dict) -> bytes:
    buffer = io.BytesIO()
    pdf = pdf_canvas.Canvas(buffer, pagesize=letter)
    page_w, page_h = letter

    # Page 1
    _draw_fnmi_pdf_header(pdf, page_w, page_h)
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(page_w / 2, page_h - 120, "FICHA DE EVALUACION - PSICOPEDAGOGIA")

    y = page_h - 160
    y = _draw_fnmi_meta_line(pdf, y, "Nombre y Apellido", str(data.get("nombre_apellido") or ""))
    y = _draw_fnmi_meta_line(pdf, y, "Lugar de Nacimiento", str(data.get("lugar_nacimiento") or ""))
    y = _draw_fnmi_meta_line(pdf, y, "Colegio donde Estudia", str(data.get("colegio_estudio") or ""))
    y = _draw_fnmi_meta_line(pdf, y, "Fecha de Evaluacion", _fmt_cmdnna_date(data.get("fecha_evaluacion")))

    y -= 40
    y = _draw_fnmi_lined_block(pdf, y, "Aspecto Fisico", str(data.get("aspecto_fisico") or ""), line_count=4)
    y -= 15
    y = _draw_fnmi_lined_block(pdf, y, "Motricidad Gruesa", str(data.get("motricidad_gruesa") or ""), line_count=4)
    y -= 15
    y = _draw_fnmi_lined_block(pdf, y, "Motricidad Fina", str(data.get("motricidad_fina") or ""), line_count=4)
    y -= 15
    _draw_fnmi_lined_block(pdf, y, "Esquema Corporal", str(data.get("esquema_corporal") or ""), line_count=4)

    # Page 2
    pdf.showPage()
    _draw_fnmi_pdf_header(pdf, page_w, page_h)
    y = page_h - 130
    y = _draw_fnmi_lined_block(pdf, y, "Orientacion Temporo- Espacial", str(data.get("orientacion_temporo_espacial") or ""), line_count=4)
    y -= 15
    y = _draw_fnmi_lined_block(pdf, y, "Memoria", str(data.get("memoria") or ""), line_count=4)
    y -= 15
    y = _draw_fnmi_lined_block(pdf, y, "Atencion y Concentracion", str(data.get("atencion_concentracion") or ""), line_count=4)
    y -= 15
    y = _draw_fnmi_lined_block(pdf, y, "Lenguaje", str(data.get("lenguaje") or ""), line_count=4)
    y -= 15
    y = _draw_fnmi_lined_block(pdf, y, "Aspecto Social", str(data.get("aspecto_social") or ""), line_count=4)
    y -= 15
    _draw_fnmi_lined_block(pdf, y, "Aspecto Escolar- Lectura", str(data.get("aspecto_escolar_lectura") or ""), line_count=3)

    # Page 3
    pdf.showPage()
    _draw_fnmi_pdf_header(pdf, page_w, page_h)
    y = page_h - 130
    y = _draw_fnmi_lined_block(pdf, y, "Escritura", str(data.get("escritura") or ""), line_count=5)
    y -= 15
    y = _draw_fnmi_lined_block(pdf, y, "Pre- Calculo", str(data.get("pre_calculo") or ""), line_count=5)
    y -= 15
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(page_w / 2, y + 6, "RECOMENDACIONES")
    _draw_fnmi_lined_block(pdf, y - 16, "", str(data.get("recomendaciones") or ""), line_count=10)

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def _extract_cmdnna_payload(form_data) -> dict:
    payload = {}
    for field in CMDNNA_DEFENDER_FIELDS:
        value = str(form_data.get(field, "")).strip()
        payload[field] = value

    payload["apellidos"] = payload["apellidos"].upper()
    payload["nombres"] = payload["nombres"].upper()
    payload["cedula"] = payload["cedula"].replace(".", "")
    payload["registro_asignado"] = payload["registro_asignado"].upper()
    payload["condicion"] = payload["condicion"].upper()
    payload["tipo_defensor"] = payload["tipo_defensor"].upper()
    return payload


def _empty_cmdnna_payload() -> dict:
    return {field: "" for field in CMDNNA_DEFENDER_FIELDS}


def _fmt_cmdnna_date(value: str | None) -> str:
    if not value:
        return ""
    value = str(value)
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def _normalize_cmdnna_rows(rows: list[dict]) -> list[dict]:
    normalized = []
    for idx, row in enumerate(rows, start=1):
        item = dict(row)
        item["row_number"] = idx
        item["apellidos"] = str(item.get("apellidos", "")).upper()
        item["nombres"] = str(item.get("nombres", "")).upper()
        item["cedula"] = str(item.get("cedula", ""))
        item["registro_asignado"] = str(item.get("registro_asignado", "")).upper()
        item["condicion"] = str(item.get("condicion", "")).upper()
        item["tipo_defensor"] = str(item.get("tipo_defensor", "")).upper()
        item["fecha_entrada_fmt"] = _fmt_cmdnna_date(item.get("fecha_entrada"))
        item["fecha_vencimiento_fmt"] = _fmt_cmdnna_date(item.get("fecha_vencimiento"))
        normalized.append(item)
    return normalized


@router.get("", response_class=HTMLResponse)
async def formats_home(request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    if not _is_admin(auth):
        user_department_id = _user_department_id(auth)
        if not user_department_id:
            raise HTTPException(403, "Su usuario no tiene departamento asignado")
        return RedirectResponse(url=f"/formats/{user_department_id}", status_code=302)

    from app.templating import templates

    departments = await list_departments()
    return templates.TemplateResponse(
        "formats/home.html",
        {
            "request": request,
            "user": auth,
            "departments": departments,
        },
    )

@router.get("/{department_id}", response_class=HTMLResponse)
async def department_formats_view(
    request: Request,
    department_id: str,
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    from app.templating import templates

    is_admin = _validate_department_access(auth, department_id)
    selected_department = await _get_department_or_404(department_id)

    return templates.TemplateResponse(
        "formats/department.html",
        {
            "request": request,
            "user": auth,
            "department": selected_department,
            "is_admin": is_admin,
            "show_cmdnna_defenders": selected_department.get("code") == "CMDNNA",
            "show_fnmi_psicopedagogia": selected_department.get("code") == "FNMI",
        },
    )


def _build_cmdnna_pdf_bytes(defenders: list[dict]) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=10 * mm,
        bottomMargin=8 * mm,
    )
    available_width = document.width

    assets_dir = Path(__file__).resolve().parents[2] / "static" / "images"
    left_logo_path = assets_dir / "logo_cmdnna.png"
    right_logo_path = assets_dir / "logo_idena.png"

    left_logo = RLImage(str(left_logo_path), width=25 * mm, height=16 * mm) if left_logo_path.exists() else ""
    right_logo = RLImage(str(right_logo_path), width=25 * mm, height=16 * mm) if right_logo_path.exists() else ""

    header_style = ParagraphStyle(
        name="CmdnnaHeader",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        alignment=1,
    )
    header_text = Paragraph(
        (
            "REPUBLICA BOLIVARIANA DE VENEZUELA<br/>"
            "CONSEJO MUNICIPAL DE DERECHOS DE NINOS, NINAS Y ADOLESCENTES (CMDNNA)<br/>"
            "CIUDAD ORINOCO - MUNICIPIO INDEPENDENCIA ESTADO ANZOATEGUI<br/>"
            "RIF: G-20003804-7<br/>"
            f"FECHA DE EMISION: {datetime.now().strftime('%d/%m/%Y')}"
        ),
        header_style,
    )

    logo_col = available_width * 0.11
    center_col = available_width - (2 * logo_col)

    header = Table([[left_logo, header_text, right_logo]], colWidths=[logo_col, center_col, logo_col])
    header.hAlign = "LEFT"
    header.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#7A7A7A")),
            ]
        )
    )

    table_data = [["#", "APELLIDOS", "NOMBRES", "CEDULA DE IDENTIDAD", "REGISTRO ASIGNADO", "ACTIVO/NO ACTIVO", "TIPO DEFENSOR", "FECHA DE ENTRADA", "FECHA DE VENCIMIENTO"]]
    for row in defenders:
        table_data.append([
            row.get("row_number", ""),
            row.get("apellidos", ""),
            row.get("nombres", ""),
            row.get("cedula", ""),
            row.get("registro_asignado", ""),
            row.get("condicion", ""),
            row.get("tipo_defensor", ""),
            row.get("fecha_entrada_fmt", ""),
            row.get("fecha_vencimiento_fmt", ""),
        ])

    if len(table_data) == 1:
        table_data.append(["", "", "", "", "", "", "", "", ""])

    table_col_widths = [available_width * 0.04, available_width * 0.15, available_width * 0.15, available_width * 0.12, available_width * 0.11, available_width * 0.10, available_width * 0.09, available_width * 0.12, 0.0]
    table_col_widths[-1] = available_width - sum(table_col_widths[:-1])

    table = Table(table_data, repeatRows=1, colWidths=table_col_widths)
    table.hAlign = "LEFT"
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2A6EA1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EDF5FB")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#6D7985")),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    document.build([header, Spacer(1, 4 * mm), table])
    buffer.seek(0)
    return buffer.getvalue()


@router.get("/{department_id}/psicopedagogia", response_class=HTMLResponse)
async def fnmi_psicopedagogia_list_view(
    department_id: str,
    request: Request,
    q: str | None = Query(default=None),
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    from app.templating import templates

    is_admin = _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "FNMI":
        raise HTTPException(404, "Este departamento no tiene la ficha psicopedagogica FNMI")

    error_message = None
    search_query = (q or "").strip()
    try:
        forms = await list_fnmi_psicopedagogia_forms(
            department_id=department_id,
            access_token=auth.get("access_token"),
            refresh_token=auth.get("refresh_token"),
            search_query=search_query,
        )
        forms = _normalize_fnmi_rows(forms)
    except Exception as err:
        logger.exception("Error loading FNMI psicopedagogia forms")
        forms = []
        error_message = _friendly_fnmi_error_message(err)

    context = {
        "request": request,
        "user": auth,
        "department": department,
        "is_admin": is_admin,
        "forms": forms,
        "error": error_message,
        "export_token": datetime.now().strftime("%Y%m%d%H%M%S"),
        "filters": {
            "q": search_query,
        },
    }
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse("fnmi_psicopedagogia/_table.html", context)
    return templates.TemplateResponse("fnmi_psicopedagogia/list.html", context)


@router.get("/{department_id}/psicopedagogia/new", response_class=HTMLResponse)
async def fnmi_psicopedagogia_new_form(department_id: str, request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    from app.templating import templates

    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "FNMI":
        raise HTTPException(404, "Este departamento no tiene la ficha psicopedagogica FNMI")

    return templates.TemplateResponse(
        "fnmi_psicopedagogia/form.html",
        {
            "request": request,
            "user": auth,
            "department": department,
            "form_record": None,
            "payload": _empty_fnmi_payload(),
        },
    )


@router.post("/{department_id}/psicopedagogia")
async def fnmi_psicopedagogia_create(department_id: str, request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "FNMI":
        raise HTTPException(404, "Este departamento no tiene la ficha psicopedagogica FNMI")

    form_data = await request.form()
    payload = _extract_fnmi_payload(form_data)
    if not payload.get("nombre_apellido"):
        raise HTTPException(422, "El campo obligatorio es: nombre y apellido.")

    try:
        await create_fnmi_psicopedagogia_form(
            department_id=department_id,
            payload=payload,
            created_by=str(auth["user"].id),
            access_token=auth.get("access_token"),
            refresh_token=auth.get("refresh_token"),
        )
    except Exception as err:
        logger.exception("Error creating FNMI psicopedagogia form")
        raise HTTPException(500, _friendly_fnmi_error_message(err)) from err
    return RedirectResponse(url=f"/formats/{department_id}/psicopedagogia", status_code=302)


@router.get("/{department_id}/psicopedagogia/{form_id}/edit", response_class=HTMLResponse)
async def fnmi_psicopedagogia_edit_form(department_id: str, form_id: str, request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    from app.templating import templates

    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "FNMI":
        raise HTTPException(404, "Este departamento no tiene la ficha psicopedagogica FNMI")

    try:
        form_record = await get_fnmi_psicopedagogia_form(form_id=form_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error loading FNMI psicopedagogia form for edit")
        raise HTTPException(500, _friendly_fnmi_error_message(err)) from err

    if not form_record or str(form_record.get("department_id")) != str(department_id):
        raise HTTPException(404, "Ficha no encontrada")

    payload = {field: str(form_record.get(field) or "") for field in FNMI_PSICOPEDAGOGIA_FIELDS}
    return templates.TemplateResponse(
        "fnmi_psicopedagogia/form.html",
        {
            "request": request,
            "user": auth,
            "department": department,
            "form_record": form_record,
            "payload": payload,
        },
    )


@router.post("/{department_id}/psicopedagogia/{form_id}")
async def fnmi_psicopedagogia_update(department_id: str, form_id: str, request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "FNMI":
        raise HTTPException(404, "Este departamento no tiene la ficha psicopedagogica FNMI")

    try:
        form_record = await get_fnmi_psicopedagogia_form(form_id=form_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error loading FNMI psicopedagogia form for update")
        raise HTTPException(500, _friendly_fnmi_error_message(err)) from err

    if not form_record or str(form_record.get("department_id")) != str(department_id):
        raise HTTPException(404, "Ficha no encontrada")

    form_data = await request.form()
    payload = _extract_fnmi_payload(form_data)
    if not payload.get("nombre_apellido"):
        raise HTTPException(422, "El campo obligatorio es: nombre y apellido.")

    try:
        await update_fnmi_psicopedagogia_form(
            form_id=form_id,
            payload=payload,
            access_token=auth.get("access_token"),
            refresh_token=auth.get("refresh_token"),
        )
    except Exception as err:
        logger.exception("Error updating FNMI psicopedagogia form")
        raise HTTPException(500, _friendly_fnmi_error_message(err)) from err
    return RedirectResponse(url=f"/formats/{department_id}/psicopedagogia", status_code=302)


@router.post("/{department_id}/psicopedagogia/{form_id}/delete")
async def fnmi_psicopedagogia_delete(department_id: str, form_id: str, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "FNMI":
        raise HTTPException(404, "Este departamento no tiene la ficha psicopedagogica FNMI")

    try:
        form_record = await get_fnmi_psicopedagogia_form(form_id=form_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error loading FNMI psicopedagogia form for delete")
        raise HTTPException(500, _friendly_fnmi_error_message(err)) from err

    if not form_record or str(form_record.get("department_id")) != str(department_id):
        raise HTTPException(404, "Ficha no encontrada")

    try:
        await delete_fnmi_psicopedagogia_form(form_id=form_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error deleting FNMI psicopedagogia form")
        raise HTTPException(500, _friendly_fnmi_error_message(err)) from err
    return RedirectResponse(url=f"/formats/{department_id}/psicopedagogia", status_code=302)


@router.get("/{department_id}/psicopedagogia/{form_id}/export/pdf")
async def fnmi_psicopedagogia_export_pdf(department_id: str, form_id: str, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    from fastapi.responses import PlainTextResponse

    try:
        _validate_department_access(auth, department_id)
        department = await _get_department_or_404(department_id)
        if department.get("code") != "FNMI":
            raise HTTPException(404, "Este departamento no tiene la ficha psicopedagogica FNMI")

        form_record = await get_fnmi_psicopedagogia_form(form_id=form_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
        if not form_record or str(form_record.get("department_id")) != str(department_id):
            raise HTTPException(404, "Ficha no encontrada")

        content = _build_fnmi_psicopedagogia_pdf_bytes(form_record)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ficha_psicopedagogia_fnmi_{department_id}_{timestamp}.pdf"
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Export-Version": "fnmi-psicopedagogia-pdf-v1",
            },
        )
    except Exception as err:
        logger.exception("Error exporting FNMI psicopedagogia PDF")
        return PlainTextResponse(f"Error al generar PDF FNMI: {err}", status_code=500)


@router.get("/{department_id}/defensores", response_class=HTMLResponse)
async def cmdnna_defenders_list_view(
    department_id: str,
    request: Request,
    q: str | None = Query(default=None),
    auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES)),
):
    from app.templating import templates

    is_admin = _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "CMDNNA":
        raise HTTPException(404, "Este departamento no tiene el listado de defensores CMDNNA")

    error_message = None
    search_query = (q or "").strip()
    try:
        defenders = await list_cmdnna_defenders(
            department_id=department_id,
            access_token=auth.get("access_token"),
            refresh_token=auth.get("refresh_token"),
            search_query=search_query,
        )
        defenders = _normalize_cmdnna_rows(defenders)
    except Exception as err:
        logger.exception("Error loading CMDNNA defenders")
        defenders = []
        error_message = _friendly_cmdnna_error_message(err)

    context = {
        "request": request,
        "user": auth,
        "department": department,
        "is_admin": is_admin,
        "defenders": defenders,
        "error": error_message,
        "export_token": datetime.now().strftime("%Y%m%d%H%M%S"),
        "filters": {
            "q": search_query,
        },
    }
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse("defensores/_table.html", context)
    return templates.TemplateResponse("defensores/list.html", context)


@router.get("/{department_id}/defensores/new", response_class=HTMLResponse)
async def cmdnna_defenders_new_form(department_id: str, request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    from app.templating import templates

    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "CMDNNA":
        raise HTTPException(404, "Este departamento no tiene el listado de defensores CMDNNA")

    return templates.TemplateResponse(
        "defensores/form.html",
        {
            "request": request,
            "user": auth,
            "department": department,
            "defender": None,
            "payload": _empty_cmdnna_payload(),
            "condiciones": CMDNNA_CONDICIONES,
            "tipos_defensor": CMDNNA_TIPOS_DEFENSOR,
        },
    )


@router.post("/{department_id}/defensores")
async def cmdnna_defenders_create(department_id: str, request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "CMDNNA":
        raise HTTPException(404, "Este departamento no tiene el listado de defensores CMDNNA")

    form_data = await request.form()
    payload = _extract_cmdnna_payload(form_data)
    if not payload.get("apellidos") or not payload.get("nombres") or not payload.get("cedula"):
        raise HTTPException(422, "Los campos obligatorios son: apellidos, nombres y cedula.")
    if not payload.get("registro_asignado") or not payload.get("condicion") or not payload.get("tipo_defensor"):
        raise HTTPException(422, "Debe completar registro asignado, condicion y tipo de defensor.")

    try:
        await create_cmdnna_defender(department_id=department_id, payload=payload, created_by=str(auth["user"].id), access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error creating CMDNNA defender")
        raise HTTPException(500, _friendly_cmdnna_error_message(err)) from err
    return RedirectResponse(url=f"/formats/{department_id}/defensores", status_code=302)


@router.get("/{department_id}/defensores/{defender_id}/edit", response_class=HTMLResponse)
async def cmdnna_defenders_edit_form(department_id: str, defender_id: str, request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    from app.templating import templates

    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "CMDNNA":
        raise HTTPException(404, "Este departamento no tiene el listado de defensores CMDNNA")

    try:
        defender = await get_cmdnna_defender(defender_id=defender_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error loading CMDNNA defender for edit")
        raise HTTPException(500, _friendly_cmdnna_error_message(err)) from err

    if not defender or str(defender.get("department_id")) != str(department_id):
        raise HTTPException(404, "Defensor no encontrado")

    payload = {field: str(defender.get(field) or "") for field in CMDNNA_DEFENDER_FIELDS}
    return templates.TemplateResponse(
        "defensores/form.html",
        {
            "request": request,
            "user": auth,
            "department": department,
            "defender": defender,
            "payload": payload,
            "condiciones": CMDNNA_CONDICIONES,
            "tipos_defensor": CMDNNA_TIPOS_DEFENSOR,
        },
    )


@router.post("/{department_id}/defensores/{defender_id}")
async def cmdnna_defenders_update(department_id: str, defender_id: str, request: Request, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "CMDNNA":
        raise HTTPException(404, "Este departamento no tiene el listado de defensores CMDNNA")

    try:
        defender = await get_cmdnna_defender(defender_id=defender_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error loading CMDNNA defender for update")
        raise HTTPException(500, _friendly_cmdnna_error_message(err)) from err

    if not defender or str(defender.get("department_id")) != str(department_id):
        raise HTTPException(404, "Defensor no encontrado")

    form_data = await request.form()
    payload = _extract_cmdnna_payload(form_data)
    if not payload.get("apellidos") or not payload.get("nombres") or not payload.get("cedula"):
        raise HTTPException(422, "Los campos obligatorios son: apellidos, nombres y cedula.")
    if not payload.get("registro_asignado") or not payload.get("condicion") or not payload.get("tipo_defensor"):
        raise HTTPException(422, "Debe completar registro asignado, condicion y tipo de defensor.")

    try:
        await update_cmdnna_defender(defender_id=defender_id, payload=payload, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error updating CMDNNA defender")
        raise HTTPException(500, _friendly_cmdnna_error_message(err)) from err
    return RedirectResponse(url=f"/formats/{department_id}/defensores", status_code=302)


@router.post("/{department_id}/defensores/{defender_id}/delete")
async def cmdnna_defenders_delete(department_id: str, defender_id: str, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    _validate_department_access(auth, department_id)
    department = await _get_department_or_404(department_id)
    if department.get("code") != "CMDNNA":
        raise HTTPException(404, "Este departamento no tiene el listado de defensores CMDNNA")

    try:
        defender = await get_cmdnna_defender(defender_id=defender_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error loading CMDNNA defender for delete")
        raise HTTPException(500, _friendly_cmdnna_error_message(err)) from err

    if not defender or str(defender.get("department_id")) != str(department_id):
        raise HTTPException(404, "Defensor no encontrado")

    try:
        await delete_cmdnna_defender(defender_id=defender_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error deleting CMDNNA defender")
        raise HTTPException(500, _friendly_cmdnna_error_message(err)) from err
    return RedirectResponse(url=f"/formats/{department_id}/defensores", status_code=302)


@router.get("/{department_id}/defensores/export/pdf")
async def cmdnna_defenders_export_pdf(department_id: str, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    from fastapi.responses import PlainTextResponse

    try:
        _validate_department_access(auth, department_id)
        department = await _get_department_or_404(department_id)
        if department.get("code") != "CMDNNA":
            raise HTTPException(404, "Este departamento no tiene el listado de defensores CMDNNA")

        defenders = await list_cmdnna_defenders(department_id=department_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
        normalized = _normalize_cmdnna_rows(defenders)
        content = _build_cmdnna_pdf_bytes(normalized)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; " + f"filename=defensores_cmdnna_v2_{department_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Export-Version": "cmdnna-pdf-v2",
            },
        )
    except Exception as err:
        import traceback

        traceback.print_exc()
        return PlainTextResponse(f"Error al generar PDF CMDNNA: {err}", status_code=500)


@router.get("/{department_id}/defensores/export/excel")
async def cmdnna_defenders_export_excel(department_id: str, auth=Depends(require_role([ROLE_ADMIN] + DEPARTMENT_ROLES))):
    from fastapi.responses import PlainTextResponse

    try:
        _validate_department_access(auth, department_id)
        department = await _get_department_or_404(department_id)
        if department.get("code") != "CMDNNA":
            raise HTTPException(404, "Este departamento no tiene el listado de defensores CMDNNA")
        defenders = await list_cmdnna_defenders(department_id=department_id, access_token=auth.get("access_token"), refresh_token=auth.get("refresh_token"))
    except Exception as err:
        logger.exception("Error loading CMDNNA defenders for Excel export")
        return PlainTextResponse(f"Error al cargar datos para Excel CMDNNA: {err}", status_code=500)

    defenders = _normalize_cmdnna_rows(defenders)
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    try:
        sheet = workbook.add_worksheet("Defensores CMDNNA")
        title_fmt = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "font_size": 10})
        header_fmt = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "font_color": "#FFFFFF", "bg_color": "#2A6EA1", "border": 1, "text_wrap": True})
        cell_fmt = workbook.add_format({"align": "center", "valign": "vcenter", "border": 1})

        sheet.set_row(0, 16)
        sheet.set_row(1, 16)
        sheet.set_row(2, 16)
        sheet.set_row(3, 16)
        sheet.set_column("A:A", 4)
        sheet.set_column("B:B", 20)
        sheet.set_column("C:C", 20)
        sheet.set_column("D:D", 17)
        sheet.set_column("E:E", 18)
        sheet.set_column("F:F", 16)
        sheet.set_column("G:G", 13)
        sheet.set_column("H:H", 13)
        sheet.set_column("I:I", 13)

        sheet.merge_range("B1:H1", "REPUBLICA BOLIVARIANA DE VENEZUELA", title_fmt)
        sheet.merge_range("B2:H2", "CONSEJO MUNICIPAL DE DERECHOS DE NINOS, NINAS Y ADOLESCENTES (CMDNNA)", title_fmt)
        sheet.merge_range("B3:H3", "CIUDAD ORINOCO - MUNICIPIO INDEPENDENCIA ESTADO ANZOATEGUI", title_fmt)
        sheet.merge_range("B4:H4", "RIF: G-20003804-7", title_fmt)
        sheet.merge_range("B5:H5", f"FECHA DE EMISION: {datetime.now().strftime('%d/%m/%Y')}", title_fmt)

        left_logo_path = Path(__file__).resolve().parents[2] / "static" / "images" / "logo_cmdnna.png"
        right_logo_path = Path(__file__).resolve().parents[2] / "static" / "images" / "logo_idena.png"
        try:
            if left_logo_path.exists():
                sheet.insert_image("A1", str(left_logo_path), {"x_scale": 0.55, "y_scale": 0.55, "x_offset": 2, "y_offset": 2})
            if right_logo_path.exists():
                sheet.insert_image("I1", str(right_logo_path), {"x_scale": 0.55, "y_scale": 0.55, "x_offset": 2, "y_offset": 2})
        except Exception:
            logger.exception("Error inserting logos in CMDNNA Excel export")

        headers = ["#", "APELLIDOS", "NOMBRES", "CEDULA DE IDENTIDAD", "REGISTRO ASIGNADO", "ACTIVO/NO ACTIVO", "TIPO DEFENSOR", "FECHA DE ENTRADA", "FECHA DE VENCIMIENTO"]
        header_row = 5
        for col_idx, header in enumerate(headers):
            sheet.write(header_row, col_idx, header, header_fmt)

        row_cursor = header_row + 1
        for defender in defenders:
            sheet.write(row_cursor, 0, defender.get("row_number", ""), cell_fmt)
            sheet.write(row_cursor, 1, defender.get("apellidos", ""), cell_fmt)
            sheet.write(row_cursor, 2, defender.get("nombres", ""), cell_fmt)
            sheet.write(row_cursor, 3, defender.get("cedula", ""), cell_fmt)
            sheet.write(row_cursor, 4, defender.get("registro_asignado", ""), cell_fmt)
            sheet.write(row_cursor, 5, defender.get("condicion", ""), cell_fmt)
            sheet.write(row_cursor, 6, defender.get("tipo_defensor", ""), cell_fmt)
            sheet.write(row_cursor, 7, defender.get("fecha_entrada_fmt", ""), cell_fmt)
            sheet.write(row_cursor, 8, defender.get("fecha_vencimiento_fmt", ""), cell_fmt)
            row_cursor += 1

        if not defenders:
            for col_idx in range(9):
                sheet.write(row_cursor, col_idx, "", cell_fmt)

        workbook.close()
    except Exception as err:
        try:
            workbook.close()
        except Exception:
            pass
        import traceback

        traceback.print_exc()
        return PlainTextResponse(f"Error al generar Excel CMDNNA: {err}", status_code=500)

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; " + f"filename=defensores_cmdnna_v2_{department_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Export-Version": "cmdnna-excel-v2",
        },
    )
