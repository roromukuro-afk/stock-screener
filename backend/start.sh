#!/usr/bin/env bash
set -e
export PYTHONUTF8=1
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
