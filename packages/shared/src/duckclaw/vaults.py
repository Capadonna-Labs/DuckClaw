from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import duckdb


_DDL_USER_VAULTS = """
CREATE TABLE IF NOT EXISTS main.user_vaults (
    user_id VARCHAR,
    scope_id VARCHAR NOT NULL DEFAULT '',
    vault_id VARCHAR,
    vault_name VARCHAR,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, scope_id, vault_id)
);
"""


def _safe_user_id(user_id: Any) -> str:
    raw = (str(user_id or "").strip() or "default").lower()
    return re.sub(r"[^a-z0-9_-]", "_", raw)[:128] or "default"


def _slug_vault_id(name: Any) -> str:
    raw = str(name or "").strip().lower()
    if not raw:
        return ""
    slug = re.sub(r"[^a-z0-9_-]+", "_", raw)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:64]


def vault_scope_id_for_tenant(tenant_id: Any) -> str:
    """
    Ámbito de registro multi-bóveda alineado con el tenant efectivo del gateway.
    ``default`` o vacío → legacy (una sola familia de filas con scope_id '').
    """
    t = str(tenant_id or "").strip()
    if not t or t.lower() == "default":
        return ""
    return _safe_user_id(t)


def _normalize_scope_id(scope_id: Any) -> str:
    s = str(scope_id or "").strip()
    if not s:
        return ""
    return _safe_user_id(s)


def _initial_vault_id_for_scoped_bootstrap() -> str:
    raw = (os.environ.get("DUCKCLAW_MULTI_VAULT_INITIAL_VAULT_ID") or "").strip()
    return _slug_vault_id(raw) or "default"


def db_root() -> Path:
    """
    Directorio `db/` del monorepo.

    Si el proceso arranca con cwd distinto del repo (p. ej. `services/db-writer`),
    definir `DUCKCLAW_REPO_ROOT` apuntando a la raíz del monorepo; si no, se usa
    `Path(\"db\").resolve()` relativo al cwd (comportamiento legacy).
    """
    env_root = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if env_root:
        return (Path(env_root).expanduser().resolve() / "db")
    return Path("db").resolve()


def system_db_path() -> Path:
    root = db_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "system.duckdb"


