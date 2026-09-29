#!/usr/bin/env python3
"""One-shot: register the "ponytail" directive skill via the DB-Writer queue.

Directive skills aren't code — the actual behavior change happens in
services/api-gateway/routers/admin_domains/playground/directive_skills.py,
which injects this description as an instruction when a chat message starts
with "/ponytail". Condensed to fit UpsertCatalogSkillCommand's 1024-char
description limit (that limit is sized for short tool-skill blurbs, not full
skill docs — kept it rather than raised it, this condensed version is enough
to work as an instruction).

Run: uv run python scripts/seed_ponytail_directive_skill.py
"""
from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

PONYTAIL_DIRECTIVE = (
    "Eres un dev senior perezoso: perezoso = eficiente, no descuidado. Antes de "
    "escribir codigo, sube esta escalera y detente en el primer peldano que sirva: "
    "1) Necesita existir esto? (YAGNI; si no, dilo en una linea) 2) Ya existe en "
    "este codigo? (reusalo) 3) Lo resuelve la stdlib o una dependencia ya instalada? "
    "4) Cabe en una linea? 5) Solo entonces, el minimo codigo que funcione. Bug = "
    "causa raiz, no sintoma: revisa todos los callers de lo que tocas, arreglalo una "
    "vez en el lugar compartido, no parchees solo la ruta que menciona el ticket. "
    "Sin abstracciones no pedidas, sin boilerplate para despues. Menos codigo es "
    "mejor que codigo clever. Marca simplificaciones deliberadas con un comentario "
    "que nombre el techo y el upgrade path. Nunca simplifiques: validacion en "
    "fronteras de confianza, manejo de errores que evita perdida de datos, "
    "seguridad, o lo pedido explicitamente. Salida: codigo primero, luego maximo "
    "3 lineas de que se omitio y cuando agregarlo."
)


def main() -> int:
    assert len(PONYTAIL_DIRECTIVE) <= 1024, f"too long: {len(PONYTAIL_DIRECTIVE)} chars"

    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import UpsertCatalogSkillCommand

    command = UpsertCatalogSkillCommand(
        tenant_id="default",
        actor_email="juanjoarevalo57@gmail.com",
        name="ponytail",
        description=PONYTAIL_DIRECTIVE,
        skill_type="directive",
        implementation_ref="directive://ponytail",
        visibility="public",
    )
    task_id = enqueue_typed_command(
        command,
        db_path=get_gateway_db_path(),
        user_id="juanjoarevalo57@gmail.com",
    )
    print(f"enqueued upsert_catalog_skill task_id={task_id} chars={len(PONYTAIL_DIRECTIVE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
