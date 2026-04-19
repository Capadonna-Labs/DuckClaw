"""
Registro interno de casos PQRSD en la bóveda DuckDB (CRM simulado).

Genera radicado MDE-YYYYMMDD-NNNN e inserta en pqrsd_assistant.radicacion_crm.
Las escrituras van por la cola db-writer cuando el handle es RO (mismo patrón que radicacion_perfil).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator, model_validator

TOOL_NAME = "pqrsd_registrar_radicacion_crm"


def _infer_user_id_for_writer(db_path: str) -> str:
    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def _enqueue_write(
    db: Any,
    *,
    sql: str,
    params: list[Any] | None = None,
    tenant_id: str = "default",
) -> tuple[bool, str | None]:
    path = str(getattr(db, "_path", "") or "").strip()
    if not path or path == ":memory:":
        return False, "Sin ruta de base de datos."
    ro = bool(getattr(db, "_read_only", False))
    if not ro:
        try:
            stmt = sql.strip()
            pl = list(params or [])
            if pl:
                db.execute(stmt, pl)
            else:
                db.execute(stmt)
            return True, None
        except Exception as e:
            return False, str(e)[:500]
    from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync

    resolved = str(Path(path).expanduser().resolve())
    uid = _infer_user_id_for_writer(resolved)
    released_ro = False
    resu = getattr(db, "resume_readonly_file_handle", None)
    try:
        if ro:
            susp = getattr(db, "suspend_readonly_file_handle", None)
            if callable(susp) and callable(resu):
                susp()
                released_ro = True
        task_id = enqueue_duckdb_write_sync(
            db_path=resolved,
            query=sql.strip(),
            params=list(params or []),
            user_id=uid,
            tenant_id=tenant_id,
        )
        poll_to = 20.0 if released_ro else 5.0
        st = poll_task_status_sync(task_id, timeout_sec=poll_to)
        if st is None:
            return False, "timeout esperando db-writer"
        if st.status != "success":
            return False, (st.detail or "db-writer failed")[:500]
        return True, None
    except Exception as e:
        return False, str(e)[:500]
    finally:
        if released_ro and callable(resu):
            try:
                resu()
            except Exception:
                pass


def _parse_scalar_count(raw: str) -> int:
    if not raw or not str(raw).strip():
        return 0
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\b(\d+)\b", str(raw))
        return int(m.group(1)) if m else 0
    if not data:
        return 0
    row = data[0]
    if isinstance(row, dict):
        v = next(iter(row.values()), 0)
        return int(v) if str(v).isdigit() else 0
    return 0


def _count_today(db: Any, schema: str, day: str) -> int:
    """Cuenta radicados del día para secuencia monótona (best-effort)."""
    if not re.fullmatch(r"[0-9]{8}", day):
        day = datetime.now().strftime("%Y%m%d")
    like = f"MDE-{day}-%"
    q = (
        f"SELECT COUNT(*)::BIGINT AS c FROM {schema}.radicacion_crm "
        f"WHERE radicado LIKE '{like}'"
    )
    raw = db.query(q)
    return _parse_scalar_count(raw)


def _radicado_exists(db: Any, schema: str, rid: str) -> bool:
    if not re.match(r"^MDE-[0-9]{8}-[0-9]{4}$", rid):
        return True
    q = f"SELECT 1 AS x FROM {schema}.radicacion_crm WHERE radicado = '{rid}' LIMIT 1"
    raw = db.query(q)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return bool(str(raw).strip())
    return len(data) > 0


def _alloc_radicado(db: Any, schema: str) -> str:
    day = datetime.now().strftime("%Y%m%d")
    n = _count_today(db, schema, day) + 1
    for _ in range(50):
        rid = f"MDE-{day}-{n:04d}"
        if not _radicado_exists(db, schema, rid):
            return rid
        n += 1
    return f"MDE-{day}-{datetime.now().strftime('%H%M%S')}"


class RadicacionCrmInput(BaseModel):
    consentimiento_tratamiento_datos: bool = Field(
        ...,
        description="true solo si el ciudadano autorizó explícitamente registrar el caso en la bóveda.",
    )
    modo: str = Field(
        ...,
        description="identificada o anonima",
        pattern="^(identificada|anonima)$",
    )
    tipo_solicitud: str = Field(
        ...,
        description="peticion, queja, reclamo, sugerencia o denuncia (texto corto).",
    )
    resumen_tecnico: str = Field(
        ...,
        description="Resumen formal administrativo del caso (sin inventar hechos no dichos por el usuario).",
        min_length=20,
    )
    dependencia_asignada: str = Field(
        ...,
        description="Secretaría o dependencia competente inferida (p. ej. Secretaría de Movilidad).",
    )
    prioridad: str = Field(
        default="Media",
        description="Baja, Media o Alta según urgencia.",
    )
    ubicacion: str | None = Field(None, description="Si aplica al caso físico.")
    fecha_hecho: str | None = Field(None, description="Fecha relativa al hecho, si aplica.")
    nombre_contacto: str | None = None
    telefono: str | None = None
    correo: str | None = None
    telegram_chat_id: str = Field(
        default="",
        description="Inyectado por el gateway desde Telegram si está vacío.",
    )

    @field_validator("modo", "tipo_solicitud", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("prioridad", mode="before")
    @classmethod
    def _norm_prioridad(cls, v: object) -> str:
        if not isinstance(v, str):
            return "Media"
        t = v.strip().lower()
        if t in ("baja", "media", "alta"):
            return t.capitalize()
        return "Media"

    @model_validator(mode="after")
    def _validate(self) -> RadicacionCrmInput:
        if not self.consentimiento_tratamiento_datos:
            raise ValueError("Se requiere consentimiento_tratamiento_datos=True.")
        return self


def get_tools(db: Any, schema: str, spec: Any) -> list[Any]:
    del spec

    ddl = f"""
