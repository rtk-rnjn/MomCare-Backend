PRAGMA foreign_keys = OFF;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS `logs` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT,
    `name` TEXT NOT NULL,
    `level` INT NOT NULL,
    `pathname` TEXT NOT NULL,
    `lineno` TEXT NOT NULL,
    `message` TEXT NOT NULL,
    `exc_info` TEXT,
    `func` TEXT,
    `sinfo` TEXT,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trim_logs AFTER INSERT ON logs
BEGIN
    DELETE FROM logs
    WHERE id NOT IN (
        SELECT id FROM logs
        ORDER BY id DESC
        LIMIT 10000
    );
END;
