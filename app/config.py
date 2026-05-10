"""Configuration for SIPF application."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde la raíz del proyecto
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

# Role constants
ROLE_ADMIN = "admin"
ROLE_FUNDACION_NINO = "fundacion_nino"
ROLE_IMMUJER = "immujer"
ROLE_CMDNNA = "cmdnna"
ROLE_CPNNA = "cpnna"

ALL_ROLES = [ROLE_ADMIN, ROLE_FUNDACION_NINO, ROLE_IMMUJER, ROLE_CMDNNA, ROLE_CPNNA]
DEPARTMENT_ROLES = [ROLE_FUNDACION_NINO, ROLE_IMMUJER, ROLE_CMDNNA, ROLE_CPNNA]
