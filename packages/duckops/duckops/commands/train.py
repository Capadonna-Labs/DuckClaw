"""Comando train: SFT (LoRA) con MLX y guardrail PM2 (Apple Silicon / memoria unificada)."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

import typer

app = typer.Typer()


def _repo_root() -> Path:
    """Raíz del monorepo."""
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _agents_root() -> Path:
    """Raíz del paquete agents (cwd recomendado para train_sft y rutas relativas en env)."""
    return _repo_root() / "packages" / "agents"


def _train_sft_path() -> Path:
    return _agents_root() / "train" / "train_sft.py"


def _parse_yaml_scalar(cfg_path: Path, key: str) -> str | None:
    """Lee una clave `key:` sin PyYAML (primera coincidencia, ignora comentarios de línea)."""
    prefix = f"{key}:"
    try:
        text = cfg_path.read_text(encoding="utf-8")
    except OSError:
        return None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.lower().startswith(prefix.lower()):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def _is_likely_filesystem_model(model: str) -> bool:
    s = (model or "").strip()
    if not s:
        return False
    if s.startswith(("/", "~/", "./")):
        return True
    if len(s) >= 2 and s[1] == ":":  # Windows drive
        return True
    return False


def _resolve_model_path(model: str, repo: Path) -> Path:
    p = Path(model).expanduser()
    if not p.is_absolute():
        p = (repo / p).resolve()
    return p


def _mlx_lm_version_tuple() -> tuple[int, int, int] | None:
    try:
        v = pkg_version("mlx-lm")
    except PackageNotFoundError:
        return None
    nums: list[int] = []
    for seg in v.split(".")[:3]:
        digits = "".join(c for c in seg if c.isdigit())
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def _mlx_lm_meets_minimum(minimum: tuple[int, int, int]) -> bool:
    got = _mlx_lm_version_tuple()
    return got is not None and got >= minimum


def _lora_target_is_gemma4(model_raw: str, repo: Path) -> bool:
    """Checkpoints Gemma 4 usan model_type gemma4; mlx-lm < 0.31.2 no incluye mlx_lm.models.gemma4."""
    s = (model_raw or "").lower()
    if "gemma-4" in s or "gemma4" in s:
        return True
    if not _is_likely_filesystem_model(model_raw):
        return False
    cfg = _resolve_model_path(model_raw, repo) / "config.json"
    if not cfg.is_file():
        return False
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return data.get("model_type") == "gemma4"
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def _validate_mlx_lm_version_for_gemma4(cfg_path: Path, repo: Path) -> None:
    model_raw = _parse_yaml_scalar(cfg_path, "model")
    if not model_raw or not _lora_target_is_gemma4(model_raw, repo):
        return
    if _mlx_lm_meets_minimum((0, 31, 2)):
        return
    ver = _mlx_lm_version_tuple()
    shown = ".".join(str(x) for x in ver) if ver else "no instalada"
    typer.secho(
        "Gemma 4 requiere mlx-lm >= 0.31.2 (módulo mlx_lm.models.gemma4).\n"
        f"  Versión actual: {shown}\n"
        "  pip install -U 'mlx-lm>=0.31.2'\n"
        "Ver specs/features/Formateo de Datasets (SFT & GRPO).md §5.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(1)


def _validate_lora_config_model(cfg_path: Path, repo: Path) -> None:
    """
    mlx_lm solo usa rutas locales si existen; si no, interpreta el string como repo HF
    y huggingface_hub valida el formato → error confuso para paths rotos.
    """
    model_raw = _parse_yaml_scalar(cfg_path, "model")
    if not model_raw:
        return
    likely_local = _is_likely_filesystem_model(model_raw)
    exists = False
    resolved = ""
    if likely_local:
        rp = _resolve_model_path(model_raw, repo)
        resolved = str(rp)
        exists = rp.exists()
    if likely_local and not exists:
        typer.secho(
            "La clave `model` en el YAML apunta a una ruta local que no existe.\n"
            "mlx_lm intentaría descargarla como repo de Hugging Face y fallará.\n"
            f"  Ruta resuelta: {resolved or model_raw}\n"
            "Opciones: crea esa carpeta con el modelo MLX, o usa un id HF "
            "(ej. deadbydawn101/gemma-4-E4B-mlx-4bit).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)


def _is_likely_hf_hub_dataset_id(data_raw: str) -> bool:
    """
    mlx_lm usa dataset local solo si Path(data).exists() como directorio; si no, asume id HF.
    Heurística: ids típicos son namespace/model (exactamente un '/'). Rutas tipo packages/... no son HF.
    """
    s = (data_raw or "").strip().strip('"').strip("'")
    if not s or s.startswith(("/", "./", "../", "~/")):
        return False
    parts = [p for p in s.split("/") if p]
    if len(parts) != 2:
        return False
    if parts[0] in ("packages", "train", "config", "scripts", "services", "specs"):
        return False
    return True


def _validate_lora_config_data(cfg_path: Path, repo: Path) -> None:
    """mlx_lm espera un directorio local con train.jsonl (y opcionalmente valid/test)."""
    data_raw = _parse_yaml_scalar(cfg_path, "data")
    if not data_raw:
        return
    p = Path(data_raw)
    resolved = p.expanduser().resolve() if p.is_absolute() else (repo / p).resolve()

    if resolved.is_dir():
        train_jsonl = resolved / "train.jsonl"
        if not train_jsonl.is_file():
            typer.secho(
                "La clave `data` apunta a un directorio local sin train.jsonl.\n"
                "mlx_lm requiere al menos train.jsonl (ver train_sft.py → gemma4/sft_data_dir).\n"
                f"  Directorio: {resolved}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        return

    if resolved.is_file():
        typer.secho(
            "La clave `data` debe ser un directorio con train.jsonl, no un archivo.\n"
            f"  Recibido: {resolved}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    if not _is_likely_hf_hub_dataset_id(data_raw):
        typer.secho(
            "La clave `data` parece una ruta de proyecto pero el directorio no existe.\n"
            "Si no existe, mlx_lm lo trata como dataset de Hugging Face y falla.\n"
            f"  Ruta resuelta: {resolved}\n"
            "Crea el directorio y train.jsonl, p. ej. ejecutando:\n"
            "  python packages/agents/train/train_sft.py\n"
            "o copia packages/agents/train/gemma4/dataset_sft.jsonl → …/sft_data_dir/train.jsonl",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)


def _pm2_run(args: list[str]) -> int:
    """Ejecuta pm2; no lanza. Devuelve código de salida (127 si pm2 no existe)."""
    try:
        r = subprocess.run(["pm2", *args], check=False, capture_output=True, text=True)
    except FileNotFoundError:
        typer.secho(
            "pm2 no está en PATH; omite guardrail o instala PM2.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return 127
    if r.returncode != 0 and r.stderr:
        typer.secho(f"pm2 {' '.join(args)}: {r.stderr.strip()}", fg=typer.colors.YELLOW, err=True)
    return r.returncode


@app.callback(invoke_without_command=True)
def cmd_train(
    ctx: typer.Context,
    config: str | None = typer.Option(
        None,
        "--config",
        "-c",
        help="YAML para `python -m mlx_lm.lora --config` (alternativa al script train_sft.py).",
    ),
    auto_suspend: bool = typer.Option(
        True,
        "--auto-suspend/--no-auto-suspend",
        help="Detiene PM2 antes del entrenamiento y lo restaura al final (libera memoria unificada).",
    ),
) -> None:
    """Pipeline SFT (LoRA) con MLX; sin --config usa packages/agents/train/train_sft.py."""
    if ctx.invoked_subcommand is not None:
        return

    repo = _repo_root()
    agents = _agents_root()

    if auto_suspend:
        typer.echo("Suspendiendo workers PM2 (liberar memoria unificada)...")
        _pm2_run(["stop", "all"])

    exit_code = 0
    try:
        if config:
            cfg_path = Path(config).expanduser()
            if not cfg_path.is_absolute():
                cfg_path = (repo / cfg_path).resolve()
            if not cfg_path.is_file():
                typer.secho(f"No existe el archivo de configuración: {cfg_path}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1)
            _validate_lora_config_model(cfg_path, repo)
            _validate_mlx_lm_version_for_gemma4(cfg_path, repo)
            _validate_lora_config_data(cfg_path, repo)
            # Parche tqdm en el bucle de entrenamiento + mlx_lm.lora (ver duckops.mlx_lora_runner).
            cmd = [
                sys.executable,
                "-m",
                "duckops.mlx_lora_runner",
                "--config",
                str(cfg_path),
            ]
            typer.echo(f"Ejecutando: {' '.join(cmd)}")
            subprocess.run(cmd, cwd=str(repo), check=True)
        else:
            script = _train_sft_path()
            if not script.is_file():
                typer.secho(f"No se encontró train_sft.py: {script}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1)
            cmd = [sys.executable, str(script)]
            typer.echo(f"Ejecutando train_sft (cwd={agents}): {' '.join(cmd)}")
            subprocess.run(cmd, cwd=str(agents), check=True)
        typer.secho("Entrenamiento completado.", fg=typer.colors.GREEN)
    except subprocess.CalledProcessError as e:
        exit_code = e.returncode
        typer.secho(f"Fallo del entrenamiento (exit {e.returncode}).", fg=typer.colors.RED, err=True)
    finally:
        if auto_suspend:
            typer.echo("Restaurando workers PM2...")
            pm2_rc = _pm2_run(["start", "all"])
            if pm2_rc != 0:
                typer.secho(
                    f"Advertencia: pm2 start all devolvió código {pm2_rc} (revisa procesos a mano).",
                    fg=typer.colors.YELLOW,
                    err=True,
                )

    if exit_code != 0:
        raise typer.Exit(exit_code)