def user_vault_dir(user_id: Any) -> Path:
    path = db_root() / "private" / _safe_user_id(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def vault_file_path(user_id: Any, vault_id: str) -> Path:
    vid = _slug_vault_id(vault_id) or "default"
    return user_vault_dir(user_id) / f"{vid}.duckdb"


def _user_vaults_table_exists(db: duckdb.DuckDBPyConnection) -> bool:
    try:
        db.execute("SELECT 1 FROM main.user_vaults LIMIT 0")
        return True
    except Exception:
        return False


def _user_vaults_has_scope_id(db: duckdb.DuckDBPyConnection) -> bool:
    try:
        rows = db.execute("PRAGMA table_info('main.user_vaults')").fetchall()
    except Exception:
        return False
    names = {str(r[1]) for r in rows}
    return "scope_id" in names


def _migrate_legacy_user_vaults_table(db: duckdb.DuckDBPyConnection) -> None:
    db.execute(
        """
        CREATE TABLE main.user_vaults_scoped_migration (
            user_id VARCHAR,
            scope_id VARCHAR NOT NULL DEFAULT '',
            vault_id VARCHAR,
            vault_name VARCHAR,
            is_active BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, scope_id, vault_id)
        )
        """
    )
    db.execute(
        """
        INSERT INTO main.user_vaults_scoped_migration
            (user_id, scope_id, vault_id, vault_name, is_active, created_at)
        SELECT user_id, '', vault_id, vault_name, is_active, created_at
        FROM main.user_vaults
        """
    )
    db.execute("DROP TABLE main.user_vaults")
    db.execute("ALTER TABLE main.user_vaults_scoped_migration RENAME TO user_vaults")


def ensure_registry() -> None:
    db = duckdb.connect(str(system_db_path()), read_only=False)
    try:
        if not _user_vaults_table_exists(db):
            db.execute(_DDL_USER_VAULTS)
            return
        if not _user_vaults_has_scope_id(db):
            _migrate_legacy_user_vaults_table(db)
    finally:
        db.close()


def _touch_duckdb_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        db = duckdb.connect(str(path), read_only=False)
        try:
            db.execute("SELECT 1")
        finally:
            db.close()
    except Exception:
        # Best-effort bootstrap: si hay lock concurrente, no bloquear el flujo.
        # El archivo/DB podrá existir ya y ser usable por el proceso principal.
        pass


def _discover_existing_user_vaults(uid: str) -> list[str]:
    """Return vault_ids discovered from existing *.duckdb files in user's folder."""
    folder = user_vault_dir(uid)
    discovered: list[str] = []
    for p in sorted(folder.glob("*.duckdb")):
        stem = (p.stem or "").strip().lower()
        vid = _slug_vault_id(stem)
        if vid:
            discovered.append(vid)
    return discovered


def _discover_existing_user_vaults_with_size(uid: str) -> list[tuple[str, int]]:
    folder = user_vault_dir(uid)
    out: list[tuple[str, int]] = []
    for p in folder.glob("*.duckdb"):
        vid = _slug_vault_id((p.stem or "").strip().lower())
        if not vid:
            continue
        try:
            size = int(p.stat().st_size)
        except Exception:
            size = 0
        out.append((vid, size))
    # Largest first so real vaults like finanzdb1 outrank fresh default files.
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def _sync_registry_with_files(
    sysdb: duckdb.DuckDBPyConnection, uid: str, scope_id: str
) -> None:
    """Registra en el ámbito dado cada *.duckdb del usuario (inactivas). Solo se usa en legacy."""
    sid = _normalize_scope_id(scope_id)
    if sid != "":
        return
    for vid, _sz in _discover_existing_user_vaults_with_size(uid):
        sysdb.execute(
            """
            INSERT INTO main.user_vaults (user_id, scope_id, vault_id, vault_name, is_active)
            VALUES (?, ?, ?, ?, FALSE)
            ON CONFLICT (user_id, scope_id, vault_id) DO NOTHING
            """,
            [uid, sid, vid, vid],
        )


def _try_read_active_vault_readonly(user_id: Any, scope_id: Any = "") -> tuple[str, Path] | None:
    """
    Camino rápido RO para el Gateway: devuelve la bóveda activa si el registry ya existe.
    Si falta bootstrap o migración, el caller puede caer al camino RW legado.
    """
    uid = _safe_user_id(user_id)
    sid = _normalize_scope_id(scope_id)
    sys_path = system_db_path()
    if not sys_path.exists():
        return None
    try:
        sysdb = duckdb.connect(str(sys_path), read_only=True)
    except Exception:
        return None
    try:
        if not _user_vaults_table_exists(sysdb) or not _user_vaults_has_scope_id(sysdb):
            return None
        row = sysdb.execute(
            """
            SELECT vault_id FROM main.user_vaults
            WHERE user_id = ? AND scope_id = ? AND is_active = TRUE
            LIMIT 1
            """,
            [uid, sid],
        ).fetchone()
        if not row:
            return None
        vault_id = str(row[0] or "default").strip() or "default"
        return vault_id, vault_file_path(uid, vault_id)
    finally:
        sysdb.close()


def _try_list_vaults_readonly(user_id: Any, scope_id: Any = "") -> list[dict[str, Any]] | None:
    """
    Lee el registry en RO cuando ya está inicializado. Evita abrir system.duckdb en RW
    durante requests comunes del Gateway.
    """
    uid = _safe_user_id(user_id)
    sid = _normalize_scope_id(scope_id)
    sys_path = system_db_path()
    if not sys_path.exists():
        return None
    try:
        sysdb = duckdb.connect(str(sys_path), read_only=True)
    except Exception:
        return None
    try:
        if not _user_vaults_table_exists(sysdb) or not _user_vaults_has_scope_id(sysdb):
            return None
        rows = sysdb.execute(
            """
            SELECT vault_id, vault_name, is_active, created_at
            FROM main.user_vaults
            WHERE user_id = ? AND scope_id = ?
            ORDER BY created_at, vault_id
            """,
            [uid, sid],
        ).fetchall()
    finally:
        sysdb.close()

    out: list[dict[str, Any]] = []
    for vault_id, vault_name, is_active, created_at in rows:
        path = vault_file_path(uid, str(vault_id))
        size = path.stat().st_size if path.exists() else 0
        out.append(
            {
                "vault_id": str(vault_id),
                "vault_name": str(vault_name or vault_id or ""),
                "is_active": bool(is_active),
                "created_at": str(created_at or ""),
                "db_path": str(path.resolve()),
                "size_bytes": int(size),
            }
        )
    return out


def _bootstrap_default_if_missing(user_id: Any, scope_id: Any = "") -> tuple[str, Path]:
    uid = _safe_user_id(user_id)
    sid = _normalize_scope_id(scope_id)
    ensure_registry()
    sysdb = duckdb.connect(str(system_db_path()), read_only=False)
    try:
        rows = sysdb.execute(
            """
            SELECT vault_id FROM main.user_vaults
            WHERE user_id = ? AND scope_id = ? AND is_active = TRUE
            LIMIT 1
            """,
            [uid, sid],
        ).fetchall()
        if rows:
            vault_id = str(rows[0][0] or "default").strip() or "default"
            path = vault_file_path(uid, vault_id)

            # Solo legacy: promover por tamaño otra bóveda cuando la activa es default.
            if sid == "" and vault_id == "default":
                discovered_with_size = _discover_existing_user_vaults_with_size(uid)
                non_default = [(vid, sz) for vid, sz in discovered_with_size if vid != "default"]
                if non_default:
                    count_non_default_rows = sysdb.execute(
                        """
                        SELECT COUNT(*) FROM main.user_vaults
                        WHERE user_id = ? AND scope_id = ? AND vault_id <> 'default'
                        """,
                        [uid, sid],
                    ).fetchone()
                    known_non_default = int((count_non_default_rows or [0])[0] or 0)
                    default_size = 0
                    try:
                        default_size = int(path.stat().st_size) if path.exists() else 0
                    except Exception:
                        default_size = 0
                    should_promote = known_non_default == 0 or default_size <= 12288
                    if should_promote:
                        chosen, _ = non_default[0]
                        chosen_path = vault_file_path(uid, chosen)
                        _touch_duckdb_file(chosen_path)
                        sysdb.execute(
                            "UPDATE main.user_vaults SET is_active = FALSE WHERE user_id = ? AND scope_id = ?",
                            [uid, sid],
                        )
                        _sync_registry_with_files(sysdb, uid, sid)
                        sysdb.execute(
                            """
                            INSERT INTO main.user_vaults
                                (user_id, scope_id, vault_id, vault_name, is_active)
                            VALUES (?, ?, ?, ?, TRUE)
                            ON CONFLICT (user_id, scope_id, vault_id) DO UPDATE SET is_active=TRUE
                            """,
                            [uid, sid, chosen, chosen],
                        )
                        return chosen, chosen_path

            _touch_duckdb_file(path)
            return vault_id, path

        # Sin fila activa en este ámbito
        if sid != "":
            chosen = _initial_vault_id_for_scoped_bootstrap()
            chosen_path = vault_file_path(uid, chosen)
            _touch_duckdb_file(chosen_path)
            sysdb.execute(
                "UPDATE main.user_vaults SET is_active = FALSE WHERE user_id = ? AND scope_id = ?",
                [uid, sid],
            )
            sysdb.execute(
                """
                INSERT INTO main.user_vaults (user_id, scope_id, vault_id, vault_name, is_active)
                VALUES (?, ?, ?, ?, TRUE)
                ON CONFLICT (user_id, scope_id, vault_id) DO UPDATE SET is_active=TRUE
                """,
                [uid, sid, chosen, chosen],
            )
            return chosen, chosen_path

        # Legacy: adoptar del disco o default
        discovered = _discover_existing_user_vaults(uid)
        chosen = ""
        non_default = [v for v in discovered if v != "default"]
        if non_default:
            chosen = non_default[0]
        elif discovered:
            chosen = discovered[0]
        else:
            chosen = "default"

        chosen_path = vault_file_path(uid, chosen)
        _touch_duckdb_file(chosen_path)
        sysdb.execute(
            "UPDATE main.user_vaults SET is_active = FALSE WHERE user_id = ? AND scope_id = ?",
            [uid, sid],
        )
        _sync_registry_with_files(sysdb, uid, sid)
        sysdb.execute(
            """
            INSERT INTO main.user_vaults (user_id, scope_id, vault_id, vault_name, is_active)
            VALUES (?, ?, ?, ?, TRUE)
            ON CONFLICT (user_id, scope_id, vault_id) DO UPDATE SET is_active=TRUE
            """,
            [uid, sid, chosen, chosen],
        )
        return chosen, chosen_path
    finally:
        sysdb.close()


def resolve_active_vault(user_id: Any, scope_id: Any = "") -> tuple[str, str]:
    sid = _normalize_scope_id(scope_id)
    ro_hit = _try_read_active_vault_readonly(user_id, sid)
    if ro_hit is not None:
        vault_id, path = ro_hit
        return vault_id, str(path.resolve())
    vault_id, path = _bootstrap_default_if_missing(user_id, sid)
    return vault_id, str(path.resolve())


def list_vaults(user_id: Any, scope_id: Any = "") -> list[dict[str, Any]]:
    uid = _safe_user_id(user_id)
    sid = _normalize_scope_id(scope_id)
    ro_rows = _try_list_vaults_readonly(uid, sid)
    if ro_rows:
        return ro_rows
    ensure_registry()
    sysdb = duckdb.connect(str(system_db_path()), read_only=False)
    try:
        _sync_registry_with_files(sysdb, uid, sid)
        rows = sysdb.execute(
            """
            SELECT vault_id, vault_name, is_active, created_at
            FROM main.user_vaults
            WHERE user_id = ? AND scope_id = ?
            ORDER BY created_at, vault_id
            """,
            [uid, sid],
        ).fetchall()
    finally:
        sysdb.close()

    out: list[dict[str, Any]] = []
    for vault_id, vault_name, is_active, created_at in rows:
        path = vault_file_path(uid, str(vault_id))
        size = path.stat().st_size if path.exists() else 0
        out.append(
            {
                "vault_id": str(vault_id),
                "vault_name": str(vault_name or vault_id or ""),
                "is_active": bool(is_active),
                "created_at": str(created_at or ""),
                "db_path": str(path.resolve()),
                "size_bytes": int(size),
            }
        )
    if not out:
        resolve_active_vault(uid, sid)
        return list_vaults(uid, sid)
    return out


def create_vault(user_id: Any, vault_name: str, scope_id: Any = "") -> dict[str, Any]:
    uid = _safe_user_id(user_id)
    sid = _normalize_scope_id(scope_id)
    name = (vault_name or "").strip() or "vault"
    base = _slug_vault_id(name) or "vault"
    ensure_registry()
    sysdb = duckdb.connect(str(system_db_path()), read_only=False)
    try:
        suffix = 1
        vault_id = base
        while True:
            row = sysdb.execute(
                """
                SELECT 1 FROM main.user_vaults
                WHERE user_id = ? AND scope_id = ? AND vault_id = ?
                LIMIT 1
                """,
                [uid, sid, vault_id],
            ).fetchone()
            if not row:
                break
            suffix += 1
            vault_id = f"{base}_{suffix}"
        path = vault_file_path(uid, vault_id)
        _touch_duckdb_file(path)
        sysdb.execute(
            """
            INSERT INTO main.user_vaults (user_id, scope_id, vault_id, vault_name, is_active)
            VALUES (?, ?, ?, ?, FALSE)
            """,
            [uid, sid, vault_id, name[:128]],
        )
        return {"vault_id": vault_id, "vault_name": name[:128], "db_path": str(path.resolve())}
    finally:
        sysdb.close()


def switch_vault(user_id: Any, vault_id: str, scope_id: Any = "") -> bool:
    uid = _safe_user_id(user_id)
    sid = _normalize_scope_id(scope_id)
    vid = _slug_vault_id(vault_id)
    if not vid:
        return False
    ensure_registry()
    sysdb = duckdb.connect(str(system_db_path()), read_only=False)
    try:
        _sync_registry_with_files(sysdb, uid, sid)
        exists = sysdb.execute(
            """
            SELECT 1 FROM main.user_vaults
            WHERE user_id = ? AND scope_id = ? AND vault_id = ?
            LIMIT 1
            """,
            [uid, sid, vid],
        ).fetchone()
        if not exists:
            return False
        _touch_duckdb_file(vault_file_path(uid, vid))
        sysdb.execute(
            "UPDATE main.user_vaults SET is_active = FALSE WHERE user_id = ? AND scope_id = ?",
            [uid, sid],
        )
        sysdb.execute(
            """
            UPDATE main.user_vaults SET is_active = TRUE
            WHERE user_id = ? AND scope_id = ? AND vault_id = ?
            """,
            [uid, sid, vid],
        )
        return True
    finally:
        sysdb.close()


def remove_vault(user_id: Any, vault_id: str, scope_id: Any = "") -> bool:
    uid = _safe_user_id(user_id)
    sid = _normalize_scope_id(scope_id)
    vid = _slug_vault_id(vault_id)
    if not vid:
        return False
    ensure_registry()
    sysdb = duckdb.connect(str(system_db_path()), read_only=False)
    was_active = False
    try:
        row = sysdb.execute(
            """
            SELECT is_active FROM main.user_vaults
            WHERE user_id = ? AND scope_id = ? AND vault_id = ?
            LIMIT 1
            """,
            [uid, sid, vid],
        ).fetchone()
        if not row:
            return False
        was_active = bool(row[0])
        sysdb.execute(
            "DELETE FROM main.user_vaults WHERE user_id = ? AND scope_id = ? AND vault_id = ?",
            [uid, sid, vid],
        )
    finally:
        sysdb.close()
    try:
        vault_file_path(uid, vid).unlink(missing_ok=True)
    except Exception:
        pass
    if was_active:
        _bootstrap_default_if_missing(uid, sid)
    return True


def validate_user_db_path(user_id: Any, db_path: str, tenant_id: Any | None = None) -> bool:
    """
    Acepta rutas .duckdb bajo el árbol ``db/`` del repo, con comprobación por usuario
    cuando la ruta está bajo private/ o shared/ (no en la raíz de db/).

    Archivos en la raíz de ``db/`` (p. ej. ``duckclaw.duckdb``, ACL del gateway) son válidos
    para el consumidor singleton (mensajes ya filtrados en el Gateway).
    """
    path = Path(db_path).expanduser().resolve()
    if path.suffix.lower() != ".duckdb":
        return False
    db_r = db_root().resolve()
    try:
        rel = path.relative_to(db_r)
    except ValueError:
        return False
    if len(rel.parts) == 1:
        return True
    uid = _safe_user_id(user_id)
    private_root = user_vault_dir(uid).resolve()
    roots: list[Path] = [
        private_root,
        (db_root() / "shared" / uid).resolve(),
    ]
    if tenant_id is not None and str(tenant_id).strip():
        tid = _safe_user_id(tenant_id)
        if tid:
            roots.append((db_root() / "shared" / tid).resolve())
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def shared_tenant_dir(tenant_id: Any) -> Path:
    """Directorio db/shared/{tenant_slug}/ (mkdir incluso si aún no hay .duckdb)."""
    path = db_root() / "shared" / _safe_user_id(tenant_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
