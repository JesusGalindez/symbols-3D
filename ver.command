#!/bin/zsh
# Doble clic: sirve esta carpeta y abre el visor. Cierra la ventana para parar.
cd "$(dirname "$0")"
PUERTO=8791
(sleep 1; open "http://localhost:$PUERTO/visor.html?s=${1:-shou-circular}") &
exec .venv/bin/python -m http.server $PUERTO
