#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/Desktop/duckclaw"
cp -a .env ".env.bak.$(date +%Y%m%d%H%M%S)"
perl -pi -e 's/87\.99\.156\.231/100.75.4.17/g' .env
perl -pi -e 's/^CAPADONNA_REMOTE_OHLC_CMD=.*/CAPADONNA_REMOTE_OHLC_CMD=CAPADONNA_LAKE_DATA_ROOT=\/root\/duckclaw\/data\/lake \/root\/duckclaw\/.venv\/bin\/python \/root\/duckclaw\/scripts\/export_lake_ohlcv.py {ticker} {timeframe} {lookback_days}/' .env
grep -q '^CAPADONNA_SSH_USER=' .env || echo 'CAPADONNA_SSH_USER=root' >> .env
echo "=== .env IBKR block ==="
grep -E '^IBKR_|^CAPADONNA_' .env
