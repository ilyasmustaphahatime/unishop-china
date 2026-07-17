#!/usr/bin/env sh
set -eu
cd backend
alembic upgrade head
