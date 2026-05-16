"""
Persistencia opcional del perfil mínimo para radicar PQRSD en la bóveda DuckDB.

Spec: specs/features/agents-axis/PQRSD_ASSISTANT_MEDELLIN.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator, model_validator

from duckclaw.forge.atoms.pqrsd_radicacion_playwright import emails_match, normalize_document_number

TOOL_NAME = "pqrsd_upsert_radicacion_perfil"


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
    # Worker con manifest read_only=false: el grafo abre DuckClaw en RW en el mismo proceso.
    # Escribir aquí evita el lock con db-writer (otro proceso) mientras el gateway tiene el archivo abierto.
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


class RadicacionPerfilInput(BaseModel):
    modo: str = Field(
        ...,
        description="identificada o anonima",
        pattern="^(identificada|anonima)$",
    )
    consentimiento_registro_db: bool = Field(
        ...,
        description="true solo si el usuario autorizó explícitamente guardar estos datos en la bóveda DuckClaw.",
    )
    correo: str | None = Field(None, description="Correo para verificación en el portal.")
    correo_confirmacion: str | None = Field(None, description="Debe coincidir con correo.")
    tipo_documento: str | None = Field(None, description="Solo modo identificada.")
    numero_documento: str | None = Field(None, description="Solo modo identificada.")
    telegram_chat_id: str = Field(
        default="",
        description="Inyectado por el gateway desde el chat de Telegram si está vacío.",
    )

    @field_validator("modo", mode="before")
    @classmethod
    def _strip_modo(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def _validate(self) -> RadicacionPerfilInput:
        if not self.consentimiento_registro_db:
            raise ValueError("Se requiere consentimiento_registro_db=True tras confirmación explícita en el chat.")
        ce = (self.correo or "").strip()
        c2 = (self.correo_confirmacion or "").strip()
        if not ce or not c2:
            raise ValueError("correo y correo_confirmacion son obligatorios.")
        if not emails_match(ce, c2):
            raise ValueError("correo y correo_confirmacion deben coincidir.")
        if str(self.modo) == "identificada":
            if not (self.tipo_documento or "").strip():
                raise ValueError("tipo_documento es obligatorio para modo identificada.")
            if not (self.numero_documento or "").strip():
                raise ValueError("numero_documento es obligatorio para modo identificada.")
        return self


def get_tools(db: Any, schema: str, spec: Any) -> list[Any]:
    del spec

    ddl = f"""
CREATE TABLE IF NOT EXISTS {schema}.radicacion_perfil (
    telegram_chat_id VARCHAR PRIMARY KEY,
    modo VARCHAR NOT NULL,
    tipo_documento VARCHAR,
    numero_documento VARCHAR,
    correo VARCHAR NOT NULL,
    consentimiento_registro_db BOOLEAN NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

    def _run(
        modo: str,
        consentimiento_registro_db: bool,
        correo: str | None = None,
        correo_confirmacion: str | None = None,
        tipo_documento: str | None = None,
        numero_documento: str | None = None,
        telegram_chat_id: str = "",
    ) -> str:
        inp = RadicacionPerfilInput(
            modo=modo,
            consentimiento_registro_db=consentimiento_registro_db,
            correo=correo,
            correo_confirmacion=correo_confirmacion,
            tipo_documento=tipo_documento,
            numero_documento=numero_documento,
            telegram_chat_id=telegram_chat_id,
        )
        cid = (inp.telegram_chat_id or "").strip()
        if not cid:
            return json.dumps(
                {"error": "Falta telegram_chat_id (el gateway debería inyectarlo desde el chat)."},
                ensure_ascii=False,
            )
        modo_s = str(inp.modo)
        td = (inp.tipo_documento or "").strip() if modo_s == "identificada" else None
        nd = (
            normalize_document_number(inp.numero_documento or "")
            if modo_s == "identificada"
            else None
        )
        em = (inp.correo or "").strip()

        ok_ddl, err_ddl = _enqueue_write(db, sql=ddl)
        if not ok_ddl:
            return json.dumps({"error": err_ddl or "DDL falló"}, ensure_ascii=False)

        sql = f"""
INSERT INTO {schema}.radicacion_perfil (
    telegram_chat_id, modo, tipo_documento, numero_documento, correo,
    consentimiento_registro_db, updated_at
) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (telegram_chat_id) DO UPDATE SET
    modo = excluded.modo,
    tipo_documento = excluded.tipo_documento,
    numero_documento = excluded.numero_documento,
    correo = excluded.correo,
    consentimiento_registro_db = excluded.consentimiento_registro_db,
    updated_at = CURRENT_TIMESTAMP
"""
        params: list[Any] = [cid, modo_s, td, nd, em, True]
        ok, err = _enqueue_write(db, sql=sql, params=params)
        if not ok:
            return json.dumps({"error": err or "upsert falló"}, ensure_ascii=False)
        return json.dumps(
            {
                "status": "saved",
                "telegram_chat_id": cid,
                "modo": modo_s,
            },
            ensure_ascii=False,
        )

    return [
        StructuredTool.from_function(
            name=TOOL_NAME,
            description=(
                "Guarda en la bóveda DuckDB (tabla pqrsd_assistant.radicacion_perfil) los datos mínimos "
                "que el usuario ya proporcionó en el chat para radicar PQRSD, solo con "
                "consentimiento_registro_db=true explícito. Requiere correo y correo_confirmacion iguales; "
                "en modo identificada también tipo y número de documento. El gateway suele rellenar "
                "telegram_chat_id automáticamente."
            ),
            func=_run,
            args_schema=RadicacionPerfilInput,
        )
    ]
