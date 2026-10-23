#!/usr/bin/env bash
# ==============================================================================
# Lanzador de la Interfaz de Usuario TurismoUQ (Streamlit + python-oracledb)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "⚡ Creando entorno virtual Python en $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/app/requirements.txt"
fi

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

echo "🌴 Iniciando Interfaz TurismoUQ en Streamlit..."
echo "📍 Directorio base: $SCRIPT_DIR"
"$VENV_DIR/bin/streamlit" run "$SCRIPT_DIR/app/main.py" "$@"
