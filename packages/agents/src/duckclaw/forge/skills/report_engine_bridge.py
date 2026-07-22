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


def _output_basename(uri: str) -> str:
    raw = (uri or "").strip()
    if not raw:
        return ""
    return Path(raw).name


def _image_slot_stats(state: dict[str, Any] | None) -> dict[str, Any]:
    sections = (state or {}).get("sections") if isinstance(state, dict) else {}
    if not isinstance(sections, dict):
        sections = {}
    filled: list[dict[str, str]] = []
    free: list[str] = []
    for sid, entry in sections.items():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("kind") or "") != "image" and not str(sid).startswith("imagen_"):
            continue
        content = str(entry.get("content") or "").strip()
        status = str(entry.get("status") or "empty")
        if content and status == "complete":
            filled.append({"section_id": str(sid), "image_path": content})
        elif not content:
            free.append(str(sid))
    # Orden natural imagen_1, imagen_2, …
    def _slot_key(sid: str) -> tuple[int, str]:
        try:
            return (int(sid.split("_", 1)[-1]), sid)
        except Exception:
            return (999, sid)

    filled.sort(key=lambda x: _slot_key(x["section_id"]))
    free.sort(key=_slot_key)
    return {
        "images_filled": len(filled),
        "images_free": len(free),
        "filled_slots": filled,
        "next_free_slot": free[0] if free else None,
    }


def _enrich_list_item(row: dict[str, Any], conversation_id: str) -> dict[str, Any]:
    uri = str(row.get("rendered_docx_uri") or "")
    # list_report_instances admin read no incluye state completo en item;
    # progress ya viene; re-lee state vía progress + URI. Para slots, parseamos
    # si el row trae state (get) — en list no viene. Pedimos stats vía progress
    # incomplete: reabrir no; usamos progress.complete_count como proxy y URI.
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    item = {
        "instance_id": row.get("instance_id"),
        "title": row.get("title"),
        "template_id": row.get("template_id"),
        "template_name": row.get("template_name"),
        "status": row.get("status"),
        "progress": progress.get("completion_percent"),
        "updated_at": row.get("updated_at"),
        "output_filename": _output_basename(uri),
        "rendered_docx_uri": uri,
        "same_conversation": bool(
            conversation_id and str(row.get("conversation_id") or "") == conversation_id
        ),
    }
    return item


def _resume_score(item: dict[str, Any], *, query: str = "") -> int:
    """Ranking: match de archivo/título > más imágenes > ready > misma conversación."""
    score = 0
    if item.get("same_conversation"):
        score += 50
    status = str(item.get("status") or "")
    if status in {"ready", "rendered", "complete"}:
        score += 15
    # Preferir docs con más contenido ya rellenado (evita el complemento 1.4 vacío de contexto).
    try:
        score += int(item.get("images_filled") or 0) * 12
    except Exception:
        pass
    try:
        score += int(item.get("progress") or 0) // 5
    except Exception:
        pass
    title = str(item.get("title") or "").lower()
    fname = str(item.get("output_filename") or "").lower()
    q = (query or "").strip().lower()
    if q:
        if q in fname or q in str(item.get("instance_id") or "").lower():
            score += 200
        if q in title:
            score += 120
        # Hash rpt_XXXXXXXX en el nombre del archivo
        if "rpt_" in q:
            token = q
            for part in q.replace("\\", "/").split("/"):
                if "rpt_" in part:
                    token = part.split(".docx")[0]
                    break
            if token and token in fname:
                score += 250
    # Preferir evidencias multi-sección (1.1 … 1.4) sobre el complemento suelto «1.4».
    if "1.1" in title and "1.4" in title:
        score += 40
    elif "1.4" in title and "1.1" not in title:
        score -= 20
    return score


def _pick_resume(items: list[dict[str, Any]], *, query: str = "") -> str | None:
    if not items:
        return None
    ranked = sorted(
        items,
        key=lambda i: _resume_score(i, query=query),
        reverse=True,
    )
    return str(ranked[0].get("instance_id") or "") or None


