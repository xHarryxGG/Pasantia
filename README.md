# SIPF - Sistema Integral de Protección de la Familia

Aplicación web para la gestión de Planes de Acción del SIPF del Municipio Independencia, Estado Anzoátegui.

## Stack

- **Backend:** FastAPI
- **Frontend:** Jinja2 + HTMX
- **Base de datos y auth:** Supabase

## Configuración

1. Crear archivo `.env` a partir de `.env.example`
2. Configurar las variables de Supabase (URL, anon key, service role key)
3. Ejecutar el script SQL en Supabase para crear las tablas (ver `supabase/schema.sql`)

## Ejecución

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Usuarios

- **Admin:** Acceso total y gestión de usuarios
- **Por departamento:** Fundación del Niño, IMMUJER, CMDNNA, CPNNA (acceso solo a su departamento)
