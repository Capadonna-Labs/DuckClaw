"""
Punto de entrada para LoRA con barra tqdm: aplica el parche y delega en mlx_lm.lora.

Uso (desde duckops train): python -m duckops.mlx_lora_runner --config /ruta/lora_config.yaml
"""

from __future__ import annotations


def main() -> None:
    from duckops.mlx_train_tqdm_patch import apply_mlx_train_tqdm_patch

    apply_mlx_train_tqdm_patch()
    from mlx_lm.lora import main as lora_main

    lora_main()


if __name__ == "__main__":
    main()