CREATE TABLE IF NOT EXISTS {schema}.radicacion_crm (
    radicado VARCHAR PRIMARY KEY,
    telegram_chat_id VARCHAR NOT NULL,
    modo VARCHAR NOT NULL,
    tipo_solicitud VARCHAR NOT NULL,
    resumen_tecnico VARCHAR NOT NULL,
    dependencia_asignada VARCHAR NOT NULL,
    prioridad VARCHAR NOT NULL DEFAULT 'Media',
    ubicacion VARCHAR,
    fecha_hecho DATE,
    nombre_contacto VARCHAR,
    telefono VARCHAR,
    correo VARCHAR,
    consentimiento_tratamiento_datos BOOLEAN NOT NULL,
    estado VARCHAR DEFAULT 'Pendiente',
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

    def _run(
        consentimiento_tratamiento_datos: bool,
        modo: str,
        tipo_solicitud: str,
        resumen_tecnico: str,
        dependencia_asignada: str,
        prioridad: str = "Media",
        ubicacion: str | None = None,
        fecha_hecho: str | None = None,
        nombre_contacto: str | None = None,
        telefono: str | None = None,
        correo: str | None = None,
        telegram_chat_id: str = "",
    ) -> str:
        inp = RadicacionCrmInput(
            consentimiento_tratamiento_datos=consentimiento_tratamiento_datos,
            modo=modo,
            tipo_solicitud=tipo_solicitud,
            resumen_tecnico=resumen_tecnico,
            dependencia_asignada=dependencia_asignada,
            prioridad=prioridad,
            ubicacion=ubicacion,
            fecha_hecho=fecha_hecho,
            nombre_contacto=nombre_contacto,
            telefono=telefono,
            correo=correo,
            telegram_chat_id=telegram_chat_id,
        )
        cid = (inp.telegram_chat_id or "").strip()
        if not cid:
            return json.dumps(
                {"error": "Falta telegram_chat_id (el gateway debería inyectarlo desde el chat)."},
                ensure_ascii=False,
            )

        ok_ddl, err_ddl = _enqueue_write(db, sql=ddl)
        if not ok_ddl:
            return json.dumps({"error": err_ddl or "DDL falló"}, ensure_ascii=False)

        radicado = _alloc_radicado(db, schema)
        sql = f"""
INSERT INTO {schema}.radicacion_crm (
    radicado, telegram_chat_id, modo, tipo_solicitud, resumen_tecnico,
    dependencia_asignada, prioridad, ubicacion, fecha_hecho,
    nombre_contacto, telefono, correo, consentimiento_tratamiento_datos
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
        params: list[Any] = [
            radicado,
            cid,
            str(inp.modo),
            str(inp.tipo_solicitud).strip()[:200],
            str(inp.resumen_tecnico).strip(),
            str(inp.dependencia_asignada).strip()[:300],
            str(inp.prioridad),
            (inp.ubicacion or "").strip() or None,
            (inp.fecha_hecho or "").strip() or None,
            (inp.nombre_contacto or "").strip() or None,
            (inp.telefono or "").strip() or None,
            (inp.correo or "").strip() or None,
            True,
        ]
        ok, err = _enqueue_write(db, sql=sql, params=params)
        if not ok:
            return json.dumps({"error": err or "insert falló"}, ensure_ascii=False)
        return json.dumps(
            {
                "status": "registered",
                "radicado": radicado,
                "telegram_chat_id": cid,
                "dependencia_asignada": str(inp.dependencia_asignada).strip(),
                "prioridad": str(inp.prioridad),
            },
            ensure_ascii=False,
        )

    return [
        StructuredTool.from_function(
            name=TOOL_NAME,
            description=(
                "Registra en la bóveda DuckDB (tabla pqrsd_assistant.radicacion_crm) un caso PQRSD con "
                "radicado interno formato MDE-YYYYMMDD-NNNN, estado Pendiente y dependencia asignada. "
                "Requiere consentimiento explícito. Úsalo cuando ya tengas resumen técnico y datos mínimos; "
                "no sustituye el radicado oficial del portal web de la Alcaldía. "
                "En tu respuesta al ciudadano, incluye obligatoriamente el valor exacto del campo `radicado` "
                "devuelto en JSON (línea: Radicado interno: MDE-…)."
            ),
            func=_run,
            args_schema=RadicacionCrmInput,
        )
    ]
