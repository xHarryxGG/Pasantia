"""Service for FNMI psicopedagogia forms CRUD."""

from datetime import datetime

from app.services.supabase_client import get_async_supabase_client


def _normalize_search_date(search_query: str) -> str | None:
    value = (search_query or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


async def list_fnmi_psicopedagogia_forms(
    department_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
    search_query: str | None = None,
):
    """List FNMI psicopedagogia forms for a department."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    query = (
        supabase.table("fnmi_psicopedagogia_forms")
        .select("id, department_id, nombre_apellido, lugar_nacimiento, colegio_estudio, fecha_evaluacion, created_at")
        .eq("department_id", department_id)
        .order("created_at", desc=True)
    )
    if search_query:
        date_value = _normalize_search_date(search_query)
        if date_value:
            query = query.eq("fecha_evaluacion", date_value)
        else:
            query = query.ilike("nombre_apellido", f"%{search_query.strip()}%")

    result = await query.execute()
    return result.data


async def get_fnmi_psicopedagogia_form(
    form_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
):
    """Get FNMI psicopedagogia form by id."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    result = await supabase.table("fnmi_psicopedagogia_forms").select("*").eq("id", form_id).execute()
    return result.data[0] if result.data else None


async def create_fnmi_psicopedagogia_form(
    department_id: str,
    payload: dict,
    created_by: str,
    access_token: str | None,
    refresh_token: str | None = None,
):
    """Create FNMI psicopedagogia form record."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    result = await (
        supabase.table("fnmi_psicopedagogia_forms")
        .insert(
            {
                "department_id": department_id,
                "nombre_apellido": payload.get("nombre_apellido", ""),
                "lugar_nacimiento": payload.get("lugar_nacimiento", ""),
                "colegio_estudio": payload.get("colegio_estudio", ""),
                "fecha_evaluacion": payload.get("fecha_evaluacion") or None,
                "aspecto_fisico": payload.get("aspecto_fisico", ""),
                "motricidad_gruesa": payload.get("motricidad_gruesa", ""),
                "motricidad_fina": payload.get("motricidad_fina", ""),
                "esquema_corporal": payload.get("esquema_corporal", ""),
                "orientacion_temporo_espacial": payload.get("orientacion_temporo_espacial", ""),
                "memoria": payload.get("memoria", ""),
                "atencion_concentracion": payload.get("atencion_concentracion", ""),
                "lenguaje": payload.get("lenguaje", ""),
                "aspecto_social": payload.get("aspecto_social", ""),
                "aspecto_escolar_lectura": payload.get("aspecto_escolar_lectura", ""),
                "escritura": payload.get("escritura", ""),
                "pre_calculo": payload.get("pre_calculo", ""),
                "recomendaciones": payload.get("recomendaciones", ""),
                "created_by": created_by,
            }
        )
        .execute()
    )
    return result.data[0] if result.data else None


async def update_fnmi_psicopedagogia_form(
    form_id: str,
    payload: dict,
    access_token: str | None,
    refresh_token: str | None = None,
):
    """Update FNMI psicopedagogia form record."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    result = await (
        supabase.table("fnmi_psicopedagogia_forms")
        .update(
            {
                "nombre_apellido": payload.get("nombre_apellido", ""),
                "lugar_nacimiento": payload.get("lugar_nacimiento", ""),
                "colegio_estudio": payload.get("colegio_estudio", ""),
                "fecha_evaluacion": payload.get("fecha_evaluacion") or None,
                "aspecto_fisico": payload.get("aspecto_fisico", ""),
                "motricidad_gruesa": payload.get("motricidad_gruesa", ""),
                "motricidad_fina": payload.get("motricidad_fina", ""),
                "esquema_corporal": payload.get("esquema_corporal", ""),
                "orientacion_temporo_espacial": payload.get("orientacion_temporo_espacial", ""),
                "memoria": payload.get("memoria", ""),
                "atencion_concentracion": payload.get("atencion_concentracion", ""),
                "lenguaje": payload.get("lenguaje", ""),
                "aspecto_social": payload.get("aspecto_social", ""),
                "aspecto_escolar_lectura": payload.get("aspecto_escolar_lectura", ""),
                "escritura": payload.get("escritura", ""),
                "pre_calculo": payload.get("pre_calculo", ""),
                "recomendaciones": payload.get("recomendaciones", ""),
            }
        )
        .eq("id", form_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def delete_fnmi_psicopedagogia_form(
    form_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
):
    """Delete FNMI psicopedagogia form record."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    await supabase.table("fnmi_psicopedagogia_forms").delete().eq("id", form_id).execute()
