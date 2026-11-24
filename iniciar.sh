#!/bin/bash
# Demo local de ReyBasar: crea el entorno la primera vez y arranca en http://localhost:8020
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt   # instala lo que falte (rápido si ya está todo)
REYBASAR_DEMO=1 exec .venv/bin/uvicorn app.main:app --reload --port 8020
