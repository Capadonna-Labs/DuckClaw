"""Duckops knowledge — espejo local de bóveda y checks offline."""

from __future__ import annotations

import typer

app = typer.Typer(help="Bóveda / conocimiento offline (espejo local, Kiwix).")


@app.command("mirror")
def cmd_mirror(
    delete: bool = typer.Option(
        False,
        "--delete",
        help="rsync --delete: el espejo queda idéntico al origen (borra extras locales).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Simular sin escribir.",
    ),
) -> None:
    """Sincroniza DUCKCLAW_VAULT_SOURCE_DIR → DUCKCLAW_VAULT_MIRROR_DIR."""
    from duckclaw.vault_mirror import run_vault_mirror, vault_mirror_dir, vault_source_dir

    src = vault_source_dir()
    dst = vault_mirror_dir()
    typer.echo(f"Origen:  {src or '(no configurado)'}")
    typer.echo(f"Espejo:  {dst or '(no configurado)'}")
    result = run_vault_mirror(delete=delete, dry_run=dry_run)
    if result.ok:
        typer.secho(f"OK · {result.detail}", fg=typer.colors.GREEN)
        if result.bytes_hint:
            typer.echo(result.bytes_hint)
        raise typer.Exit(0)
    typer.secho(f"FAIL · {result.detail}", fg=typer.colors.RED)
    raise typer.Exit(1)


@app.command("status")
def cmd_status() -> None:
    """Estado de espejo vault + ZIMs Kiwix."""
    from duckclaw.vault_mirror import (
        kiwix_zim_dir,
        list_zim_files,
        vault_mirror_dir,
        vault_source_dir,
    )

    src = vault_source_dir()
    mirror = vault_mirror_dir()
    zim_dir = kiwix_zim_dir()
    typer.echo(f"VAULT_SOURCE: {'OK ' + str(src) if src and src.is_dir() else 'MISSING ' + str(src)}")
    typer.echo(
        f"VAULT_MIRROR: {'OK ' + str(mirror) if mirror and mirror.is_dir() else 'MISSING ' + str(mirror)}"
    )
    if zim_dir is None:
        typer.echo("KIWIX_ZIM_DIR: (no configurado)")
    else:
        zims = list_zim_files(zim_dir)
        typer.echo(f"KIWIX_ZIM_DIR: {zim_dir} · {len(zims)} archivo(s) .zim")
        for z in zims[:20]:
            typer.echo(f"  - {z.name}")
