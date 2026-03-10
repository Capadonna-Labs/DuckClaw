#!/usr/bin/env bash
# Monta /tmp/duckclaw_media en tmpfs (RAM) para Habeas Data.
# Los archivos de voz nunca se escriben en SSD.
# Uso: sudo ./scripts/setup_media_tmpfs.sh

MEDIA_DIR="${DUCKCLAW_MEDIA_DIR:-/tmp/duckclaw_media}"
SIZE="64M"

mkdir -p "$MEDIA_DIR"
if ! mount | grep -q "$MEDIA_DIR"; then
  mount -t tmpfs -o size=$SIZE tmpfs "$MEDIA_DIR"
  echo "Montado tmpfs en $MEDIA_DIR ($SIZE)"
else
  echo "$MEDIA_DIR ya está montado"
fi
