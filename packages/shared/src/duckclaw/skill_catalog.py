"""DB-first catalog of skill categories and pickable platform skills."""

from __future__ import annotations

import json
import logging
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from duckclaw.framework_tool_pack import baseline_skills_for_profile, load_framework_tool_pack
from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_log = logging.getLogger(__name__)

PACK_FILENAME = "framework_skill_categories_v1.json"
PACK_SEED = "framework_skill_categories_v1"

_ADMIN_SKILL_CATEGORIES_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_skill_categories (
    category_id VARCHAR PRIMARY KEY,
    category_key VARCHAR NOT NULL UNIQUE,
    title VARCHAR NOT NULL,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    read_only BOOLEAN DEFAULT false,
    scope VARCHAR DEFAULT 'platform',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_ADMIN_SKILL_CATALOG_ITEMS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_skill_catalog_items (
    item_id VARCHAR PRIMARY KEY,
    category_id VARCHAR NOT NULL,
    skill_key VARCHAR NOT NULL,
    label VARCHAR NOT NULL,
    hint TEXT,
    sort_order INTEGER DEFAULT 0,
    default_config_json TEXT DEFAULT '{}',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (category_id, skill_key)
)
"""

_CREATE_INDEXES_DDL = """
CREATE INDEX IF NOT EXISTS idx_admin_skill_catalog_items_category
    ON main.admin_skill_catalog_items (category_id, active, sort_order)
"""


def skill_categories_pack_path() -> Path:
    return Path(__file__).resolve().parent / "seeds" / PACK_FILENAME


@lru_cache(maxsize=1)
def load_skill_categories_pack() -> dict[str, Any]:
    path = skill_categories_pack_path()
    if not path.is_file():
        raise FileNotFoundError(f"skill categories pack not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("skill categories pack must be a JSON object")
    return data


def ensure_skill_catalog_schema(db: Any) -> None:
    if getattr(db, "_read_only", False):
        return
    for ddl in (
        _ADMIN_SKILL_CATEGORIES_DDL,
        _ADMIN_SKILL_CATALOG_ITEMS_DDL,
        _CREATE_INDEXES_DDL,
    ):
        for stmt in ddl.strip().split(";"):
            sql = stmt.strip()
            if sql:
                db.execute(sql)


def _category_row_count(db: Any) -> int:
    rows = _query_all_dicts(db, "SELECT COUNT(*) AS cnt FROM main.admin_skill_categories")
    if not rows:
        return 0
    raw = rows[0].get("cnt")
    return int(raw or 0)


def seed_framework_skill_catalog_if_empty(db: Any) -> int:
    """Insert platform skill categories from the framework seed when tables are empty."""
    if getattr(db, "_read_only", False):
        return 0
    ensure_skill_catalog_schema(db)
    if _category_row_count(db) > 0:
        return 0
    pack = load_skill_categories_pack()
    inserted = 0
    for raw_category in pack.get("categories") or []:
        if not isinstance(raw_category, dict):
            continue
        category_key = str(raw_category.get("id") or "").strip()
        title = str(raw_category.get("title") or "").strip()
        if not category_key or not title:
            continue
        category_id = f"skcat_{uuid.uuid4().hex}"
        description = str(raw_category.get("description") or "").strip()
        sort_order = int(raw_category.get("sort_order") or 0)
        read_only = bool(raw_category.get("read_only", False))
        db.execute(
            f"""
            INSERT INTO main.admin_skill_categories
              (category_id, category_key, title, description, sort_order, read_only, scope)
            VALUES (
              '{_sql_lit(category_id, 64)}',
              '{_sql_lit(category_key, 128)}',
              '{_sql_lit(title, 256)}',
              '{_sql_lit(description, 2048)}',
              {sort_order},
              {str(read_only).lower()},
              'platform'
            )
            """
        )
        inserted += 1
        skills = raw_category.get("skills") or []
        if not isinstance(skills, list):
            continue
        for idx, raw_skill in enumerate(skills):
            if isinstance(raw_skill, str):
                skill_key = raw_skill.strip()
                label = skill_key
                hint = ""
                default_config: dict[str, Any] = {}
            elif isinstance(raw_skill, dict):
                skill_key = str(raw_skill.get("id") or "").strip()
                label = str(raw_skill.get("label") or skill_key).strip() or skill_key
                hint = str(raw_skill.get("hint") or "").strip()
                cfg = raw_skill.get("default_config")
                default_config = dict(cfg) if isinstance(cfg, dict) else {}
            else:
                continue
            if not skill_key:
                continue
            item_id = f"skitem_{uuid.uuid4().hex}"
            db.execute(
                f"""
                INSERT INTO main.admin_skill_catalog_items
                  (item_id, category_id, skill_key, label, hint, sort_order, default_config_json)
                VALUES (
                  '{_sql_lit(item_id, 64)}',
                  '{_sql_lit(category_id, 64)}',
                  '{_sql_lit(skill_key, 128)}',
                  '{_sql_lit(label, 256)}',
                  '{_sql_lit(hint, 1024)}',
                  {idx * 10},
                  '{_sql_lit(json.dumps(default_config, ensure_ascii=False), 8192)}'
                )
                """
            )
    if inserted:
        _log.info("seeded %d framework skill categories (%s)", inserted, PACK_SEED)
    return inserted


def sync_framework_skill_catalog_from_pack(db: Any) -> int:
    """Insert missing platform categories and skills from the framework seed (idempotent)."""
    if getattr(db, "_read_only", False):
        return 0
    ensure_skill_catalog_schema(db)
    pack = load_skill_categories_pack()
    added = 0
    for raw_category in pack.get("categories") or []:
        if not isinstance(raw_category, dict):
            continue
        category_key = str(raw_category.get("id") or "").strip()
        title = str(raw_category.get("title") or "").strip()
        if not category_key or not title:
            continue
        description = str(raw_category.get("description") or "").strip()
        sort_order = int(raw_category.get("sort_order") or 0)
        read_only = bool(raw_category.get("read_only", False))
        cat_rows = _query_all_dicts(
            db,
            "SELECT category_id FROM main.admin_skill_categories "
            f"WHERE category_key = '{_sql_lit(category_key, 128)}' LIMIT 1",
        )
        if cat_rows:
            category_id = str(cat_rows[0].get("category_id") or "")
        else:
            category_id = f"skcat_{uuid.uuid4().hex}"
            db.execute(
                f"""
                INSERT INTO main.admin_skill_categories
                  (category_id, category_key, title, description, sort_order, read_only, scope)
                VALUES (
                  '{_sql_lit(category_id, 64)}',
                  '{_sql_lit(category_key, 128)}',
                  '{_sql_lit(title, 256)}',
                  '{_sql_lit(description, 2048)}',
                  {sort_order},
                  {str(read_only).lower()},
                  'platform'
                )
                """
            )
            added += 1
        skills = raw_category.get("skills") or []
        if not isinstance(skills, list):
            continue
        for idx, raw_skill in enumerate(skills):
            if isinstance(raw_skill, str):
                skill_key = raw_skill.strip()
                label = skill_key
                hint = ""
                default_config: dict[str, Any] = {}
            elif isinstance(raw_skill, dict):
                skill_key = str(raw_skill.get("id") or "").strip()
                label = str(raw_skill.get("label") or skill_key).strip() or skill_key
                hint = str(raw_skill.get("hint") or "").strip()
                cfg = raw_skill.get("default_config")
                default_config = dict(cfg) if isinstance(cfg, dict) else {}
            else:
                continue
            if not skill_key:
                continue
            item_rows = _query_all_dicts(
                db,
                "SELECT item_id FROM main.admin_skill_catalog_items "
                f"WHERE category_id = '{_sql_lit(category_id, 64)}' "
                f"AND skill_key = '{_sql_lit(skill_key, 128)}' LIMIT 1",
            )
            if item_rows:
                continue
            item_id = f"skitem_{uuid.uuid4().hex}"
            db.execute(
                f"""
                INSERT INTO main.admin_skill_catalog_items
                  (item_id, category_id, skill_key, label, hint, sort_order, default_config_json)
                VALUES (
                  '{_sql_lit(item_id, 64)}',
                  '{_sql_lit(category_id, 64)}',
                  '{_sql_lit(skill_key, 128)}',
                  '{_sql_lit(label, 256)}',
                  '{_sql_lit(hint, 1024)}',
                  {idx * 10},
                  '{_sql_lit(json.dumps(default_config, ensure_ascii=False), 8192)}'
                )
                """
            )
            added += 1
    if added:
        _log.info("synced %d missing framework skill catalog rows (%s)", added, PACK_SEED)
    return added


def list_skill_categories_from_db(db: Any) -> list[dict[str, Any]]:
    ensure_skill_catalog_schema(db)
    seed_framework_skill_catalog_if_empty(db)
    sync_framework_skill_catalog_from_pack(db)
    categories: list[dict[str, Any]] = []
    cat_rows = _query_all_dicts(
        db,
        "SELECT category_id, category_key, title, description, sort_order, read_only "
        "FROM main.admin_skill_categories "
        "WHERE active = true "
        "ORDER BY sort_order, title",
    )
    for cat in cat_rows:
        category_id = str(cat.get("category_id") or "")
        item_rows = _query_all_dicts(
            db,
            "SELECT skill_key, label, hint, sort_order "
            "FROM main.admin_skill_catalog_items "
            f"WHERE category_id = '{_sql_lit(category_id, 64)}' AND active = true "
            "ORDER BY sort_order, label",
        )
        skills = [
            {
                "id": str(row.get("skill_key") or "").strip(),
                "label": str(row.get("label") or row.get("skill_key") or "").strip(),
                "hint": str(row.get("hint") or "").strip() or None,
            }
            for row in item_rows
            if str(row.get("skill_key") or "").strip()
        ]
        categories.append(
            {
                "id": str(cat.get("category_key") or "").strip(),
                "title": str(cat.get("title") or "").strip(),
                "description": str(cat.get("description") or "").strip() or None,
                "read_only": bool(cat.get("read_only")),
                "skills": skills,
            }
        )
    return categories


def baseline_profiles_payload() -> dict[str, list[str]]:
    pack = load_framework_tool_pack()
    profiles = pack.get("profiles") or {}
    out: dict[str, list[str]] = {}
    if isinstance(profiles, dict):
        for key in ("general", "minimal", "rag_only"):
            if key in profiles:
                out[key] = baseline_skills_for_profile(key)
    if "general" not in out:
        out["general"] = baseline_skills_for_profile("general")
    return out


def skill_categories_api_payload(db: Any) -> dict[str, Any]:
    return {
        "categories": list_skill_categories_from_db(db),
        "baseline_profiles": baseline_profiles_payload(),
        "pack_version": PACK_SEED,
    }