def list_report_instances(limit: int = 20, query: str = "") -> str:
    """Lista documentos Word del usuario. Pasa query=nombre.docx o rpt_XXX si el usuario nombra un archivo.

    Úsalo ANTES de create. Si el usuario cita un .docx concreto, resolve_report_instance
    o query aquí — NO uses el complemento más reciente a ciegas.
    """
    from duckclaw.report_engine.admin_report_read import (
        get_report_instance,
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
        items: list[dict[str, Any]] = []
        for r in rows:
            item = _enrich_list_item(r, conversation_id)
            # Stats de imágenes desde state (necesario para ranking correcto).
            inst = get_report_instance(
                db,
                instance_id=str(r.get("instance_id") or ""),
                tenant_id=tenant_id,
            )
            stats = _image_slot_stats((inst or {}).get("state"))
            item["images_filled"] = stats["images_filled"]
            item["images_free"] = stats["images_free"]
            item["next_free_slot"] = stats["next_free_slot"]
            items.append(item)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        _close_hub_db_if_owned(db)

    q = (query or "").strip()
    if q:
        q_l = q.lower()
        filtered = [
            i
            for i in items
            if q_l in str(i.get("output_filename") or "").lower()
            or q_l in str(i.get("title") or "").lower()
            or q_l in str(i.get("instance_id") or "").lower()
            or q_l in str(i.get("rendered_docx_uri") or "").lower()
        ]
        if filtered:
            items = filtered

    resume = _pick_resume(items, query=q)
    return json.dumps(
        {
            "instances": items,
            "resume_suggestion": resume,
            "query": q or None,
            "count": len(items),
            "hint": (
                "Si el usuario nombró un .docx, usa ese instance_id. "
                "NO pidas reenviar imágenes ya en filled_slots: inspecciona con "
                "inspect_report_images o mira images_filled. "
                "Para agregar evidencia nueva: append_images_to_report."
            ),
        },
        ensure_ascii=False,
    )


def resolve_report_instance(query: str) -> str:
    """Resuelve instance_id a partir de nombre .docx, rpt_XXX o título parcial.

    Obligatorio cuando el usuario dice «agrégalo en EVIDENCIAS_…_rpt_58e9….docx».
    """
    q = (query or "").strip()
    if not q:
        return json.dumps({"error": "query vacío"}, ensure_ascii=False)
    raw = list_report_instances(limit=50, query=q)
    try:
        payload = json.loads(raw)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    if payload.get("error"):
        return raw
    items = payload.get("instances") or []
    if not items:
        return json.dumps(
            {
                "error": f"No hay documento que coincida con «{q}»",
                "hint": "list_report_instances sin filtro para ver los disponibles.",
            },
            ensure_ascii=False,
        )
    best = max(items, key=lambda i: _resume_score(i, query=q))
    return json.dumps(
        {
            "instance_id": best.get("instance_id"),
            "title": best.get("title"),
            "output_filename": best.get("output_filename"),
            "images_filled": best.get("images_filled"),
            "next_free_slot": best.get("next_free_slot"),
            "status": best.get("status"),
            "match_query": q,
        },
        ensure_ascii=False,
    )


def inspect_report_images(instance_id: str = "", query: str = "") -> str:
    """Inventario de imágenes YA en el documento (paths en vault). NO pidas reenviarlas."""
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
    )

    ref = (instance_id or "").strip()
    q = (query or "").strip()
    if not ref and q:
        resolved = json.loads(resolve_report_instance(q))
        if resolved.get("error"):
            return json.dumps(resolved, ensure_ascii=False)
        ref = str(resolved.get("instance_id") or "")
    if not ref:
        return json.dumps(
            {"error": "instance_id o query requeridos"},
            ensure_ascii=False,
        )

    tenant_id, actor_email, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        instance = get_report_instance(db, instance_id=ref, tenant_id=tenant_id)
        if not instance:
            return _missing_instance_error(ref)
        if not actor_can_access_instance(db, instance=instance, actor_email=actor_email):
            return json.dumps({"error": "Acceso denegado"}, ensure_ascii=False)
        from duckclaw.report_engine.blank_template import BLANK_SECTION_SCHEMA
        from duckclaw.report_engine.state import merge_missing_schema_sections

        template = None
        try:
            from duckclaw.report_engine.admin_report_read import get_report_template

            template = get_report_template(
                db, template_id=str(instance.get("template_id") or ""), tenant_id=tenant_id
            )
        except Exception:
            template = None
        schema = (template or {}).get("section_schema") or BLANK_SECTION_SCHEMA
        state = merge_missing_schema_sections(dict(instance.get("state") or {}), schema)
        stats = _image_slot_stats(state)
        return json.dumps(
            {
                "instance_id": ref,
                "title": instance.get("title"),
                "output_filename": _output_basename(
                    str(instance.get("rendered_docx_uri") or "")
                ),
                **stats,
                "hint": (
                    "Las filled_slots ya tienen imagen: NO pidas al usuario reenviarlas. "
                    "Solo pide/usa [IMAGENES_ADJUNTAS] del mensaje actual para huecos nuevos "
                    "(next_free_slot). Luego append_images_to_report + render."
                ),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        _close_hub_db_if_owned(db)


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
    force_new: bool = False,
) -> str:
    """Crea un documento Word desde CERO (sin plantilla previa): texto + imágenes.

    Usa plantilla en blanco con huecos intro/texto_1..15/cierre e imagen_1..15.
    Si ya hay un borrador de esta conversación, NO crea otro: usa
    append_images_to_report / patch + render sobre resume_suggestion
    (salvo force_new=true o el usuario pide explícitamente otro documento).
    """
    from duckclaw.forge.rag.knowledge_paths import knowledge_output_roots
    from duckclaw.report_engine.blank_template import (
        BLANK_SECTION_SCHEMA,
        ensure_blank_template_seed,
    )

    try:
        if not force_new and not (instance_id or "").strip():
            blocked = _resume_block_if_existing_draft()
            if blocked is not None:
                return blocked

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
        seed_path = ensure_blank_template_seed(template_root, force=True)
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
            "Si faltan textos: patch_report_section (texto_N, cierre). "
            "Para AGREGAR más imágenes al mismo doc: append_images_to_report. "
            "Luego render_report_instance."
        )
        return json.dumps(created, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _resume_block_if_existing_draft() -> str | None:
    """Si hay borrador de esta conversación, obliga a reanudar en vez de crear."""
    raw = list_report_instances(limit=20)
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if payload.get("error"):
        return None
    items = payload.get("instances") or []
    same = [i for i in items if i.get("same_conversation")]
    pool = same or items
    if not pool:
        return None
    iid = _pick_resume(pool) or payload.get("resume_suggestion")
    target = next((i for i in pool if i.get("instance_id") == iid), pool[0])
    return json.dumps(
        {
            "error": (
                "Ya existe un documento de esta conversación. "
                "NO crees uno nuevo: reanúdalo."
            ),
            "resume_instance_id": iid,
            "title": target.get("title"),
            "output_filename": target.get("output_filename"),
            "images_filled": target.get("images_filled"),
            "hint": (
                "Si el usuario nombró un .docx: resolve_report_instance(query). "
                "inspect_report_images para ver qué ya está (NO pedir reenviar). "
                "append_images_to_report + render_report_instance. "
                "Solo create_blank_document(..., force_new=true) si piden OTRO documento."
            ),
        },
        ensure_ascii=False,
    )


def _ensure_blank_template_up_to_date(tenant_id: str, actor_email: str) -> str:
    """Upsert plantilla blank con schema actual (15 slots) y regenera seed .docx."""
    from duckclaw.report_engine.blank_template import (
        BLANK_SECTION_SCHEMA,
        ensure_blank_template_seed,
    )

    template_root = _tenant_report_template_root(tenant_id)
    if template_root is None:
        raise ValueError("No se pudo resolver el vault privado del tenant")
    seed_path = ensure_blank_template_seed(template_root, force=True)
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
    return tid


def append_images_to_report(
    instance_id: str = "",
    image_paths: str = "",
    captions: str = "",
    query: str = "",
) -> str:
    """Agrega imágenes al siguiente hueco libre de un documento YA existente.

    instance_id O query (nombre .docx / rpt_XXX). Si el usuario nombra
    EVIDENCIAS_…_rpt_58e9….docx, pásalo en query — NO uses el doc complemento 1.4.
    Las imágenes 1.1–1.3 YA en el doc NO se reenvían: solo paths nuevos de
    [IMAGENES_ADJUNTAS] o de otro instance (inspect_report_images).
    """
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
    )
    from duckclaw.report_engine.blank_template import BLANK_IMAGE_SLOTS, BLANK_SECTION_SCHEMA
    from duckclaw.report_engine.state import merge_missing_schema_sections

    iid = (instance_id or "").strip()
    q = (query or "").strip()
    # Aceptar filename / rpt_ en el campo instance_id por comodidad del LLM.
    if not iid and q:
        resolved = json.loads(resolve_report_instance(q))
        if resolved.get("error"):
            return json.dumps(resolved, ensure_ascii=False)
        iid = str(resolved.get("instance_id") or "")
    elif iid and (".docx" in iid.lower() or "/" in iid or " " in iid):
        resolved = json.loads(resolve_report_instance(iid))
        if resolved.get("error"):
            return json.dumps(resolved, ensure_ascii=False)
        iid = str(resolved.get("instance_id") or "")

    if not iid:
        return json.dumps(
            {
                "error": "instance_id o query requeridos",
                "hint": "resolve_report_instance con el nombre .docx que citó el usuario.",
            },
            ensure_ascii=False,
        )
    paths = _parse_image_paths_arg(image_paths)
    if not paths:
        return json.dumps(
            {
                "error": "image_paths vacío",
                "hint": (
                    "Usa rutas de [IMAGENES_ADJUNTAS] del mensaje actual. "
                    "Si la 1.4 ya está en otro doc, inspect_report_images de ese "
                    "instance y reusa filled_slots[].image_path aquí."
                ),
            },
            ensure_ascii=False,
        )

    caption_list = [
        c.strip() for c in (captions or "").replace("\n", ";").split(";") if c.strip()
    ]

    tenant_id, actor_email, _ = _session_scope()
    try:
        _ensure_blank_template_up_to_date(tenant_id, actor_email)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    db = None
    rendered_uri = ""
    title = ""
    try:
        db = _open_hub_db()
        instance = get_report_instance(db, instance_id=iid, tenant_id=tenant_id)
        if not instance:
            return _missing_instance_error(iid)
        if not actor_can_access_instance(db, instance=instance, actor_email=actor_email):
            return json.dumps({"error": "Acceso denegado"}, ensure_ascii=False)
        rendered_uri = str(instance.get("rendered_docx_uri") or "")
        title = str(instance.get("title") or "")
        state = merge_missing_schema_sections(
            dict(instance.get("state") or {}), BLANK_SECTION_SCHEMA
        )
        sections = state.get("sections") if isinstance(state.get("sections"), dict) else {}
        already = _image_slot_stats(state)
    finally:
        _close_hub_db_if_owned(db)

    free_slots: list[str] = []
    for i in range(1, BLANK_IMAGE_SLOTS + 1):
        sid = f"imagen_{i}"
        entry = sections.get(sid) if isinstance(sections.get(sid), dict) else {}
        content = str((entry or {}).get("content") or "").strip()
        status = str((entry or {}).get("status") or "empty")
        if not content and status != "complete":
            free_slots.append(sid)

    if not free_slots:
        return json.dumps(
            {
                "error": f"No quedan huecos de imagen (máx. {BLANK_IMAGE_SLOTS})",
                "instance_id": iid,
                "already_filled": already.get("filled_slots"),
            },
            ensure_ascii=False,
        )

    placed: list[dict[str, str]] = []
    texts: list[dict[str, str]] = []
    for idx, path in enumerate(paths):
        if idx >= len(free_slots):
            break
        slot = free_slots[idx]
        patch_raw = patch_report_image(instance_id=iid, section_id=slot, image_path=path)
        patched = json.loads(patch_raw)
        if patched.get("error"):
            return json.dumps(
                {"error": patched.get("error"), "placed_so_far": placed, **patched},
                ensure_ascii=False,
            )
        placed.append({"section_id": slot, "image_path": path})
        if idx < len(caption_list):
            n = slot.split("_", 1)[-1]
            text_sid = f"texto_{n}"
            patch_report_section(
                instance_id=iid,
                section_id=text_sid,
                content=caption_list[idx],
                mode="replace",
                mark_complete=True,
            )
            texts.append({"section_id": text_sid, "content": caption_list[idx]})

    return json.dumps(
        {
            "instance_id": iid,
            "title": title,
            "output_filename": _output_basename(rendered_uri),
            "images_already_present": already.get("filled_slots"),
            "images_appended": placed,
            "texts_appended": texts,
            "remaining_image_slots": max(0, len(free_slots) - len(placed)),
            "hint": "Llama render_report_instance con este mismo instance_id para actualizar el .docx.",
        },
        ensure_ascii=False,
    )


