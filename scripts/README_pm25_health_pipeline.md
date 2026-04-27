# Pipeline PM2.5 vs salud (Valle de Aburrá)

Scripts para extraer datos por API, construir dataset integrado y generar 3 gráficas:

- Scatter PM2.5 vs enfermedades respiratorias.
- Serie temporal PM2.5 con periodos críticos.
- Boxplot PM2.5 por zonas.

## Requisitos

- Python con `pandas`, `requests`, `matplotlib`, `seaborn`, `pyarrow`.
- Opcional: `OPENAQ_API_KEY`.
- Opcional: `IDEAM_ENV_DATA_URL` (si no pasas `--url` en script IDEAM).

## 1) Extracción de datos

```bash
python scripts/data_fetch/fetch_pm25_openaq.py \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --output-dir data/raw/openaq \
  --city "Medellín" \
  --country CO
```

```bash
python scripts/data_fetch/fetch_pm25_siata.py \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --output-dir data/raw/siata
```

```bash
python scripts/data_fetch/fetch_env_ideam.py \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --output-dir data/raw/ideam \
  --url "$IDEAM_ENV_DATA_URL"
```

## 2) Construcción de dataset maestro

Si todavía no tienes salud oficial, omite `--health-file` y el pipeline genera `resp_cases` proxy.

```bash
python scripts/data_prep/build_master_dataset.py \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --openaq-file data/raw/openaq/openaq_pm25_2018-01-01_2024-12-31.parquet \
  --siata-file data/raw/siata/siata_pm25_2018-01-01_2024-12-31.parquet \
  --ideam-file data/raw/ideam/ideam_env_2018-01-01_2024-12-31.parquet \
  --output-dir data/processed
```

Con salud real:

```bash
python scripts/data_prep/build_master_dataset.py \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --openaq-file data/raw/openaq/openaq_pm25_2018-01-01_2024-12-31.parquet \
  --siata-file data/raw/siata/siata_pm25_2018-01-01_2024-12-31.parquet \
  --health-file data/raw/salud/respiratorias_2018_2024.csv \
  --output-dir data/processed
```

Salida principal:

- `data/processed/master_2018_2024.parquet`
- `data/processed/metadata_summary.json`

## 3) Gráficas

```bash
python scripts/plots/plot_scatter_pm25_vs_resp.py \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --master-file data/processed/master_2018_2024.parquet \
  --output-dir reports/figures
```

```bash
python scripts/plots/plot_timeseries_pm25_alerts.py \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --master-file data/processed/master_2018_2024.parquet \
  --output-dir reports/figures
```

```bash
python scripts/plots/plot_boxplot_by_zone.py \
  --start-date 2018-01-01 \
  --end-date 2024-12-31 \
  --master-file data/processed/master_2018_2024.parquet \
  --output-dir reports/figures \
  --top-n 10
```

## Contrato de salud esperado

Columnas mínimas para salud real:

- `date` (o `fecha`)
- `zone` (o `zona`, `municipio`)
- `resp_cases` (o equivalente, por ejemplo `enfermedades_respiratorias`)

Opcional:

- `population`
