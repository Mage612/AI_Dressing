#!/bin/sh
set -eu

cd /code/backend
mkdir -p uploads
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-9000}"