def delete_report_instance(instance_id: str, delete_output_files: bool = True) -> str:
    """Archiva (soft-delete) un documento Report Engine y opcionalmente borra sus .docx en output/."""
    from duckclaw.forge.rag.knowledge_paths import (
        knowledge_output_roots,
        relative_path_under_output_root,
    )
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
    )

    iid = (instance_id or "").strip()
    if not iid:
        return json.dumps({"error": "instance_id requerido"}, ensure_ascii=False)

    tenant_id, actor_email, _ = _session_scope()
    deleted_paths: list[str] = []
    db = None
    try:
        db = _open_hub_db()
        instance = get_report_instance(db, instance_id=iid, tenant_id=tenant_id)
        if not instance:
            return _missing_instance_error(iid)
        if not actor_can_access_instance(db, instance=instance, actor_email=actor_email):
            return json.dumps({"error": "Acceso denegado"}, ensure_ascii=False)
        rendered = str(instance.get("rendered_docx_uri") or "").strip()
    finally:
        _close_hub_db_if_owned(db)

    _dispatch_write(
        {
            "command_type": "soft_delete_report_instance",
            "instance_id": iid,
        }
    )

    if delete_output_files and rendered:
        try:
            primary = Path(rendered).expanduser().resolve()
            roots = knowledge_output_roots()
            matched = relative_path_under_output_root(primary, roots) if roots else None
            targets: list[Path] = []
            if matched is not None:
                _root, rel = matched
                for root in roots:
                    targets.append((root.expanduser().resolve() / rel).resolve())
            else:
                targets.append(primary)
            for target in targets:
                if target.is_file():
                    target.unlink()
                    deleted_paths.append(str(target))
        except Exception as exc:
            return json.dumps(
                {
                    "instance_id": iid,
                    "archived": True,
                    "warning": f"Instancia archivada pero falló borrar output: {exc}",
                    "deleted_paths": deleted_paths,
                },
                ensure_ascii=False,
            )

    return json.dumps(
        {
            "instance_id": iid,
            "archived": True,
            "deleted_paths": deleted_paths,
        },
        ensure_ascii=False,
    )


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
        get_report_template,
    )
    from duckclaw.report_engine.state import merge_missing_schema_sections

    tenant_id, actor_email, _ = _session_scope()
    try:
        path = _resolve_patchable_image_path(image_path, tenant_id=tenant_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    sid = (section_id or "").strip()
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
        template = get_report_template(
            db, template_id=str(instance.get("template_id") or ""), tenant_id=tenant_id
        )
        schema = (template or {}).get("section_schema") or []
        state = merge_missing_schema_sections(dict(instance.get("state") or {}), schema)
        sections = state.get("sections") if isinstance(state.get("sections"), dict) else {}
        entry = sections.get(sid)
        if not isinstance(entry, dict):
            valid = [
                key
                for key, e in sections.items()
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
                        "(create_blank_document → imagen_1..15)."
                    )
                },
                ensure_ascii=False,
            )
    finally:
        _close_hub_db_if_owned(db)

    # El path se guarda como content (replace); el render lo convierte en InlineImage.
    return patch_report_section(
        instance_id=instance_id,
        section_id=sid,
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
                "No uses run_sandbox para fabricar Word; usa Report Engine."
            )
        if "sección desconocida" in msg:
            payload["hint"] = (
                "Revisa section_schema con list_report_templates "
                "y usa patch_report_section con un section_id válido."
            )
        return json.dumps(payload, ensure_ascii=False)


