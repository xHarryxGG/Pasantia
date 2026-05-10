-- FIX: El trigger bloquea la creación de usuarios por RLS.
-- Ejecutar en Supabase SQL Editor.

-- Eliminar el trigger que causa el error
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- Los perfiles se crean desde la aplicación al crear usuarios desde /admin/users
-- Para usuarios creados manualmente en Supabase Dashboard, ejecutar después:
-- INSERT INTO profiles (id, role) VALUES ('<uuid-del-usuario>', 'admin') ON CONFLICT (id) DO UPDATE SET role = 'admin';
