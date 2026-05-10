-- SIPF Database Schema
-- Run this in Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Departments
CREATE TABLE departments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed departments
INSERT INTO departments (code, name) VALUES
    ('FNMI', 'Fundación del Niño Municipio Independencia'),
    ('IMMUJER', 'Instituto Municipal de la Mujer'),
    ('CMDNNA', 'Consejo Municipal de Derechos del Niño, Niña y Adolescente'),
    ('CPNNA', 'Consejo de Protección del Niño, Niña y Adolescente');

-- Profiles (extends auth.users)
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'fundacion_nino',
    full_name VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_role CHECK (role IN ('admin', 'fundacion_nino', 'immujer', 'cmdnna', 'cpnna'))
);

-- RLS for profiles
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own profile"
    ON profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Service role can do everything on profiles"
    ON profiles FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Action plans
CREATE TABLE action_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    month INT NOT NULL CHECK (month >= 1 AND month <= 12),
    year INT NOT NULL CHECK (year >= 2020 AND year <= 2100),
    goal TEXT DEFAULT '',
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(department_id, month, year)
);

ALTER TABLE action_plans ENABLE ROW LEVEL SECURITY;

-- Activities
CREATE TABLE activities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plan_id UUID NOT NULL REFERENCES action_plans(id) ON DELETE CASCADE,
    description TEXT DEFAULT '',
    location VARCHAR(255) DEFAULT '',
    logistics TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE activities ENABLE ROW LEVEL SECURITY;

-- Activity schedules (weekly/day grid)
CREATE TABLE activity_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    activity_id UUID NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    week_number INT NOT NULL,
    monday BOOLEAN DEFAULT FALSE,
    tuesday BOOLEAN DEFAULT FALSE,
    wednesday BOOLEAN DEFAULT FALSE,
    thursday BOOLEAN DEFAULT FALSE,
    friday BOOLEAN DEFAULT FALSE,
    saturday BOOLEAN DEFAULT FALSE,
    sunday BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(activity_id, week_number)
);

ALTER TABLE activity_schedules ENABLE ROW LEVEL SECURITY;

-- CMDNNA defenders list
CREATE TABLE cmdnna_defenders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    apellidos VARCHAR(150) NOT NULL,
    nombres VARCHAR(150) NOT NULL,
    cedula VARCHAR(30) NOT NULL,
    registro_asignado VARCHAR(40) NOT NULL,
    condicion VARCHAR(30) NOT NULL,
    tipo_defensor VARCHAR(30) NOT NULL,
    fecha_entrada DATE,
    fecha_vencimiento DATE,
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE cmdnna_defenders ENABLE ROW LEVEL SECURITY;

-- FNMI psicopedagogia forms
CREATE TABLE fnmi_psicopedagogia_forms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    nombre_apellido VARCHAR(200) NOT NULL,
    lugar_nacimiento VARCHAR(255) DEFAULT '',
    colegio_estudio VARCHAR(255) DEFAULT '',
    fecha_evaluacion DATE,
    aspecto_fisico TEXT DEFAULT '',
    motricidad_gruesa TEXT DEFAULT '',
    motricidad_fina TEXT DEFAULT '',
    esquema_corporal TEXT DEFAULT '',
    orientacion_temporo_espacial TEXT DEFAULT '',
    memoria TEXT DEFAULT '',
    atencion_concentracion TEXT DEFAULT '',
    lenguaje TEXT DEFAULT '',
    aspecto_social TEXT DEFAULT '',
    aspecto_escolar_lectura TEXT DEFAULT '',
    escritura TEXT DEFAULT '',
    pre_calculo TEXT DEFAULT '',
    recomendaciones TEXT DEFAULT '',
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE fnmi_psicopedagogia_forms ENABLE ROW LEVEL SECURITY;

-- Helper: get user's department from profile (for RLS)
CREATE OR REPLACE FUNCTION get_user_department_id()
RETURNS UUID AS $$
    SELECT department_id FROM profiles WHERE id = auth.uid();
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'
    );
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

-- RLS Policies for action_plans
CREATE POLICY "Users can view plans of their department"
    ON action_plans FOR SELECT
    USING (
        is_admin() OR department_id = get_user_department_id()
    );

CREATE POLICY "Users can insert plans for their department"
    ON action_plans FOR INSERT
    WITH CHECK (
        is_admin() OR department_id = get_user_department_id()
    );

CREATE POLICY "Users can update plans of their department"
    ON action_plans FOR UPDATE
    USING (
        is_admin() OR department_id = get_user_department_id()
    )
    WITH CHECK (
        is_admin() OR department_id = get_user_department_id()
    );

