"""Exercise handle backfill on an isolated, temporary local MySQL instance.

Does not connect to or modify the application's development database. Runtime
credentials stay in memory; only safe aggregate results are printed.
"""

from pathlib import Path
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

BACKEND = Path(__file__).resolve().parents[1]
MYSQLD = Path(r"C:\Program Files\MySQL\MySQL Server 9.4\bin\mysqld.exe")


def main() -> int:
    if not MYSQLD.is_file():
        print("ENVIRONMENT BLOCKED: local mysqld executable unavailable.")
        return 1
    # This exact generated directory is the only recursive-cleanup target.
    with tempfile.TemporaryDirectory(prefix="unishop-handle-migration-") as temporary:
        directory = Path(temporary).resolve()
        assert directory.parent == Path(tempfile.gettempdir()).resolve()
        data = directory / "data"
        base_args = [str(MYSQLD), "--no-defaults", f"--datadir={data}", "--skip-log-bin"]
        initialized = subprocess.run(
            [*base_args, "--initialize-insecure"], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if initialized.returncode:
            print("ENVIRONMENT BLOCKED: isolated MySQL initialization failed.")
            return 1
        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]
        process = subprocess.Popen(
            [*base_args, "--bind-address=127.0.0.1", f"--port={port}", "--mysqlx=0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        password = secrets.token_urlsafe(32)
        root_password = secrets.token_urlsafe(32)
        root_engine = create_engine(URL.create("mysql+pymysql", username="root",
                                              host="127.0.0.1", port=port))
        app_engine = None
        stage = "startup"
        try:
            for _ in range(150):
                try:
                    with root_engine.connect() as connection:
                        connection.execute(text("SELECT 1"))
                    break
                except Exception:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Isolated server unavailable")
            stage = "isolated provisioning"
            with root_engine.begin() as connection:
                connection.execute(text("CREATE DATABASE unishop_china"))
                connection.execute(text("CREATE USER 'unishop_app'@'localhost' IDENTIFIED BY :p"),
                                   {"p": password})
                connection.execute(text("GRANT ALL PRIVILEGES ON unishop_china.* "
                                        "TO 'unishop_app'@'localhost'"))
                connection.execute(text("ALTER USER 'root'@'localhost' IDENTIFIED BY :p"),
                                   {"p": root_password})
            root_engine.dispose()
            root_engine = create_engine(URL.create("mysql+pymysql", username="root",
                                                  password=root_password,
                                                  host="127.0.0.1", port=port))
            url = URL.create("mysql+pymysql", username="unishop_app", password=password,
                             host="127.0.0.1", port=port, database="unishop_china",
                             query={"charset": "utf8mb4"})
            env = os.environ.copy()
            env["DATABASE_URL"] = url.render_as_string(hide_password=False)
            env["APP_ENV"] = "development"

            def alembic(*arguments, expect_failure=False):
                completed = subprocess.run(
                    [sys.executable, "-m", "alembic", *arguments], cwd=BACKEND,
                    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=60,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if (completed.returncode != 0) != expect_failure:
                    # Only disposable-schema diagnostics; never print connection URLs,
                    # SQL parameters or the runtime-only provisioning credentials.
                    for line in completed.stderr.splitlines():
                        if line.startswith(("sqlalchemy.exc.", "RuntimeError:")):
                            print(line.split("[SQL:", 1)[0].replace(password, "[redacted]")
                                  .replace(root_password, "[redacted]")[:400])
                    raise RuntimeError("Isolated Alembic operation failed")

            stage = "baseline migration"
            alembic("upgrade", "f6a1b2c3d4e5")
            app_engine = create_engine(url, pool_pre_ping=True)
            with app_engine.begin() as connection:
                for index, display_name in enumerate((None, "Existing Public Name", "\u5f20\u4f1f")):
                    user_id = str(uuid4())
                    connection.execute(text(
                        "INSERT INTO users (id,email,password_hash,created_at,updated_at) "
                        "VALUES (:id,:email,'synthetic-unused',NOW(),NOW())"
                    ), {"id": user_id, "email": f"migration-{index}@example.test"})
                    connection.execute(text(
                        "INSERT INTO user_profiles "
                        "(id,user_id,public_id,display_name,city,created_at,updated_at) "
                        "VALUES (:id,:user_id,:public_id,:display_name,:city,NOW(),NOW())"
                    ), {"id": str(uuid4()), "user_id": user_id, "public_id": str(uuid4()),
                        "display_name": display_name, "city": (None, "Qingdao", "Hangzhou")[index]})
                baseline = connection.execute(text("SELECT * FROM users ORDER BY id")).all()
                profiles = connection.execute(text("SELECT * FROM user_profiles ORDER BY id")).all()
                columns = list(profiles[0]._mapping)

            def preserved():
                with app_engine.connect() as connection:
                    assert connection.execute(text("SELECT * FROM users ORDER BY id")).all() == baseline
                    # Column names originate only from reflected test schema, never input.
                    statement = "SELECT " + ",".join(columns) + " FROM user_profiles ORDER BY id"
                    assert connection.execute(text(statement)).all() == profiles

            stage = "upgrade and backfill"
            alembic("upgrade", "head")
            preserved()
            with app_engine.connect() as connection:
                handles = list(connection.scalars(text("SELECT public_handle FROM user_profiles")))
                assert len(handles) == len(set(handles)) == 3
                assert all(len(h) == 25 and h.startswith("user-") for h in handles)
            if "--catalog" in sys.argv:
                stage = "catalog isolated backfill and round-trip"
                with app_engine.connect() as connection:
                    assert connection.scalar(text("SELECT COUNT(*) FROM cities")) == 6
                    assert connection.scalar(text("SELECT COUNT(*) FROM user_profiles p JOIN cities c "
                                                   "ON c.id=p.city_id WHERE BINARY p.city=BINARY c.name_en")) == 2
                alembic("downgrade", "c7d8e9f0a1b2")
                preserved()
                # Simulate unknown legacy data only inside this disposable server.
                # The upgrade must refuse BEFORE creating any Phase 8 table.
                with app_engine.begin() as connection:
                    connection.execute(text("ALTER TABLE user_profiles ALTER CHECK ck_user_profiles_supported_city NOT ENFORCED"))
                    connection.execute(text("UPDATE user_profiles SET city='Unmapped Synthetic' WHERE city='Qingdao'"))
                alembic("upgrade", "head", expect_failure=True)
                with app_engine.begin() as connection:
                    assert connection.scalar(text("SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema=DATABASE() AND table_name='cities'")) == 0
                    connection.execute(text("UPDATE user_profiles SET city='Qingdao' WHERE city='Unmapped Synthetic'"))
                    connection.execute(text("ALTER TABLE user_profiles ALTER CHECK ck_user_profiles_supported_city ENFORCED"))
                alembic("upgrade", "head")
                preserved()
                alembic("check")
                print(json.dumps({"catalog_cycle": "PASS", "seed_cities": 6,
                                  "mapped_profiles": 2, "unknown_city_refused_before_ddl": True,
                                  "existing_profile_data_preserved": True}))
            if "--seller-verification" in sys.argv:
                stage = "seller verification isolated cycle"
                with app_engine.begin() as connection:
                    owner = connection.scalar(text("SELECT id FROM users ORDER BY id LIMIT 1"))
                    connection.execute(text(
                        "INSERT INTO seller_verifications "
                        "(id,user_id,review_reference,status,handwritten_challenge,challenge_expires_at,created_at,updated_at) "
                        "VALUES (:id,:owner,:reference,'PENDING','SYNTHETIC123',DATE_ADD(NOW(),INTERVAL 10 MINUTE),NOW(),NOW())"
                    ), {"id": str(uuid4()), "owner": owner, "reference": secrets.token_hex(16)})
                    assert connection.scalar(text("SELECT COUNT(*) FROM seller_verifications")) == 1
                    seller_baseline = connection.execute(text(
                        "SELECT id,user_id,review_reference,status,handwritten_challenge,created_at,updated_at "
                        "FROM seller_verifications")).all()
                alembic("downgrade", "b7c1d2e3f4a5")
                alembic("upgrade", "head")
                with app_engine.connect() as connection:
                    assert connection.execute(text(
                        "SELECT id,user_id,review_reference,status,handwritten_challenge,created_at,updated_at "
                        "FROM seller_verifications")).all() == seller_baseline
                    assert connection.scalar(text("SELECT COUNT(*) FROM seller_verifications "
                                                  "WHERE challenge_expires_at IS NULL")) == 0
                print(json.dumps({"challenge_expiry_cycle": "PASS", "seller_data_preserved": True}))
                alembic("downgrade", "a61b2c3d4e5f")
                preserved()
                alembic("upgrade", "head")
                preserved()
                with app_engine.connect() as connection:
                    for name in ("seller_verifications", "seller_evidence", "seller_verification_audit"):
                        assert connection.scalar(text("SELECT COUNT(*) FROM " + name)) == 0
                print(json.dumps({"seller_verification_cycle": "PASS", "prior_data_preserved": True}))
            stage = "downgrade"
            alembic("downgrade", "f6a1b2c3d4e5")
            preserved()
            stage = "second upgrade"
            alembic("upgrade", "head")
            preserved()
            stage = "no drift"
            alembic("check")
            if "--seller-verification" in sys.argv:
                # This instance and every profile in it are owned by this script.
                # Phase 6 downgrade intentionally drops ONLY its synthetic profiles.
                stage = "phase 6 isolated downgrade"
                alembic("downgrade", "d5f0c1e2a3b4")
                with app_engine.connect() as connection:
                    assert connection.execute(text("SELECT * FROM users ORDER BY id")).all() == baseline
                    assert connection.scalar(text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema=DATABASE() AND table_name='user_profiles'")) == 0
                alembic("upgrade", "head")
                alembic("check")
                with app_engine.connect() as connection:
                    assert connection.execute(text("SELECT * FROM users ORDER BY id")).all() == baseline
                    assert connection.scalar(text("SELECT COUNT(*) FROM user_profiles")) == 0
                print(json.dumps({"phase_6_cycle": "PASS", "authentication_data_preserved": True}))
            print(json.dumps({"isolated_mysql": "PASS", "backfill_rows": 3,
                              "upgrade": "PASS", "downgrade": "PASS", "upgrade_again": "PASS",
                              "preservation": True, "drift": False}))
            return 0
        except Exception as error:
            print(json.dumps({"status": "FAIL", "stage": stage,
                              "error_type": type(error).__name__}))
            return 1
        finally:
            if app_engine is not None:
                app_engine.dispose()
            try:
                with root_engine.connect() as connection:
                    connection.execute(text("SHUTDOWN"))
            except Exception:
                pass
            root_engine.dispose()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
