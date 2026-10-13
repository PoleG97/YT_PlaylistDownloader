#!/usr/bin/env bash
# Lanzador: crea el entorno virtual la primera vez y ejecuta el descargador.
# Funciona desde cualquier carpeta, también a través de un enlace simbólico.
set -e
DIR="$(dirname "$(readlink -f "$0")")"

if [ ! -x "$DIR/.venv/bin/python" ]; then
    echo "Primera ejecución: creando entorno virtual..."
    python3 -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"
fi

exec "$DIR/.venv/bin/python" "$DIR/converter.py" "$@"
