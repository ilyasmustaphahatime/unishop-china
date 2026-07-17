"""Safely verify the configured UniShop China database connection."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def failure() -> int:
    print("Database connection failed.")
    print("Review MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST and database permissions.")
    return 1


def main() -> int:
    try:
        from app.core.database import check_database_connection
    except Exception:
        return failure()

    if not check_database_connection():
        return failure()

    print("Database connection successful.")
    print("MySQL responded with: 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
