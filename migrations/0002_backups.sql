-- migrations/0002_backups.sql: one row per weekly backup posted to the backup channel (FR-16).
-- The bot checks once a day and posts a new backup when the last one is a week old, so a restart
-- never skips a backup or posts an extra one.
CREATE TABLE backups (
    id         INTEGER PRIMARY KEY,
    made_at    TEXT NOT NULL,                   -- when the copy was made, ISO 8601 UTC
    size_bytes INTEGER NOT NULL
);