CREATE POLICY "Users can delete plans of their department"
    ON action_plans FOR DELETE
    USING (
        is_admin() OR department_id = get_user_department_id()
    );

-- RLS for activities (via plan's department)
CREATE POLICY "Users can view activities of their department plans"
    ON activities FOR SELECT
    USING (
        is_admin() OR EXISTS (
            SELECT 1 FROM action_plans ap
            WHERE ap.id = activities.plan_id
            AND (is_admin() OR ap.department_id = get_user_department_id())
        )
    );

CREATE POLICY "Users can insert activities in their department plans"
    ON activities FOR INSERT
    WITH CHECK (
        is_admin() OR EXISTS (
            SELECT 1 FROM action_plans ap
            WHERE ap.id = activities.plan_id
            AND ap.department_id = get_user_department_id()
        )
    );

CREATE POLICY "Users can update activities of their department plans"
    ON activities FOR UPDATE
    USING (
        is_admin() OR EXISTS (
            SELECT 1 FROM action_plans ap
            WHERE ap.id = activities.plan_id
            AND ap.department_id = get_user_department_id()
        )
    );

CREATE POLICY "Users can delete activities of their department plans"
    ON activities FOR DELETE
    USING (
        is_admin() OR EXISTS (
            SELECT 1 FROM action_plans ap
            WHERE ap.id = activities.plan_id
            AND ap.department_id = get_user_department_id()
        )
    );

-- RLS for activity_schedules (via activity -> plan)
CREATE POLICY "Users can manage schedules of their department activities"
    ON activity_schedules FOR ALL
    USING (
        is_admin() OR EXISTS (
            SELECT 1 FROM activities a
            JOIN action_plans ap ON ap.id = a.plan_id
            WHERE a.id = activity_schedules.activity_id
            AND (is_admin() OR ap.department_id = get_user_department_id())
        )
    )
    WITH CHECK (
        is_admin() OR EXISTS (
            SELECT 1 FROM activities a
            JOIN action_plans ap ON ap.id = a.plan_id
            WHERE a.id = activity_schedules.activity_id
            AND ap.department_id = get_user_department_id()
        )
    );

-- RLS for cmdnna_defenders
CREATE POLICY "Users can view cmdnna defenders of their department"
    ON cmdnna_defenders FOR SELECT
    USING (
        is_admin() OR department_id = get_user_department_id()
    );

CREATE POLICY "Users can insert cmdnna defenders for their department"
    ON cmdnna_defenders FOR INSERT
    WITH CHECK (
        is_admin() OR department_id = get_user_department_id()
    );

CREATE POLICY "Users can update cmdnna defenders of their department"
    ON cmdnna_defenders FOR UPDATE
    USING (
        is_admin() OR department_id = get_user_department_id()
    )
    WITH CHECK (
        is_admin() OR department_id = get_user_department_id()
    );

CREATE POLICY "Users can delete cmdnna defenders of their department"
    ON cmdnna_defenders FOR DELETE
    USING (
        is_admin() OR department_id = get_user_department_id()
    );

-- RLS for fnmi_psicopedagogia_forms
CREATE POLICY "Users can view fnmi forms of their department"
    ON fnmi_psicopedagogia_forms FOR SELECT
    USING (
        is_admin() OR department_id = get_user_department_id()
    );

CREATE POLICY "Users can insert fnmi forms for their department"
    ON fnmi_psicopedagogia_forms FOR INSERT
    WITH CHECK (
        is_admin() OR department_id = get_user_department_id()
    );

CREATE POLICY "Users can update fnmi forms of their department"
    ON fnmi_psicopedagogia_forms FOR UPDATE
    USING (
        is_admin() OR department_id = get_user_department_id()
    )
    WITH CHECK (
        is_admin() OR department_id = get_user_department_id()
    );

CREATE POLICY "Users can delete fnmi forms of their department"
    ON fnmi_psicopedagogia_forms FOR DELETE
    USING (
        is_admin() OR department_id = get_user_department_id()
    );

-- NOTA: El trigger de auto-crear perfil fue removido porque RLS bloquea la inserción.
-- Los perfiles se crean desde la app en /admin/users al crear usuarios.
--
-- To create the first admin: 1) Create user in Supabase Auth (Dashboard > Authentication > Add user);
-- 2) Run: INSERT INTO profiles (id, role) VALUES ('<user-uuid>', 'admin') ON CONFLICT (id) DO UPDATE SET role = 'admin';
