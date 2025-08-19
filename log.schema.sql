PRAGMA foreign_keys  = OFF;
PRAGMA journal_mode  = WAL;
PRAGMA synchronous   = NORMAL;
PRAGMA busy_timeout  = 5000;
PRAGMA temp_store    = FILE;

CREATE TABLE IF NOT EXISTS `logs` (
    `id`            INTEGER     PRIMARY KEY     AUTOINCREMENT,
    `name`          TEXT        NOT NULL,
    `level`         INTEGER     NOT NULL,
    `pathname`      TEXT        NOT NULL,
    `lineno`        TEXT        NOT NULL,
    `message`       TEXT        NOT NULL,
    `exc_info`      TEXT,
    `func`          TEXT,
    `sinfo`         TEXT,
    `created_at`    TIMESTAMP   DEFAULT         CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trim_logs AFTER INSERT ON logs
BEGIN
    DELETE  FROM     logs
    WHERE   id <= NEW.id - 10000;
END;
