#!/bin/bash
# Respaldo diario de ReyBasar: base de datos + fotos. Guarda 14 días.
# Cron (root):  15 3 * * * /srv/reybasar/app/deploy/respaldo.sh
set -e
DEST=/srv/reybasar/respaldos
HOY=$(date +%F)
mkdir -p "$DEST"
sqlite3 /srv/reybasar/data/reybasar.db ".backup '$DEST/reybasar-$HOY.db'"
gzip -f "$DEST/reybasar-$HOY.db"
tar -czf "$DEST/media-$HOY.tgz" -C /srv/reybasar media
find "$DEST" -type f -mtime +14 -delete
