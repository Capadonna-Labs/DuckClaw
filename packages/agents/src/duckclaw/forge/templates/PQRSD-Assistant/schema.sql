-- Asistente PQRSD: esquema reservado (read-only en runtime típico).
-- Tabla opcional para trazas de orientación si el producto la habilita.
CREATE SCHEMA IF NOT EXISTS pqrsd_assistant;

CREATE TABLE IF NOT EXISTS pqrsd_assistant.orientation_notes (
    id INTEGER PRIMARY KEY,
    topic TEXT,
    summary TEXT,
    source_urls TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Perfil mínimo para radicar PQRSD (misma bóveda; consentimiento explícito en chat).
CREATE TABLE IF NOT EXISTS pqrsd_assistant.radicacion_perfil (
    telegram_chat_id VARCHAR PRIMARY KEY,
    modo VARCHAR NOT NULL,
    tipo_documento VARCHAR,
    numero_documento VARCHAR,
    correo VARCHAR NOT NULL,
    consentimiento_registro_db BOOLEAN NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- CRM interno (GovTech): radicado simulado MDE-YYYYMMDD-NNNN; no reemplaza el portal oficial.
CREATE TABLE IF NOT EXISTS pqrsd_assistant.radicacion_crm (
    radicado VARCHAR PRIMARY KEY,
    telegram_chat_id VARCHAR NOT NULL,
    modo VARCHAR NOT NULL,
    tipo_solicitud VARCHAR NOT NULL,
    resumen_tecnico TEXT NOT NULL,
    dependencia_asignada VARCHAR NOT NULL,
    estado VARCHAR NOT NULL DEFAULT 'Pendiente',
    prioridad VARCHAR NOT NULL DEFAULT 'Media',
    ubicacion TEXT,
    fecha_hecho TEXT,
    nombre_contacto VARCHAR,
    telefono VARCHAR,
    correo VARCHAR,
    consentimiento_tratamiento_datos BOOLEAN NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
