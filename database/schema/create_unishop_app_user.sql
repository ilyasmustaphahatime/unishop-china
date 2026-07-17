-- UniShop China local database application user setup.
--
-- IMPORTANT:
-- 1. Replace every REPLACE_WITH_LOCAL_PASSWORD value below with the same strong,
--    local password before running this script in MySQL Workbench.
-- 2. Put that password in backend/.env as MYSQL_PASSWORD.
-- 3. Never commit the real password or paste it into source files.
-- 4. Run this script while connected with a MySQL administrator account.

CREATE DATABASE IF NOT EXISTS unishop_china
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'unishop_app'@'localhost'
IDENTIFIED BY 'REPLACE_WITH_LOCAL_PASSWORD';

ALTER USER 'unishop_app'@'localhost'
IDENTIFIED BY 'REPLACE_WITH_LOCAL_PASSWORD';

GRANT ALL PRIVILEGES
ON unishop_china.*
TO 'unishop_app'@'localhost';

CREATE USER IF NOT EXISTS 'unishop_app'@'127.0.0.1'
IDENTIFIED BY 'REPLACE_WITH_LOCAL_PASSWORD';

ALTER USER 'unishop_app'@'127.0.0.1'
IDENTIFIED BY 'REPLACE_WITH_LOCAL_PASSWORD';

GRANT ALL PRIVILEGES
ON unishop_china.*
TO 'unishop_app'@'127.0.0.1';

FLUSH PRIVILEGES;

SHOW GRANTS FOR 'unishop_app'@'localhost';
SHOW GRANTS FOR 'unishop_app'@'127.0.0.1';
