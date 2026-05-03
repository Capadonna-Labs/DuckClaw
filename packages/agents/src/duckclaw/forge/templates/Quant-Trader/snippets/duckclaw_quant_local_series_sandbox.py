# Snippet: leer tabla local parquet/CSV bajo `/workspace/data/` sin ml4t-data (solo DuckDB+Pandas ya en imagen).
#
# Ej.: exportación previa desde host montada RO. Ajustar GLOB y columnas esperadas según archivo.
#
# No abrir vault Duck del usuario dentro del sandbox; solo ficheros datos explícitos montados.

import glob
import json
from pathlib import Path

import pandas as pd


def load_first_parquet_under_data() -> pd.DataFrame:
    candidates = sorted(glob.glob(str(Path("/workspace/data") / "*.parquet")))
    if not candidates:
        raise FileNotFoundError("no parquet in /workspace/data")
    return pd.read_parquet(candidates[0])


def main() -> None:
    df = load_first_parquet_under_data()
    cols = sorted(df.columns.astype(str).tolist())
    print(
        json.dumps(
            {"ok": True, "columns": cols, "n_rows": int(df.shape[0]), "hint": "use ml4t diagnostic on derived returns in next cell"},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()