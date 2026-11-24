#!/bin/bash
# Descarga las fotos de categoría (Unsplash, licencia libre) para servirlas desde el propio sitio.
# Correr desde la Terminal de tu Mac:  bash diseno/descargar_fotos.sh
cd "$(dirname "$0")/.."
destino=app/static/img/categorias
declare -a fotos=(
  "dama 1612423284934-2850a4ea6b0f 1000"
  "caballero 1489987707025-afc232f7ea0f 800"
  "ninas 1622290291720-ac961c43ee30 800"
  "ninos 1622290319146-7b63df48a635 800"
  "juguetes 1596461404969-9ae70f2830c1 800"
  "otros 1540221652346-e5dd6b50f3e7 800"
)
for f in "${fotos[@]}"; do
  set -- $f
  curl -sfL "https://images.unsplash.com/photo-$2?w=$3&q=78&fit=crop&fm=jpg" -o "$destino/foto-$1.jpg" && echo "✓ $1"
done
