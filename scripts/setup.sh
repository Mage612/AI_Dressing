#!/bin/sh
set -eu

cd /code
mkdir -p backend/uploads
pip install --no-cache-dir -r backend/requirements-prod.txt
