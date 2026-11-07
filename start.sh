#!/usr/bin/env bash
# One-command start: creates .venv on first use, installs dependencies, then runs the project.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null; then
      "$candidate" -m venv .venv
      break
    fi
  done
  .venv/bin/pip install -q --retries 10 --timeout 60 -r requirements.txt
fi
exec .venv/bin/python run.py "$@"
