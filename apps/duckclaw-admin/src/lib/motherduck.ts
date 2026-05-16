/**
 * Cliente DuckDB local (archivo .duckdb) para rutas API que no pasan por el Gateway.
 *
 * Misma bóveda que PQRSD-Assistant vía DUCKCLAW_PQRSD_ASSISTANT_DB_PATH.
 * No abrir el mismo archivo en escritura concurrente desde otro proceso (Gateway, db-writer)
 * sin coordinación; en producción preferir lecturas/escrituras vía API Gateway.
 */
import fs from 'fs';
import path from 'path';
import duckdb from 'duckdb';

import { resolvePqrsAssistantDuckDbPath } from '@/lib/crm/config';

let _database: duckdb.Database | null = null;
let _connection: duckdb.Connection | null = null;

function getConnection(): duckdb.Connection {
  if (_connection) {
    return _connection;
  }
  const dbPath = resolvePqrsAssistantDuckDbPath();
  const dir = path.dirname(dbPath);
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch {
    // ignore
  }
  _database = new duckdb.Database(dbPath);
  _connection = _database.connect();
  return _connection;
}

function allAsync<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T[]> {
  const conn = getConnection();
  return new Promise((resolve, reject) => {
    const cb = (err: Error | null, rows: unknown) => {
      if (err) {
        reject(err);
      } else {
        resolve((rows as T[]) ?? []);
      }
    };
    const c = conn as unknown as {
      all: (sql: string, ...args: unknown[]) => void;
    };
    if (params && params.length > 0) {
      c.all(sql, ...params, cb);
    } else {
      c.all(sql, cb);
    }
  });
}

function runAsync(sql: string, params?: unknown[]): Promise<void> {
  const conn = getConnection();
  return new Promise((resolve, reject) => {
    const cb = (err: Error | null) => {
      if (err) {
        reject(err);
      } else {
        resolve();
      }
    };
    const c = conn as unknown as {
      run: (sql: string, ...args: unknown[]) => void;
    };
    if (params && params.length > 0) {
      c.run(sql, ...params, cb);
    } else {
      c.run(sql, cb);
    }
  });
}

/**
 * Ejecuta SQL de lectura; retorna filas.
 */
export async function query<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T[]> {
  return allAsync<T>(sql, params);
}

/**
 * Una fila o null.
 */
export async function queryOne<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T | null> {
  const rows = await query<T>(sql, params);
  return rows[0] ?? null;
}

/**
 * Mutación sin resultado tabular.
 */
export async function execute(
  sql: string,
  params?: unknown[]
): Promise<number> {
  await runAsync(sql, params);
  return 0;
}

const SCHEMA = 'pqrsd_crm';
const TICKETS = `${SCHEMA}.tickets`;
const SECRETARIAS = `${SCHEMA}.secretarias`;

let schemaInitialized = false;

export async function ensureSchema(): Promise<void> {
  if (schemaInitialized) {
    return;
  }
  try {
    await runAsync(`CREATE SCHEMA IF NOT EXISTS ${SCHEMA}`);

    await runAsync(`
      CREATE TABLE IF NOT EXISTS ${TICKETS} (
        id_ticket VARCHAR PRIMARY KEY,
        numero_radicado VARCHAR NOT NULL,
        id_secretaria VARCHAR NOT NULL DEFAULT 'sec-salud',
        nombre_ciudadano VARCHAR NOT NULL DEFAULT 'Ciudadano Anónimo',
        documento_ciudadano VARCHAR,
        email_ciudadano VARCHAR,
        telefono_ciudadano VARCHAR,
        tipo_solicitud VARCHAR NOT NULL DEFAULT 'Peticion',
        asunto VARCHAR DEFAULT 'Solicitud PQRSD',
        contenido_raw TEXT NOT NULL,
        resumen_ia TEXT,
        respuesta_sugerida TEXT,
        estado VARCHAR NOT NULL DEFAULT 'Pendiente',
        canal_origen VARCHAR NOT NULL DEFAULT 'Email',
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_limite TIMESTAMP,
        fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    for (const col of ['documento_ciudadano', 'telefono_ciudadano'] as const) {
      try {
        await runAsync(`ALTER TABLE ${TICKETS} ADD COLUMN ${col} VARCHAR`);
      } catch {
        // ya existe
      }
    }

    await runAsync(`
      CREATE TABLE IF NOT EXISTS ${SECRETARIAS} (
        id_secretaria VARCHAR PRIMARY KEY,
        nombre VARCHAR NOT NULL,
        color_identificador VARCHAR NOT NULL DEFAULT '#0057B8'
      )
    `);

    const existingSecretarias = await query<{ cnt: bigint | number }>(
      `SELECT COUNT(*)::BIGINT AS cnt FROM ${SECRETARIAS}`
    );
    const count = Number(existingSecretarias[0]?.cnt ?? 0);
    if (count === 0) {
      await runAsync(`
        INSERT INTO ${SECRETARIAS} (id_secretaria, nombre, color_identificador) VALUES
          ('sec-salud',      'Secretaría de Salud',                '#0057B8'),
          ('sec-educacion',  'Secretaría de Educación',            '#00875A'),
          ('sec-movilidad',  'Secretaría de Movilidad',            '#D97706'),
          ('sec-cultura',    'Secretaría de Cultura',              '#7C3AED'),
          ('sec-desarrollo', 'Secretaría de Desarrollo Económico', '#DC2626')
      `);
    }

    schemaInitialized = true;
    console.log('[DuckDB local] Schema pqrsd_crm verificado/creado');
  } catch (err) {
    console.error('[DuckDB local] Error al crear schema:', err);
    throw err;
  }
}
