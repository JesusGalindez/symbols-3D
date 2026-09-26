#!/bin/zsh
# Doble clic: arranca el editor de símbolos y lo abre. Cierra la ventana para parar.
cd "$(dirname "$0")"
(sleep 1; open "http://localhost:8792/editor.html${1:+?s=$1}") &
exec .venv/bin/python tools/editor.py
