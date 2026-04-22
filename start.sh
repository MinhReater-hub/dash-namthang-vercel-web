#!/usr/bin/env bash
set -e
python refresh_data.py
exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers ${GUNICORN_WORKERS:-2} --timeout ${GUNICORN_TIMEOUT:-120} wsgi:app
