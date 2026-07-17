#!/usr/bin/env sh
set -eu
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