def render_report_instance(instance_id: str, force: bool = False) -> str:
    """Genera el DOCX del informe desde plantilla + estado actual."""
    from duckclaw.forge.rag.knowledge_paths import (
        knowledge_allowed_roots,
        knowledge_output_roots,
        replicate_file_to_all_output_roots,
    )
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
        primary_path = Path(str(rendered.get("path") or ""))
        replicated_paths = replicate_file_to_all_output_roots(primary_path, roots=roots)
        rendered["path"] = replicated_paths[0] if replicated_paths else str(primary_path)
        rendered["paths"] = replicated_paths
        rendered["output_roots"] = [str(r) for r in roots]
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
                    "paths": replicated_paths,
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
                description=(
                    "Lista plantillas Word (.docx) del Report Engine ya registradas. "
                    "Úsala cuando el usuario pide un informe/documento Word por plantilla "
                    "(p. ej. informe mensual de actividades) y necesitas el template_id. "
                    "NO sirve para listar tablas DuckDB ni el esquema de la base."
                ),
            ),
            StructuredTool.from_function(
                register_report_template,
                name="register_report_template",
                description=(
                    "Registra un .docx del vault (p. ej. INFORME MENSUAL.docx) en el Report Engine. "
                    "Paso 1 cuando piden rellenar/generar un informe Word con huecos {{ejecucionN.M}} "
                    "o {{fecha_ejecucion}}. Detecta section_id por placeholders. "
                    "NO uses inspect_schema/read_sql para este pedido: el destino es Word, no DuckDB."
                ),
            ),
            StructuredTool.from_function(
                list_report_instances,
                name="list_report_instances",
                description=(
                    "Lista borradores Word. Pasa query=nombre.docx o rpt_XXX si el usuario "
                    "nombra un archivo. resume_suggestion prioriza el doc con MÁS imágenes "
                    "(p. ej. evidencias 1.1–1.4), no el complemento suelto más reciente. "
                    "ÚSALO ANTES de create. No confundir con tablas SQL."
                ),
            ),
            StructuredTool.from_function(
                resolve_report_instance,
                name="resolve_report_instance",
                description=(
                    "Resuelve instance_id desde un .docx o rpt_XXX citado por el usuario. "
                    "Obligatorio cuando dicen «agrégalo en EVIDENCIAS_…_rpt_….docx»."
                ),
            ),
            StructuredTool.from_function(
                inspect_report_images,
                name="inspect_report_images",
                description=(
                    "Lista imágenes YA guardadas en un Word (paths vault). "
                    "PROHIBIDO pedir al usuario que reenvíe esas imágenes. "
                    "Solo pide adjuntos nuevos para next_free_slot."
                ),
            ),
            StructuredTool.from_function(
                create_report_instance,
                name="create_report_instance",
                description=(
                    "Crea borrador Word desde plantilla registrada (template_id + title). "
                    "Úsalo tras register/list cuando el usuario da textos de ejecuciones "
                    "(1.1, 1.2, …) o pide generar el informe mensual. "
                    "Luego patch_report_section por cada section_id y render_report_instance. "
                    "NO pidas periodo como campo de producto; la identidad es instance_id."
                ),
            ),
            StructuredTool.from_function(
                create_blank_document,
                name="create_blank_document",
                description=(
                    "Crea un Word NUEVO desde cero (hasta 15 imágenes). "
                    "PROHIBIDO si el usuario pide agregar/completar un doc ya generado: "
                    "entonces resolve_report_instance → append_images_to_report. "
                    "Si ya hay borrador de esta conversación, esta tool falla salvo "
                    "force_new=true. Pasa image_paths de [IMAGENES_ADJUNTAS]."
                ),
            ),
            StructuredTool.from_function(
                append_images_to_report,
                name="append_images_to_report",
                description=(
                    "Agrega imágenes al siguiente hueco libre de un Word YA existente. "
                    "Pasa query=EVIDENCIAS_….docx o instance_id. "
                    "Si la 1.4 está en otro doc complemento, inspect_report_images de ese "
                    "y reusa el path; NO pidas reenviar 1.1–1.3. Luego render."
                ),
            ),
            StructuredTool.from_function(
                delete_report_instance,
                name="delete_report_instance",
                description=(
                    "Archiva un documento Report Engine (soft-delete) y opcionalmente "
                    "borra sus .docx en output/ (todas las raíces). Úsalo cuando pidan "
                    "eliminar un informe/evidencias generado por error."
                ),
            ),
            StructuredTool.from_function(
                patch_report_image,
                name="patch_report_image",
                description=(
                    "Coloca una imagen adjunta (por su path del chat/vault) en una sección "
                    "kind=image (p. ej. imagen_1). Se inserta como InlineImage en el render, "
                    "conservando el layout. Para agregar varias al doc existente preferí "
                    "append_images_to_report. Para texto usa patch_report_section."
                ),
            ),
            StructuredTool.from_function(
                get_report_status,
                name="get_report_status",
                description=(
                    "Estado de secciones del borrador Word (faltantes/parciales/completas). "
                    "Úsalo antes de cerrar el informe. No consulta el esquema DuckDB."
                ),
            ),
            StructuredTool.from_function(
                patch_report_section,
                name="patch_report_section",
                description=(
                    "Rellena UNA sección del informe Word (mode append|replace) por section_id "
                    "del schema (p. ej. ejecucion1.1, ejecucion2.1, fecha_ejecucion). "
                    "Cuando el usuario dicte 'en la ejecución 1.1 pon: …', mapea a ese id y "
                    "escribe en pasado con tildes. Texto plano por hueco — no pegues tablas "
                    "markdown ni inventes SQL. La plantilla conserva layout; tú solo llenas huecos."
                ),
            ),
            StructuredTool.from_function(
                render_report_instance,
                name="render_report_instance",
                description=(
                    "Genera el .docx final (docxtpl) en OUTPUT tras patch. "
                    "Escribe en todas las DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS a la vez "
                    "(espejo local + Drive) para trazabilidad. "
                    "Úsalo cuando el usuario pide generar/exportar el informe en la carpeta "
                    "output para revisar (luego evidencias). Falla si faltan required o "
                    "quedan {{ }}. force=true exporta borrador incompleto. "
                    "No inventes Word fuera del motor."
                ),
            ),
            StructuredTool.from_function(
                generate_report_docx_from_markdown,
                name="generate_report_docx_from_markdown",
                description=(
                    "ÚLTIMO RECURSO — solo plantillas de UN campo. "
                    "Informe mensual multi-campo ({{ejecucion1.1}}, …): create + patch por "
                    "section_id + render. No sustituye el flujo por sección. "
                    "PDF: export_docx_to_pdf tras el render."
                ),
            ),
        ]
    )
