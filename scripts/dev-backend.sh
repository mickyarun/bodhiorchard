#!/usr/bin/env bash
# Launches the backend dev server via backend/dev_server.py, which decides
# whether to enable uvicorn's --reload per-platform (see that file for why
# it's disabled on native Windows). This script only resolves the venv's
# python interpreter, since the venv layout itself differs by platform
# (.venv/bin on macOS/Linux, .venv/Scripts on native Windows).
set -euo pipefail
cd "$(dirname "$0")/../backend"

if [ -x .venv/Scripts/python.exe ]; then
  PYTHON=.venv/Scripts/python.exe
else
  PYTHON=.venv/bin/python
fi

exec "$PYTHON" dev_server.py
