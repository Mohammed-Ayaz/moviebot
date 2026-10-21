-- migrations/0001_init.sql
CREATE TABLE categories (
    key      TEXT PRIMARY KEY,              -- 'launch'
    name     TEXT NOT NULL,                 -- 'The launch'
    position INTEGER NOT NULL,              -- display order
    side     TEXT NOT NULL CHECK (side IN ('bad', 'good', 'both')),
    blurb    TEXT
);

CREATE TABLE films (
    id           INTEGER PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,      -- 'heropanti-2014'
    tmdb_id      INTEGER UNIQUE,            -- NULL until matched
    title        TEXT NOT NULL,
    year         INTEGER,
    category_key TEXT REFERENCES categories(key) ON DELETE SET NULL,
    side         TEXT CHECK (side IN ('bad', 'good', 'both')),
    genre        TEXT,                      -- 'masala', 'drama', 'horror' or NULL
    is_indian    INTEGER NOT NULL DEFAULT 1 CHECK (is_indian IN (0, 1)),
    grade        TEXT,                      -- see the Appendix
    note         TEXT,                      -- written by members
    why_watch    TEXT,                      -- written only by imports (FR-20)
    poster_path  TEXT,                      -- TMDB path such as '/abc.jpg'
    runtime_min  INTEGER,
    tmdb_synced_at TEXT,                -- when TMDB details were last fetched
    added_by     INTEGER,                   -- Discord user id, NULL for seed and AI films
    added_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    watched_at   TEXT                       -- NULL means not watched yet
);

CREATE UNIQUE INDEX films_title_year ON films (lower(title), year);
CREATE INDEX films_watched ON films (watched_at);

CREATE TABLE suggestions (
    id           INTEGER PRIMARY KEY,
    film_id      INTEGER NOT NULL REFERENCES films(id) ON DELETE CASCADE,
    requested_by INTEGER NOT NULL,          -- Discord user id
    suggested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    chosen       INTEGER NOT NULL DEFAULT 0 CHECK (chosen IN (0, 1))
);

CREATE INDEX suggestions_recent ON suggestions (suggested_at);

CREATE TABLE verdicts (
    film_id    INTEGER NOT NULL REFERENCES films(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL,          -- Discord user id
    user_name  TEXT NOT NULL,             -- display name when the verdict was left
    verdict    TEXT NOT NULL CHECK (verdict IN ('liked', 'mixed', 'disliked')),
    comment    TEXT,                      -- up to 500 characters
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (film_id, user_id)        -- one verdict per member per film
);

CREATE TABLE blocklist (
    id     INTEGER PRIMARY KEY,
    title  TEXT NOT NULL,
    year   INTEGER,
    reason TEXT,
    UNIQUE (title, year)
);
