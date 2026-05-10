"""Service for CMDNNA defenders CRUD."""

from app.services.supabase_client import get_async_supabase_client


async def list_cmdnna_defenders(
    department_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
    search_query: str | None = None,
):
    """List CMDNNA defenders for a department."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    query = (
        supabase.table("cmdnna_defenders")
        .select("id, department_id, apellidos, nombres, cedula, registro_asignado, condicion, tipo_defensor, fecha_entrada, fecha_vencimiento, created_at")
        .eq("department_id", department_id)
        .order("created_at", desc=False)
    )
    if search_query:
        needle = search_query.strip().replace(".", "")
        query = query.or_(
            f"apellidos.ilike.%{needle}%,nombres.ilike.%{needle}%,cedula.ilike.%{needle}%"
        )

    result = await query.execute()
    return result.data


async def get_cmdnna_defender(
    defender_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
):
    """Get CMDNNA defender by id."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    result = await supabase.table("cmdnna_defenders").select("*").eq("id", defender_id).execute()
    return result.data[0] if result.data else None


async def create_cmdnna_defender(
    department_id: str,
    payload: dict,
    created_by: str,
    access_token: str | None,
    refresh_token: str | None = None,
):
    """Create CMDNNA defender record."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    result = await (
        supabase.table("cmdnna_defenders")
        .insert(
            {
                "department_id": department_id,
                "apellidos": payload.get("apellidos", ""),
                "nombres": payload.get("nombres", ""),
                "cedula": payload.get("cedula", ""),
                "registro_asignado": payload.get("registro_asignado", ""),
                "condicion": payload.get("condicion", ""),
                "tipo_defensor": payload.get("tipo_defensor", ""),
                "fecha_entrada": payload.get("fecha_entrada") or None,
                "fecha_vencimiento": payload.get("fecha_vencimiento") or None,
                "created_by": created_by,
            }
        )
        .execute()
    )
    return result.data[0] if result.data else None


async def update_cmdnna_defender(
    defender_id: str,
    payload: dict,
    access_token: str | None,
    refresh_token: str | None = None,
):
    """Update CMDNNA defender record."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    result = await (
        supabase.table("cmdnna_defenders")
        .update(
            {
                "apellidos": payload.get("apellidos", ""),
                "nombres": payload.get("nombres", ""),
                "cedula": payload.get("cedula", ""),
                "registro_asignado": payload.get("registro_asignado", ""),
                "condicion": payload.get("condicion", ""),
                "tipo_defensor": payload.get("tipo_defensor", ""),
                "fecha_entrada": payload.get("fecha_entrada") or None,
                "fecha_vencimiento": payload.get("fecha_vencimiento") or None,
            }
        )
        .eq("id", defender_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def delete_cmdnna_defender(
    defender_id: str,
    access_token: str | None,
    refresh_token: str | None = None,
):
    """Delete CMDNNA defender record."""
    supabase = await get_async_supabase_client(access_token=access_token, refresh_token=refresh_token)
    await supabase.table("cmdnna_defenders").delete().eq("id", defender_id).execute()
