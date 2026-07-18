"""Report Engine tool bridges — templates, instances, sections (transversal)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool


def _hub_db_path() -> str:
    from duckclaw.gateway_db import get_gateway_db_path

    path = (get_gateway_db_path() or "").strip()
    if path:
        return path
    raise RuntimeError("No hay ruta DuckDB del gateway para Report Engine.")


def _open_hub_db() -> Any:
    """Reutiliza la conexión RW del worker si es el mismo hub (evita lock RO+RW)."""
    from duckclaw.forge.skills.report_engine_hub_context import get_report_engine_hub_db
    from duckclaw.state_delta_vault import _same_vault_db_path

    hub_path = _hub_db_path()
    reuse = get_report_engine_hub_db()
    if reuse is not None:
        rpath = str(getattr(reuse, "_path", "") or "").strip()
        if rpath and _same_vault_db_path(rpath, hub_path):
            return reuse

    from duckclaw import DuckClaw

    return DuckClaw(hub_path, read_only=True)


def _hub_db_is_owned(db: Any) -> bool:
    """True solo si abrimos una conexión efímera (no la del worker)."""
    from duckclaw.forge.skills.report_engine_hub_context import get_report_engine_hub_db

    reuse = get_report_engine_hub_db()
    return reuse is None or reuse is not db


def _close_hub_db_if_owned(db: Any | None) -> None:
    if db is None or not _hub_db_is_owned(db):
        return
    try:
        db.close()
    except Exception:
        pass


def _session_scope() -> tuple[str, str, str]:
    from duckclaw.forge.skills.knowledge_tool_context import (
        get_knowledge_tool_project_id,
        get_knowledge_tool_tenant_id,
        get_session_actor_email,
    )

    return (
        get_knowledge_tool_tenant_id(),
        get_session_actor_email(),
        get_knowledge_tool_project_id(),
    )


def _session_conversation_id() -> str:
    from duckclaw.forge.skills.knowledge_tool_context import get_session_chat_id

    return get_session_chat_id()


def _image_roots_for_tenant(tenant_id: str, *, output_roots: list[Path]) -> list[Path]:
    """Raíces donde el render puede leer imágenes: vault del tenant + OUTPUT."""
    from duckclaw.vaults import user_vault_dir

    roots: list[Path] = []
    try:
        roots.append(user_vault_dir(tenant_id).resolve())
    except Exception:
        pass
    roots.extend(output_roots)
    return list(dict.fromkeys(roots))


def _tenant_report_template_root(tenant_id: str) -> Path | None:
    """Storage privado para plantillas framework; no debe aparecer en Drive/OUTPUT."""
    from duckclaw.vaults import user_vault_dir

    try:
        return user_vault_dir(tenant_id).resolve() / "report_engine"
    except Exception:
        return None


def _apply_report_command_inline(db: Any, body: dict[str, Any]) -> None:
    from duckclaw.write_command_handlers import dispatch_command

    ensure = getattr(db, "_ensure_python_exec_connection", None)
    if callable(ensure):
        ensure()
    con = getattr(db, "_con", None)
    if con is None:
        raise RuntimeError("Sin conexión DuckDB activa para Report Engine inline")
    con.execute("BEGIN TRANSACTION")
    try:
        dispatch_command(con, body)
        con.execute("COMMIT")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise


def _dispatch_write(payload: dict[str, Any]) -> None:
    """Encola comando tipado y espera confirmación del db-writer antes de continuar."""
    from duckclaw.db_write_fire_and_forget import wait_write_task, write_poll_timeout_sec
    from duckclaw.db_write_queue import enqueue_or_apply_duckdb_write_sync
    from duckclaw.spawn_profile import spawn_inline_writes_enabled
    from duckclaw.state_delta_vault import _same_vault_db_path

    tenant_id, actor_email, _ = _session_scope()
    task_id = str(uuid.uuid4())
    body = {
        "task_id": task_id,
        "tenant_id": tenant_id,
        "actor_email": actor_email,
        **payload,
    }
    hub_path = _hub_db_path()
    reuse = None
    try:
        from duckclaw.forge.skills.report_engine_hub_context import get_report_engine_hub_db

        reuse = get_report_engine_hub_db()
    except Exception:
        reuse = None

    same_hub_open = bool(
        reuse is not None
        and _same_vault_db_path(str(getattr(reuse, "_path", "") or ""), hub_path)
    )

    if spawn_inline_writes_enabled() and same_hub_open and reuse is not None:
        _apply_report_command_inline(reuse, body)
        return

    released = False
    if same_hub_open and reuse is not None and not spawn_inline_writes_enabled():
        release = getattr(reuse, "release_file_handle_for_external_writer", None)
        if callable(release):
            try:
                release()
                released = True
            except Exception:
                released = False

    try:
        enqueue_or_apply_duckdb_write_sync(
            db_path=hub_path,
            command=body,
            user_id=actor_email,
            tenant_id=tenant_id,
        )
        if spawn_inline_writes_enabled():
            return
        # DUCKCLAW_WRITE_POLL_SEC=0 es fire-and-forget para chat/gateway.
        # Report Engine hace read-after-write (_ensure_instance_readable): sin poll
        # el create "falla" aunque el db-writer persista segundos después.
        poll_sec = write_poll_timeout_sec()
        if poll_sec <= 0:
            poll_sec = 30.0
        status = wait_write_task(task_id, timeout_sec=poll_sec)
        if status is None:
            raise RuntimeError(
                "Timeout esperando confirmación del db-writer. "
                "Revisa que DuckClaw-DB-Writer esté activo (pm2) o habilita escrituras inline."
            )
        if status.status != "success":
            detail = (status.detail or "db-writer rechazó el comando").strip()
            raise RuntimeError(detail)
    finally:
        if released and reuse is not None:
            resume = getattr(reuse, "resume_file_handle", None)
            if callable(resume):
                try:
                    resume()
                except Exception:
                    pass


def list_report_templates(limit: int = 50) -> str:
    """Lista plantillas de informe visibles para el tenant y actor actual."""
    from duckclaw.report_engine.admin_report_read import list_report_templates as _list

    tenant_id, actor_email, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        rows = _list(db, tenant_id=tenant_id, actor_email=actor_email, limit=limit)
        return json.dumps(
            {
                "templates": rows,
                "count": len(rows),
                "hint": (
                    "Sin plantillas: en Chat pide «registra mi plantilla Word del vault» "
                    "o usa Entregables en Productividad (nuevo informe)."
                    if not rows
                    else ""
                ),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        _close_hub_db_if_owned(db)


def register_report_template(
    template_docx_path: str,
    name: str,
    description: str = "",
    visibility: str = "private",
    template_id: str = "",
) -> str:
    """Analiza un .docx en el vault y registra una plantilla de informe (secciones Jinja o Heading)."""
    from duckclaw.forge.rag.knowledge_paths import resolve_readable_document_path
    from duckclaw.report_engine.analyzer import analyze_docx_template

    try:
        source = resolve_readable_document_path(relative_path=template_docx_path)
        analysis = analyze_docx_template(source)
        tid = (template_id or "").strip() or f"rtpl_{uuid.uuid4().hex[:10]}"
        from duckclaw.report_engine.analyzer import normalize_analyzer_mode_for_storage

        storage_mode = normalize_analyzer_mode_for_storage(str(analysis.get("analyzer_mode") or "jinja"))
        _dispatch_write(
            {
                "command_type": "upsert_report_template",
                "template_id": tid,
                "name": (name or tid).strip(),
                "description": (description or "").strip(),
                "template_uri": str(source),
                "section_schema": analysis.get("sections") or [],
                "analyzer_mode": storage_mode,
                "visibility": (visibility or "private").strip(),
            }
        )
        return json.dumps(
            {
                "template_id": tid,
                "name": name,
                "section_count": len(analysis.get("sections") or []),
                "sections": analysis.get("sections") or [],
                "tables": analysis.get("tables") or [],
                "fields_in_tables": analysis.get("fields_in_tables", 0),
                "analyzer_mode": analysis.get("analyzer_mode"),
                "storage_analyzer_mode": storage_mode,
                "warning": analysis.get("warning"),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _missing_instance_error(instance_id: str) -> str:
    from duckclaw.report_engine.admin_report_read import diagnose_missing_instance

    tenant_id, _, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        detail = diagnose_missing_instance(
            db,
            instance_id=(instance_id or "").strip(),
            tenant_id=tenant_id,
        )
        return json.dumps(
            {
                "error": "Instancia no encontrada",
                "detail": detail,
                "instance_id": (instance_id or "").strip(),
                "tenant_id": tenant_id,
                "hint": (
                    "No es caché: o el write no llegó a esta DuckDB, o el tenant de sesión "
                    "no coincide. Verifica en Productividad → Entregables o "
                    "get_report_status con el mismo instance_id."
                ),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "error": "Instancia no encontrada",
                "instance_id": (instance_id or "").strip(),
                "tenant_id": tenant_id,
                "detail": str(exc),
            },
            ensure_ascii=False,
        )
    finally:
        _close_hub_db_if_owned(db)


def _ensure_instance_readable(instance_id: str) -> None:
    """Tras create/patch: falla si la sesión no puede leer la fila (DB/tenant)."""
    from duckclaw.report_engine.admin_report_read import (
        diagnose_missing_instance,
        get_report_instance,
    )

    tenant_id, _, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        if get_report_instance(db, instance_id=instance_id, tenant_id=tenant_id):
            return
        raise RuntimeError(
            diagnose_missing_instance(db, instance_id=instance_id, tenant_id=tenant_id)
        )
    finally:
        _close_hub_db_if_owned(db)


def create_report_instance(
    template_id: str,
    title: str,
    period_key: str = "",
    project_id: str = "",
    instance_id: str = "",
) -> str:
    """Crea un borrador desde plantilla. Solo requiere template_id + title.

    No preguntes periodo: identity = instance_id. period_key se ignora (legacy).
    """
    try:
        tenant_id, actor_email, ctx_project = _session_scope()
        pid = (project_id or ctx_project or "").strip()
        iid = (instance_id or "").strip() or f"rpt_{uuid.uuid4().hex[:10]}"
        clean_title = (title or "Documento").strip() or "Documento"
        _dispatch_write(
            {
                "command_type": "create_report_instance",
                "instance_id": iid,
                "template_id": (template_id or "").strip(),
                "title": clean_title,
                "period_key": "",
                "project_id": pid,
                "conversation_id": _session_conversation_id(),
            }
        )
        _ensure_instance_readable(iid)
        return json.dumps(
            {
                "instance_id": iid,
                "template_id": template_id,
                "title": clean_title,
                "project_id": pid,
                "status": "draft",
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def list_report_instances(limit: int = 20) -> str:
    """Lista documentos (instancias) en curso del usuario para reanudar en vez de crear.

    Úsalo ANTES de create: si ya hay un borrador de esta conversación, reanúdalo
    (patch + render con el mismo instance_id). Crea uno nuevo solo si el usuario
    pide explícitamente otro documento.
    """
    from duckclaw.report_engine.admin_report_read import (
        list_report_instances as _list_instances,
    )

    tenant_id, actor_email, project_id = _session_scope()
    conversation_id = _session_conversation_id()
    db = None
    try:
        db = _open_hub_db()
        rows = _list_instances(
            db,
            tenant_id=tenant_id,
            actor_email=actor_email,
            project_id=project_id,
            limit=max(1, min(int(limit or 20), 50)),
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        _close_hub_db_if_owned(db)

    items = [
        {
            "instance_id": r.get("instance_id"),
            "title": r.get("title"),
            "template_id": r.get("template_id"),
            "template_name": r.get("template_name"),
            "status": r.get("status"),
            "progress": (r.get("progress") or {}).get("completion_percent"),
            "updated_at": r.get("updated_at"),
            "same_conversation": bool(
                conversation_id and str(r.get("conversation_id") or "") == conversation_id
            ),
        }
        for r in rows
    ]
    # Sugerencia de reanudación: primero de esta conversación, si no el más reciente.
    resume = next((i["instance_id"] for i in items if i["same_conversation"]), None)
    if resume is None and items:
        resume = items[0]["instance_id"]
    return json.dumps(
        {"instances": items, "resume_suggestion": resume, "count": len(items)},
        ensure_ascii=False,
    )


def _blank_template_id(tenant_id: str, actor_email: str) -> str:
    import hashlib

    seed = f"{(tenant_id or 'default').strip().lower()}:{(actor_email or 'system').strip().lower()}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"rtpl_blank_{digest}"


def create_blank_document(
    title: str,
    instance_id: str = "",
    image_paths: str = "",
    intro: str = "",
) -> str:
    """Crea un documento Word desde CERO (sin plantilla previa): texto + imágenes.

    Usa una plantilla en blanco reutilizable con huecos de texto (intro, texto_1..3,
    cierre) e imagen (imagen_1..3). Pasa image_paths (rutas de [IMAGENES_ADJUNTAS],
    separadas por ; o salto de línea) para colocarlas de una vez. Opcional: intro.
    Luego puedes patch_report_section más texto y render_report_instance.
    """
    from duckclaw.forge.rag.knowledge_paths import knowledge_output_roots
    from duckclaw.report_engine.blank_template import (
        BLANK_SECTION_SCHEMA,
        ensure_blank_template_seed,
    )

    try:
        tenant_id, actor_email, _ = _session_scope()
        roots = knowledge_output_roots()
        if not roots:
            return json.dumps(
                {"error": "DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS no configurado"},
                ensure_ascii=False,
            )
        template_root = _tenant_report_template_root(tenant_id)
        if template_root is None:
            return json.dumps(
                {"error": "No se pudo resolver el vault privado del tenant"},
                ensure_ascii=False,
            )
        seed_path = ensure_blank_template_seed(template_root)
        tid = _blank_template_id(tenant_id, actor_email)
        _dispatch_write(
            {
                "command_type": "upsert_report_template",
                "template_id": tid,
                "name": "Documento en blanco",
                "description": "Plantilla framework: texto + imágenes desde cero.",
                "template_uri": str(seed_path),
                "section_schema": BLANK_SECTION_SCHEMA,
                "analyzer_mode": "jinja",
                "visibility": "private",
            }
        )
        create_raw = create_report_instance(
            template_id=tid,
            title=(title or "Documento").strip() or "Documento",
            instance_id=instance_id,
        )
        created = json.loads(create_raw)
        if created.get("error"):
            return create_raw
        iid = str(created.get("instance_id") or "")
        created["template_id"] = tid
        created["text_sections"] = [
            s["id"] for s in BLANK_SECTION_SCHEMA if s.get("kind") != "image"
        ]
        created["image_sections"] = [
            s["id"] for s in BLANK_SECTION_SCHEMA if s.get("kind") == "image"
        ]

        title_text = (title or "Documento").strip() or "Documento"
        if iid:
            patch_report_section(
                instance_id=iid,
                section_id="titulo",
                content=title_text,
                mode="replace",
                mark_complete=True,
            )

        intro_text = (intro or "").strip()
        if intro_text and iid:
            patch_report_section(
                instance_id=iid,
                section_id="intro",
                content=intro_text,
                mode="replace",
                mark_complete=True,
            )
            created["intro_patched"] = True

        paths = _parse_image_paths_arg(image_paths)
        image_slots = [
            s["id"] for s in BLANK_SECTION_SCHEMA if s.get("kind") == "image"
        ]
        placed: list[dict[str, str]] = []
        for slot, path in zip(image_slots, paths):
            patch_raw = patch_report_image(
                instance_id=iid, section_id=slot, image_path=path
            )
            patched = json.loads(patch_raw)
            if patched.get("error"):
                created["image_patch_error"] = patched
                break
            placed.append({"section_id": slot, "image_path": path})
        if placed:
            created["images_placed"] = placed
        created["hint"] = (
            "Si faltan textos: patch_report_section (texto_1..3, cierre). "
            "Si faltan imágenes: patch_report_image. Luego render_report_instance."
        )
        return json.dumps(created, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _parse_image_paths_arg(raw: str) -> list[str]:
    """Acepta JSON list, rutas separadas, o líneas tipo ``imagen_1 → /path.png``."""
    import re

    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(p).strip() for p in parsed if str(p).strip()]
        except Exception:
            pass

    parts: list[str] = []
    path_re = re.compile(
        r"(/[^\s;]+?\.(?:png|jpe?g|webp|gif)|"
        r"[A-Za-z]:\\[^\s;]+?\.(?:png|jpe?g|webp|gif))",
        re.IGNORECASE,
    )
    for chunk in text.replace(";", "\n").splitlines():
        cleaned = chunk.strip().strip("'\"")
        if not cleaned:
            continue
        # «imagen_1 → /vault/.../a.png»
        if "→" in cleaned or "->" in cleaned:
            cleaned = cleaned.replace("→", "->").split("->", 1)[-1].strip().strip("'\"")
        match = path_re.search(cleaned)
        if match:
            parts.append(match.group(0))
            continue
        if cleaned.startswith("/") or (len(cleaned) > 2 and cleaned[1] == ":"):
            parts.append(cleaned)
    # Dedup preserve order
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _resolve_patchable_image_path(raw_path: str, *, tenant_id: str) -> str:
    """Valida que el archivo existe y está bajo vault del tenant u OUTPUT."""
    from duckclaw.forge.rag.knowledge_paths import knowledge_output_roots

    path = (raw_path or "").strip().strip("'\"")
    if not path:
        raise ValueError("image_path vacío")
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_file():
        raise ValueError(f"Imagen no accesible: {path}")
    roots = _image_roots_for_tenant(tenant_id, output_roots=knowledge_output_roots())
    ok = any(
        candidate == root.resolve() or root.resolve() in candidate.parents for root in roots
    )
    if not ok:
        raise ValueError(
            f"Imagen «{path}» fuera del vault/inbound del tenant u OUTPUT. "
            "Reenvía la imagen por el chat."
        )
    return str(candidate)


def patch_report_image(
    instance_id: str,
    section_id: str,
    image_path: str,
) -> str:
    """Coloca una imagen (por su path del vault/chat) en una sección kind=image.

    image_path: ruta absoluta que llegó por el chat (adjunto) o relativa bajo OUTPUT.
    La imagen se inserta como InlineImage en el render, conservando el layout Word.
    """
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
    )

    tenant_id, actor_email, _ = _session_scope()
    try:
        path = _resolve_patchable_image_path(image_path, tenant_id=tenant_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    db = None
    try:
        db = _open_hub_db()
        instance = get_report_instance(
            db, instance_id=(instance_id or "").strip(), tenant_id=tenant_id
        )
        if not instance:
            return _missing_instance_error(instance_id)
        if not actor_can_access_instance(db, instance=instance, actor_email=actor_email):
            return json.dumps({"error": "Acceso denegado"}, ensure_ascii=False)
        entry = (instance["state"].get("sections") or {}).get((section_id or "").strip())
        if not isinstance(entry, dict):
            valid = [
                sid
                for sid, e in (instance["state"].get("sections") or {}).items()
                if isinstance(e, dict) and str(e.get("kind") or "") == "image"
            ]
            return json.dumps(
                {
                    "error": f"Sección desconocida: {section_id}",
                    "image_sections": valid,
                    "hint": (
                        "Solo plantillas con kind=image (p. ej. create_blank_document). "
                        "El informe mensual corporativo no tiene huecos de imagen."
                    ),
                },
                ensure_ascii=False,
            )
        if str(entry.get("kind") or "") != "image":
            return json.dumps(
                {
                    "error": (
                        f"La sección «{section_id}» es de texto; usa patch_report_section. "
                        "patch_report_image solo aplica a secciones kind=image "
                        "(create_blank_document → imagen_1..3)."
                    )
                },
                ensure_ascii=False,
            )
    finally:
        _close_hub_db_if_owned(db)

    # El path se guarda como content (replace); el render lo convierte en InlineImage.
    return patch_report_section(
        instance_id=instance_id,
        section_id=section_id,
        content=path,
        mode="replace",
        mark_complete=True,
    )


def get_report_status(instance_id: str) -> str:
    """Devuelve progreso del informe: secciones completas, parciales y faltantes."""
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
        get_report_template,
    )
    from duckclaw.report_engine.state import summarize_status

    tenant_id, actor_email, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        instance = get_report_instance(db, instance_id=(instance_id or "").strip(), tenant_id=tenant_id)
        if not instance:
            return _missing_instance_error(instance_id)
        if not actor_can_access_instance(db, instance=instance, actor_email=actor_email):
            return json.dumps({"error": "Acceso denegado"}, ensure_ascii=False)
        template = get_report_template(db, template_id=str(instance["template_id"]), tenant_id=tenant_id)
        schema = (template or {}).get("section_schema") or []
        summary = summarize_status(instance["state"], schema)
        return json.dumps(
            {
                "instance_id": instance["instance_id"],
                "title": instance["title"],
                "status": instance["status"],
                **summary,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        _close_hub_db_if_owned(db)


def patch_report_section(
    instance_id: str,
    section_id: str,
    content: str,
    mode: str = "append",
    mark_complete: bool = False,
) -> str:
    """Añade o reemplaza contenido en una sección del informe en construcción."""
    from duckclaw.report_engine.admin_report_read import get_report_instance, get_report_template
    from duckclaw.report_engine.state import summarize_status

    try:
        _dispatch_write(
            {
                "command_type": "patch_report_section",
                "instance_id": (instance_id or "").strip(),
                "section_id": (section_id or "").strip(),
                "content": content or "",
                "mode": (mode or "append").strip().lower(),
                "mark_complete": bool(mark_complete),
            }
        )
        tenant_id, _, _ = _session_scope()
        db = None
        progress: dict[str, Any] = {}
        try:
            db = _open_hub_db()
            instance = get_report_instance(
                db, instance_id=(instance_id or "").strip(), tenant_id=tenant_id
            )
            if instance:
                template = get_report_template(
                    db, template_id=str(instance["template_id"]), tenant_id=tenant_id
                )
                schema = (template or {}).get("section_schema") or []
                progress = summarize_status(instance["state"], schema)
        finally:
            _close_hub_db_if_owned(db)

        hint = ""
        raw_content = content or ""
        if "|" in raw_content and "\n" in raw_content:
            hint = (
                "Detecté posible tabla markdown: en celdas Word se aplanará a texto. "
                "Preferible un patch por cada {{ campo }} de la plantilla."
            )
        return json.dumps(
            {
                "instance_id": instance_id,
                "section_id": section_id,
                "mode": mode,
                "mark_complete": mark_complete,
                "status": "updated",
                "progress": progress,
                "hint": hint,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        msg = str(exc)
        payload: dict[str, Any] = {"error": msg}
        if "sección desconocida" in msg.lower() or "Sección desconocida" in msg:
            try:
                tenant_id, _, _ = _session_scope()
                db = _open_hub_db()
                try:
                    instance = get_report_instance(
                        db, instance_id=(instance_id or "").strip(), tenant_id=tenant_id
                    )
                    if instance:
                        template = get_report_template(
                            db, template_id=str(instance["template_id"]), tenant_id=tenant_id
                        )
                        schema = (template or {}).get("section_schema") or []
                        payload["valid_section_ids"] = [
                            str(s.get("id") or "")
                            for s in schema
                            if isinstance(s, dict) and s.get("id")
                        ]
                finally:
                    _close_hub_db_if_owned(db)
            except Exception:
                pass
        return json.dumps(payload, ensure_ascii=False)


def _discover_markdown_relative_path(*, report_title: str) -> str:
    """Busca .md en OUTPUT por tokens del título (sin carpetas de nicho hardcodeadas)."""
    import re

    from duckclaw.forge.rag.knowledge_paths import knowledge_output_roots

    roots = knowledge_output_roots()
    if not roots:
        raise ValueError(
            "No hay DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS. "
            "Indica markdown_relative_path explícitamente."
        )

    title_tokens = {
        tok
        for tok in re.findall(r"[a-zA-Z0-9áéíóúñ]+", (report_title or "").lower())
        if len(tok) >= 3
    }
    if not title_tokens:
        raise ValueError(
            "Indica markdown_relative_path (ruta .md bajo OUTPUT) o markdown_content."
        )

    scored: list[tuple[int, str]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            rel_lower = rel.lower()
            score = sum(6 for tok in title_tokens if tok in rel_lower)
            if score > 0:
                scored.append((score, rel))

    if not scored:
        raise ValueError(
            "No hay .md en OUTPUT que coincida con el título. "
            "Pasa markdown_relative_path o markdown_content explícitos."
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def _read_markdown_for_report(
    *,
    markdown_relative_path: str,
    markdown_content: str,
    report_title: str = "",
) -> tuple[str, str]:
    text = (markdown_content or "").strip()
    if text:
        return text, "inline"

    rel = (markdown_relative_path or "").strip()
    if not rel:
        rel = _discover_markdown_relative_path(report_title=report_title)

    from duckclaw.forge.rag.knowledge_paths import resolve_readable_document_path

    path = resolve_readable_document_path(relative_path=rel)
    return path.read_text(encoding="utf-8", errors="replace").strip(), rel


def _resolve_registered_template_id(
    *,
    template_docx_path: str,
    template_name: str,
    template_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    from duckclaw.report_engine.admin_report_read import list_report_templates as _list

    tid_hint = (template_id or "").strip()
    if tid_hint:
        tenant_id, actor_email, _ = _session_scope()
        db = _open_hub_db()
        try:
            rows = _list(db, tenant_id=tenant_id, actor_email=actor_email, limit=200)
        finally:
            _close_hub_db_if_owned(db)
        for row in rows:
            if str(row.get("template_id")) == tid_hint:
                schema = row.get("section_schema") or []
                return tid_hint, schema if isinstance(schema, list) else []
        raise ValueError(f"Plantilla registrada no encontrada: {tid_hint}")

    docx_name = Path(template_docx_path).name.lower()
    name_hint = (template_name or "").strip().lower()
    tenant_id, actor_email, _ = _session_scope()
    db = _open_hub_db()
    try:
        rows = _list(db, tenant_id=tenant_id, actor_email=actor_email, limit=200)
    finally:
        _close_hub_db_if_owned(db)
    for row in rows:
        uri = str(row.get("template_uri") or "").lower()
        row_name = str(row.get("name") or "").strip().lower()
        if docx_name and uri.endswith(docx_name):
            schema = row.get("section_schema") or []
            return str(row["template_id"]), schema if isinstance(schema, list) else []
        if name_hint and row_name == name_hint:
            schema = row.get("section_schema") or []
            return str(row["template_id"]), schema if isinstance(schema, list) else []
    return "", []


def _primary_section_id(section_schema: list[dict[str, Any]]) -> str:
    preferred = ("resumen_ejecutivo", "body", "contenido", "informe", "resumen")
    ids = [str(s.get("id") or "").strip() for s in section_schema if isinstance(s, dict)]
    for pid in preferred:
        if pid in ids:
            return pid
    return ids[0] if ids else "body"


def generate_report_docx_from_markdown(
    template_docx_path: str,
    report_title: str,
    markdown_relative_path: str = "",
    markdown_content: str = "",
    period_key: str = "",
    template_name: str = "",
    template_id: str = "",
) -> str:
    """One-shot SOLO para plantillas de un solo campo. Multi-campo → patch por sección."""
    try:
        markdown, markdown_source = _read_markdown_for_report(
            markdown_relative_path=markdown_relative_path,
            markdown_content=markdown_content,
            report_title=report_title,
        )
        if not markdown:
            raise ValueError("El markdown está vacío")

        resolved_id, schema = _resolve_registered_template_id(
            template_docx_path=template_docx_path,
            template_name=template_name,
            template_id=template_id,
        )
        if not resolved_id:
            reg_raw = register_report_template(
                template_docx_path=template_docx_path,
                name=(template_name or Path(template_docx_path).stem).strip(),
                template_id=template_id,
            )
            reg = json.loads(reg_raw)
            if reg.get("error"):
                return reg_raw
            resolved_id = str(reg["template_id"])
            schema = reg.get("sections") or []

        schema_list = schema if isinstance(schema, list) else []
        if len(schema_list) > 1:
            ids = [str(s.get("id") or "") for s in schema_list if isinstance(s, dict)]
            return json.dumps(
                {
                    "error": (
                        "Plantilla multi-campo: generate_report_docx_from_markdown no aplica. "
                        "Usa create_report_instance + patch_report_section por cada section_id "
                        "+ render_report_instance."
                    ),
                    "template_id": resolved_id,
                    "section_ids": [i for i in ids if i],
                    "section_count": len(ids),
                },
                ensure_ascii=False,
            )

        create_raw = create_report_instance(
            template_id=resolved_id,
            title=report_title,
        )
        created = json.loads(create_raw)
        if created.get("error"):
            return create_raw
        instance_id = str(created["instance_id"])

        section_id = _primary_section_id(schema_list)
        patch_raw = patch_report_section(
            instance_id=instance_id,
            section_id=section_id,
            content=markdown,
            mode="replace",
            mark_complete=True,
        )
        patched = json.loads(patch_raw)
        if patched.get("error"):
            return patch_raw

        render_raw = render_report_instance(instance_id)
        rendered = json.loads(render_raw)
        if rendered.get("error"):
            return render_raw

        return json.dumps(
            {
                "instance_id": instance_id,
                "template_id": resolved_id,
                "section_id": section_id,
                "title": report_title,
                "markdown_source": markdown_source,
                **rendered,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        payload: dict[str, Any] = {"error": str(exc)}
        msg = str(exc).lower()
        if "markdown" in msg or "output_roots" in msg:
            payload["hint"] = (
                "Pasa markdown_relative_path o markdown_content. "
                "No uses pandoc ni run_sandbox para plantillas."
            )
        if "sección desconocida" in msg:
            payload["hint"] = (
                "Revisa section_schema con list_report_templates "
                "y usa patch_report_section con un section_id válido."
            )
        return json.dumps(payload, ensure_ascii=False)


def render_report_instance(instance_id: str, force: bool = False) -> str:
    """Genera el DOCX del informe desde plantilla + estado actual."""
    from duckclaw.forge.rag.knowledge_paths import knowledge_allowed_roots, knowledge_output_roots
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
        get_report_template,
    )
    from duckclaw.report_engine.render import render_instance_docx_from_uri
    from duckclaw.report_engine.render_validate import (
        assert_ready_to_render,
        assert_template_is_patchable,
    )

    tenant_id, actor_email, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        instance = get_report_instance(db, instance_id=(instance_id or "").strip(), tenant_id=tenant_id)
        if not instance:
            return _missing_instance_error(instance_id)
        if not actor_can_access_instance(db, instance=instance, actor_email=actor_email):
            return json.dumps({"error": "Acceso denegado"}, ensure_ascii=False)
        template = get_report_template(db, template_id=str(instance["template_id"]), tenant_id=tenant_id)
        if not template:
            return json.dumps({"error": "Plantilla no encontrada"}, ensure_ascii=False)

        assert_template_is_patchable(str(template.get("analyzer_mode") or "jinja"))
        schema = template.get("section_schema") or []
        progress = assert_ready_to_render(
            instance["state"],
            schema if isinstance(schema, list) else [],
            force=bool(force),
        )

        roots = knowledge_output_roots()
        if not roots:
            return json.dumps({"error": "DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS no configurado"}, ensure_ascii=False)
        out_root = roots[0]
        private_template_root = _tenant_report_template_root(tenant_id)
        private_roots = [private_template_root] if private_template_root is not None else []
        allowed = list(dict.fromkeys(knowledge_allowed_roots() + roots + private_roots))
        image_roots = _image_roots_for_tenant(tenant_id, output_roots=roots)

        rendered = render_instance_docx_from_uri(
            template_uri=str(template["template_uri"]),
            state_json=json.dumps(instance["state"], ensure_ascii=False),
            output_root=out_root,
            instance_id=str(instance["instance_id"]),
            title=str(instance["title"]),
            period_key=str(instance["period_key"]),
            allowed_roots=allowed,
            image_roots=image_roots,
        )
        unresolved = rendered.get("unresolved_placeholders") or []
        if unresolved and not force:
            return json.dumps(
                {
                    "error": (
                        "Tras el render quedaron placeholders sin resolver. "
                        "Revisa el schema / patches o pasa force=true."
                    ),
                    "unresolved_placeholders": unresolved,
                    "path": rendered.get("path"),
                    "progress": progress,
                },
                ensure_ascii=False,
            )

        status = "ready" if not unresolved else "draft"
        _dispatch_write(
            {
                "command_type": "update_report_instance_render",
                "instance_id": instance["instance_id"],
                "rendered_docx_uri": str(rendered["path"]),
                "status": status,
            }
        )
        try:
            from duckclaw.productivity_artifacts import register_vault_artifact_from_path

            register_vault_artifact_from_path(
                Path(str(rendered["path"])),
                tenant_id=tenant_id,
                owner_email=actor_email,
                source_kind="report_render",
                source_ref=str(instance["instance_id"]),
                title=str(instance["title"]),
            )
        except Exception:
            pass
        return json.dumps(
            {
                **rendered,
                "progress": progress,
                "forced": bool(force),
                "status": status,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        _close_hub_db_if_owned(db)


def register_report_engine_tools(tools_list: list[Any]) -> None:
    tools_list.extend(
        [
            StructuredTool.from_function(
                list_report_templates,
                name="list_report_templates",
                description="Lista plantillas Word de informes registradas para este tenant.",
            ),
            StructuredTool.from_function(
                register_report_template,
                name="register_report_template",
                description=(
                    "Registra una plantilla .docx del vault para el Report Engine. "
                    "Paso 1 del flujo Word corporativo (antes de create_report_instance). "
                    "Detecta secciones por {{ placeholders }} o títulos Heading."
                ),
            ),
            StructuredTool.from_function(
                list_report_instances,
                name="list_report_instances",
                description=(
                    "Lista documentos en curso del usuario (para reanudar en vez de crear). "
                    "ÚSALO ANTES de create/create_blank: si hay un borrador de esta "
                    "conversación (resume_suggestion), reanúdalo con ese instance_id. "
                    "Crea uno nuevo solo si el usuario pide explícitamente otro documento."
                ),
            ),
            StructuredTool.from_function(
                create_report_instance,
                name="create_report_instance",
                description=(
                    "Crea borrador desde plantilla registrada. Args: template_id + title. "
                    "NO pidas periodo/mes: la identidad es instance_id. "
                    "Luego patch_report_section por cada sección faltante."
                ),
            ),
            StructuredTool.from_function(
                create_blank_document,
                name="create_blank_document",
                description=(
                    "Crea un Word desde CERO (sin plantilla previa): huecos de texto e "
                    "imagen. Úsalo cuando el usuario quiere 'un documento con este texto y "
                    "estas imágenes'. Pasa image_paths con las rutas de [IMAGENES_ADJUNTAS] "
                    "(separadas por ; ) e intro opcional. Luego render_report_instance."
                ),
            ),
            StructuredTool.from_function(
                patch_report_image,
                name="patch_report_image",
                description=(
                    "Coloca una imagen adjunta (por su path del chat/vault) en una sección "
                    "kind=image (p. ej. imagen_1). Se inserta como InlineImage en el render, "
                    "conservando el layout. Para texto usa patch_report_section."
                ),
            ),
            StructuredTool.from_function(
                get_report_status,
                name="get_report_status",
                description=(
                    "Muestra qué secciones faltan, están parciales o completas. "
                    "Úsalo antes de proponer contenido o cerrar el informe."
                ),
            ),
            StructuredTool.from_function(
                patch_report_section,
                name="patch_report_section",
                description=(
                    "Actualiza UNA sección/celda de la plantilla (mode append|replace). "
                    "Texto plano por hueco {{ id }} — no pegues tablas markdown ni bloques "
                    "enteros; rellena cada section_id del schema (p. ej. cuerpo, seccion.1). "
                    "La plantilla Word conserva tablas y estilos; tú solo llenas huecos."
                ),
            ),
            StructuredTool.from_function(
                render_report_instance,
                name="render_report_instance",
                description=(
                    "Genera el Word final (docxtpl) como .docx directo en OUTPUT. "
                    "Falla si faltan secciones required o quedan {{ placeholders }}. "
                    "force=true exporta borrador incompleto a propósito. "
                    "Preferir sobre convert_document/pandoc cuando hay plantilla registrada."
                ),
            ),
            StructuredTool.from_function(
                generate_report_docx_from_markdown,
                name="generate_report_docx_from_markdown",
                description=(
                    "ÚLTIMO RECURSO — solo plantillas de UN campo. "
                    "Plantillas multi-campo: create + patch por section_id + render. "
                    "No es pandoc; no sustituye el flujo por sección."
                ),
            ),
        ]
    )
