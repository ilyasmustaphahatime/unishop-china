"""Disposable native MySQL migration gate; never downgrades the development server.

Run with --mysqld <installed mysqld executable>. Creates a fresh temporary datadir,
uses a random loopback port, creates synthetic credentials, and stops only its own
child process. No .env, system service or existing datadir is changed.
"""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time

import pymysql
from sqlalchemy import URL, create_engine, inspect, select
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
OLD, NEW = "d13e4f5a6b7c", "e14f5a6b7c8d"


@contextmanager
def disposable_server(binary):
    binary = Path(binary).resolve(strict=True)
    if binary.name.lower() != "mysqld.exe":
        raise RuntimeError("Expected an installed Windows mysqld executable.")
    with tempfile.TemporaryDirectory(prefix="unishop-phase14-mysql-") as directory:
        data = Path(directory).resolve()
        assert data.parent == Path(tempfile.gettempdir()).resolve()
        assert data.name.startswith("unishop-phase14-mysql-")
        base = [str(binary), "--no-defaults", "--basedir="+str(binary.parent.parent), "--datadir="+str(data)]
        initialized = subprocess.run(base + ["--initialize-insecure", "--console"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if initialized.returncode:
            raise RuntimeError("Disposable MySQL initialization failed.")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        if port == 3306:
            raise RuntimeError("Refusing the development port.")
        process = subprocess.Popen(base + ["--port="+str(port), "--bind-address=127.0.0.1", "--mysqlx=OFF",
            "--skip-log-bin", "--innodb-buffer-pool-size=134217728", "--console"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        connection = None
        try:
            deadline = time.monotonic()+45
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    connection = pymysql.connect(host="127.0.0.1", port=port, user="root", password="", connect_timeout=2, autocommit=True)
                    break
                except pymysql.MySQLError:
                    time.sleep(.2)
            if connection is None:
                raise RuntimeError("Disposable MySQL readiness failed.")
            password = secrets.token_urlsafe(36)
            with connection.cursor() as cursor:
                cursor.execute("CREATE DATABASE unishop_china CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
                cursor.execute("CREATE USER 'unishop_app'@'127.0.0.1' IDENTIFIED BY %s", (password,))
                cursor.execute("GRANT ALL PRIVILEGES ON unishop_china.* TO 'unishop_app'@'127.0.0.1'")
                # The blank root password exists only during new local bootstrap.
                cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (secrets.token_urlsafe(36),))
            url = URL.create("mysql+pymysql", username="unishop_app", password=password,
                             host="127.0.0.1", port=port, database="unishop_china", query={"charset": "utf8mb4"})
            yield url
        finally:
            if connection is not None:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SHUTDOWN")
                except pymysql.MySQLError:
                    pass
                connection.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysqld", required=True)
    args = parser.parse_args()
    with disposable_server(args.mysqld) as url:
        # Import application modules only AFTER isolating database configuration.
        os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False), APP_ENV="development")
        from alembic import command
        from alembic.config import Config
        from app.core.database import engine
        from app.models import Deal, Offer
        from app.services.offer_service import OfferService
        from scripts.personalization_http_checks import database_fingerprint
        from tests.fixtures.conversations import chat_config
        from tests.fixtures.offers import seed_offer_world
        assert engine.url.port == url.port and engine.url.port != 3306
        config = Config(str(BACKEND / "alembic.ini"))
        command.upgrade(config, OLD)
        with engine.connect() as connection:
            prior_names = inspect(connection).get_table_names()
            prior_schema = {name: connection.exec_driver_sql("SHOW CREATE TABLE `"+name+"`").first()[1] for name in prior_names}
        with Session(engine, expire_on_commit=False) as db, db.begin():
            world, refs = seed_offer_world(db)
        prior = database_fingerprint()
        command.upgrade(config, NEW)
        command.check(config)
        after = database_fingerprint()
        assert all(prior[n] == after[n] for n in prior if n != "alembic_version")
        with Session(engine) as db:
            service = OfferService(db, chat_config())
            result, created = service.create(world.buyer.id, dict(conversation_ref=refs[0], amount="123.45",
                client_offer_id="00000000-0000-4000-8000-000000000001"))
            assert created
            service.transition(world.seller.id, result.offer_ref, "accept")
        before_down = database_fingerprint()
        command.downgrade(config, OLD)
        down = database_fingerprint()
        assert "offers" not in down and "deals" not in down
        assert all(before_down[n] == down[n] for n in down if n != "alembic_version")
        with engine.connect() as connection:
            assert all(connection.exec_driver_sql("SHOW CREATE TABLE `"+n+"`").first()[1] == prior_schema[n] for n in prior_names)
        command.upgrade(config, NEW)
        command.check(config)
        after = database_fingerprint()
        assert all(down[n] == after[n] for n in down if n != "alembic_version")
        with Session(engine) as db:
            assert db.scalar(select(Offer.id)) is None and db.scalar(select(Deal.id)) is None
        with create_engine(url).connect() as connection:
            version = connection.exec_driver_sql("SELECT VERSION()").scalar()
        engine.dispose()
        print(f"PASS isolated MySQL {version}: base -> {OLD} -> {NEW} -> {OLD} -> {NEW}; no drift; prior data/schema preserved")


if __name__ == "__main__":
    main()
