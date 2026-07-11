#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE="${ROOT}/integrations/edge-devices/native"
cd "${NATIVE}"
if [[ "$(uname -s)" == "Darwin" ]]; then
  g++ -O3 -shared -fPIC -std=c++14 edge_core.cpp -o libedgecore.dylib
  echo "OK: integrations/edge-devices/native/libedgecore.dylib"
else
  g++ -O3 -shared -fPIC -std=c++14 edge_core.cpp -o libedgecore.so
  echo "OK: integrations/edge-devices/native/libedgecore.so"
fi
