#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Run the installation steps in START_HERE.md first.'
  exit 1
fi
exec .venv/bin/python store_app.py
