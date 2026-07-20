"""Rutas y sync del espejo local de la bóveda (GDrive → disco local)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def vault_source_dir() -> Path | None:
    raw = (os.environ.get("DUCKCLAW_VAULT_SOURCE_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def vault_mirror_dir() -> Path | None:
    raw = (os.environ.get("DUCKCLAW_VAULT_MIRROR_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def kiwix_zim_dir() -> Path | None:
    raw = (os.environ.get("DUCKCLAW_KIWIX_ZIM_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def list_zim_files(zim_dir: Path | None = None) -> list[Path]:
    root = zim_dir if zim_dir is not None else kiwix_zim_dir()
    if root is None or not root.is_dir():
        return []
    return sorted(p for p in root.glob("*.zim") if p.is_file())


@dataclass(frozen=True)
class VaultMirrorResult:
    ok: bool
    detail: str
    source: Path | None = None
    mirror: Path | None = None
    bytes_hint: str = ""


def run_vault_mirror(*, delete: bool = False, dry_run: bool = False) -> VaultMirrorResult:
    """
    Copia la bóveda origen → espejo local con rsync (o shutil si no hay rsync).

    Por defecto no usa ``--delete`` (seguro). Con ``delete=True`` el espejo queda exacto.
    """
    source = vault_source_dir()
    mirror = vault_mirror_dir()
    if source is None:
        return VaultMirrorResult(False, "DUCKCLAW_VAULT_SOURCE_DIR no configurado")
    if mirror is None:
        return VaultMirrorResult(False, "DUCKCLAW_VAULT_MIRROR_DIR no configurado")
    if not source.is_dir():
        return VaultMirrorResult(
            False,
            f"origen inaccesible (¿Drive offline?): {source}",
            source=source,
            mirror=mirror,
        )

    mirror.mkdir(parents=True, exist_ok=True)
    rsync = shutil.which("rsync")
    if rsync:
        cmd = [rsync, "-a", "--human-readable", "--stats"]
        if dry_run:
            cmd.append("--dry-run")
        if delete:
            cmd.append("--delete")
        cmd.extend(
            [
                "--exclude",
                ".DS_Store",
                "--exclude",
                "*/.DS_Store",
                f"{source}/",
                f"{mirror}/",
            ]
        )
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=3600,
            )
        except subprocess.TimeoutExpired:
            return VaultMirrorResult(
                False, "rsync timeout (>1h)", source=source, mirror=mirror
            )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "rsync failed")[:400]
            return VaultMirrorResult(False, err, source=source, mirror=mirror)
        stats = (proc.stdout or "").strip().splitlines()[-5:]
        return VaultMirrorResult(
            True,
            "espejo actualizado" + (" (dry-run)" if dry_run else ""),
            source=source,
            mirror=mirror,
            bytes_hint="; ".join(stats)[:300],
        )

    if dry_run:
        return VaultMirrorResult(
            True,
            "dry-run: rsync no en PATH; se usaría copytree",
            source=source,
            mirror=mirror,
        )
    # Fallback sin rsync (sin --delete fino)
    for item in source.iterdir():
        dest = mirror / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        elif item.is_file():
            shutil.copy2(item, dest)
    return VaultMirrorResult(
        True, "espejo actualizado (shutil, sin rsync)", source=source, mirror=mirror
    )
