# Movie Night Bot: Build Guide

Last updated: 2026-10-25

## Overview

Movie Night Bot is a Discord bot for one friends' server: a shared watchlist anyone can add to, and a Suggest button that picks tonight's film. It costs €0 a month, is written in Python, and is built in nine small milestones that a person or an AI coding tool can follow.

**Goals**

- Keep one shared list of films the server wants to watch, with posters and details from TMDB.
- Make choosing fast: one click suggests an unwatched film, and another click re-rolls.
- Record what everyone thought of each film, so an AI can study the group's taste and send back reasons to watch.
- Be a portfolio-quality CS project: layered architecture, tests, CI and a real deployment.

**Non-goals for v1**

- More than one Discord server. The bot is single-server by design.
- Streaming availability, voice features or a website.
- The bot calling an AI itself. You run the AI step by hand in Claude, which keeps it free.
- Stats and a Hall of Fame. These are planned for v2.

**Constraints**

- €0 a month: free tiers only, and no commercial use, because TMDB's free key forbids it.
- Python 3.12 and discord.py 2.7.
- It must run comfortably on a server with 1 GB of RAM.

**How to use this guide**

- Building it yourself: work through the Build plan one milestone at a time. Each milestone has a checklist and a "done when" test.
- Building it with an AI: save this guide in the repo as `docs/SPEC.md`, add the rules file from "Building it with AI", and give the AI one milestone at a time.
- Requirement IDs (FR-1, NFR-1) link the milestones, the tests and the code reviews back to this spec.

## Requirements

v1 has 23 functional requirements, 21 must-haves and 2 should-haves, delivered across milestones M1 to M8. FR-18 holds the v2 ideas.

**Functional requirements**

| ID | Requirement | Priority | Milestone |
| --- | --- | --- | --- |
| FR-1 | `/ping` replies with the bot's latency, so you can see it is alive. | Must | M1 |
| FR-2 | `/add` saves a film with title, year, and an optional category and note. | Must | M2 |
| FR-3 | `/list` shows the watchlist 10 films per page: unwatched films by default, with filters for category and watched state. | Must | M2 |
| FR-4 | Adding the same film twice is refused: same TMDB id, or same title and year. | Must | M2 |
| FR-5 | `/add` searches TMDB as you type and stores the TMDB id, poster and runtime. | Must | M3 |
| FR-6 | `/about` shows credits, including TMDB's required notice. | Must | M3 |
| FR-7 | `/suggest` and a Suggest button pick a random unwatched film that wasn't picked in the last 10 suggestions. | Must | M4 |
| FR-8 | The suggestion card shows poster, year, runtime, category and note, with "Another" and "We're watching this" buttons. | Must | M4 |
| FR-9 | "We're watching this" marks the film watched and posts it as tonight's pick. | Must | M4 |
| FR-10 | `/suggest` can filter by category, genre and side (hate-watch or actually good). | Should | M4 |
| FR-11 | `/remove` deletes a film after a confirm button, and says publicly who removed it. Anyone in the server can. | Must | M5 |
| FR-12 | `/edit` changes a film's note in a pop-up form, and its category with an option. Anyone in the server can. | Must | M5 |
| FR-13 | `/watched` marks a film watched, and `/unwatch` undoes it. Anyone in the server can. | Must | M5 |
| FR-14 | `/export` sends the whole list as a JSON file (admins only). | Must | M6 |
| FR-15 | A one-time import loads `watchlist_seed.json`. Running it twice changes nothing. Film notes go into `why_watch` (FR-20), because an AI wrote them. | Must | M6 |
| FR-16 | A weekly task backs up the database to a private admin channel. | Must | M6 |
| FR-17 | Adding a film from the do-not-watch list shows its reason and asks for confirmation. | Should | M6 |
| FR-18 | Stats and a Hall of Fame. | Could | v2 |

An admin is a member with the Manage Server permission, or with the role set in `ADMIN_ROLE_ID`.

**Verdicts and the AI round trip**

Members record what they thought of each film. `/export` hands everything to an AI as one JSON file, and `/import` brings back the AI's reasons to watch and its new picks. The bot never calls an AI itself.

| ID | Requirement | Priority | Milestone |
| --- | --- | --- | --- |
| FR-19 | `/verdict` records a member's take on a film: Liked, Mixed or Didn't like, plus an optional comment of up to 500 characters. Each member has one verdict per film, saved with their display name and the date; running it again replaces it. A verdict on an unwatched film marks it watched. | Must | M8 |
| FR-20 | Each film has a `why_watch` text of up to 1,000 characters that only imports write. Film and suggestion cards show it. | Must | M8 |
| FR-21 | `/export` (FR-14) sends one JSON file in the format shown in the Appendix: every film with its details, `why_watch` and verdicts, plus the categories, the do-not-watch list, a `format_version`, and instructions telling the AI what it may change. | Must | M8 |
| FR-22 | `/import` (admins) takes an attached JSON file in that format, up to 2 MB, checks it, and shows a private summary: films to add, `why_watch` texts to change, and skipped entries with the reason. Nothing changes until Confirm. | Must | M8 |
| FR-23 | An import only adds films and sets `why_watch`. It never deletes a film or changes verdicts, notes, watched dates or anything else members wrote, and an empty `why_watch` leaves the stored one alone. Importing the same file twice changes nothing. | Must | M8 |
| FR-24 | Imported films match existing ones by slug, then TMDB id, then title and year. Unmatched films are added as AI picks and looked up on TMDB like `/add`. Entries that break the `/add` rules or are on the do-not-watch list are skipped. | Must | M8 |

**Non-functional requirements**

| ID | Requirement | How to check it |
| --- | --- | --- |
| NFR-1 | Costs €0 a month. | The cloud billing page shows €0, and only free tiers are used. |
| NFR-2 | Every interaction is acknowledged within 3 seconds, Discord's limit. Autocomplete answers within 2 seconds. | Test by hand in the test server. The bot logs a warning for any handler slower than 2 seconds. |
| NFR-3 | Restarts by itself after a crash, keeps its buttons working after a restart, and emails you within 15 minutes of going down. | Kill the process, reboot the VM, then stop the bot and wait for the email. |
| NFR-4 | Secrets live only in `.env`. SQL uses placeholders only. The bot has the fewest permissions it needs, no port is open except SSH, and it runs as a non-root user. | The security checklist in Testing and code quality. |
| NFR-5 | The layer rules hold, ruff passes, the code has type hints, and service-layer test coverage is 80% or more. | CI on every push. |
| NFR-6 | At most 7 days of data can be lost, and `/export` works at any time. | Restore a backup on your laptop once. |
| NFR-7 | Uses less than 200 MB of RAM. | `systemctl status moviebot` shows memory use. |
| NFR-8 | Shows TMDB's attribution, and nothing is sold. | Check the `/about` output. |

## Tech stack

Every piece below is free and standard for a small Python Discord bot. Pin these versions in the AI rules file so generated code matches them.

| Component | Choice | Why |
| --- | --- | --- |
| Language | Python 3.12 | The newest version discord.py lists as supported, and Ubuntu 24.04's default. |
| Discord library | discord.py 2.7 | Mature and async, with slash commands, buttons, pop-up forms and autocomplete built in. |
| Database | SQLite through `aiosqlite` | One file, no server to run, plenty for one Discord server. The async driver keeps the bot responsive. |
| HTTP client | `aiohttp` | Already installed with discord.py, and async, so TMDB calls never freeze the bot. |
| Movie data | TMDB API | Free for non-commercial use, as long as you credit TMDB. |
| Configuration | `python-dotenv` plus a typed settings dataclass | Keeps secrets out of the code, and fails fast at startup if one is missing. |
| Packaging | `uv`, with `pyproject.toml` and `uv.lock` | One tool for Python itself, the virtual environment and locked dependencies. The server installs exactly what you tested. |
| Lint and format | `ruff` | One fast tool for both jobs. |
| Tests | `pytest`, `pytest-asyncio`, `pytest-cov` | Async tests and coverage reports. |
| CI | GitHub Actions | Free for public repos. Private repos get about 33 hours a month free. |
| Hosting | Oracle Cloud Always Free, `VM.Standard.E2.1.Micro`, Ubuntu 24.04 | Free including its public IP address, with 1 GB of RAM. |
| Process manager | systemd | Starts the bot on boot, restarts it after a crash, and keeps its logs. |
| Monitoring | Healthchecks.io, free Hobbyist plan | Emails you when the bot stops checking in. |

Deliberately left out: Docker, Redis, an ORM, a web framework and a separate API. Each adds moving parts that a single-server bot doesn't need, and any of them can be added later without a rewrite.

## Architecture

The bot has four layers, and calls only point down: Discord code calls services, and services call the repositories and the TMDB client. Nothing calls upward, so the rules can be tested without Discord, and a web page could reuse them later.

```text
Discord server
    │  commands and clicks
    ▼
Bot layer: cogs/, ui/              Web API: api/ (v2, optional)
    │                                  │
    └──────────────┬───────────────────┘
                   ▼
          Services: services/
    ┌──────────────┴───────────────────┐
    ▼                                  ▼
Repositories: db/                  TMDB client: tmdb/
    │                                  │
    ▼                                  ▼
SQLite file: data/moviebot.db      TMDB API: api.themoviedb.org
```

Discord events enter at the top and every call flows down. The web API is optional and planned for v2; it would reuse the same services.

| Layer | Folder | Does | Never |
| --- | --- | --- | --- |
| Bot | `cogs/`, `ui/` | Reads command input, checks Discord permissions, calls one service method, draws embeds and buttons. | Runs SQL or holds business rules. |
| Services | `services/` | The business rules: duplicates, who may edit, the suggestion algorithm. | Imports `discord`. |
| Repositories | `db/` | All SQL and the migrations. | Holds business rules. |
| TMDB client | `tmdb/` | All TMDB calls, with timeouts and a cache. | Knows about Discord. |

**Rules every change must keep**

1. Calls point down only: bot, then services, then repositories and the TMDB client.
2. Services receive what they use through the constructor: repositories, the TMDB client, a clock and a `random.Random`. Tests pass in fakes and a fixed seed.
3. Services return dataclasses from `models.py` and raise domain errors such as `FilmNotFound`, `DuplicateFilm` and `NotAllowed`. Cogs turn those into short ephemeral messages.
4. Only `db/` contains SQL, only `tmdb/` makes HTTP calls, and only `cogs/` and `ui/` import `discord`.
5. One database connection is opened at startup and shared by everything.

**Project layout**

```
moviebot/
├── pyproject.toml          dependencies, ruff and pytest settings
├── uv.lock                 exact versions, committed
├── .python-version         3.12
├── .env.example            every variable, no real values
├── .gitignore              includes .env and data/
├── README.md
├── AGENTS.md               rules for AI tools
├── docs/
│   ├── SPEC.md             this guide
│   └── decisions.md        one line per design decision
├── migrations/
│   ├── 0001_init.sql
│   └── 0002_backups.sql
├── scripts/
│   └── import_seed.py
├── src/moviebot/
│   ├── __main__.py         entry point: python -m moviebot
│   ├── config.py           Settings dataclass from the environment
│   ├── bot.py              Bot subclass: setup_hook, background tasks
│   ├── models.py           dataclasses and domain errors
│   ├── cogs/
│   │   ├── watchlist.py    /add /remove /edit /list /watched /unwatch
│   │   ├── suggest.py      /suggest
│   │   └── admin.py        /ping /about /export, owner sync
│   ├── ui/
│   │   ├── buttons.py      persistent buttons
│   │   ├── views.py        list pages, confirm dialogs
│   │   ├── modals.py       the edit form
│   │   └── embeds.py       film and suggestion cards
│   ├── services/
│   │   ├── watchlist.py    add, edit, remove, watched, the TMDB refresh
│   │   ├── picker.py       the suggestion algorithm
│   │   ├── seed.py         the seed import that scripts/import_seed.py runs
│   │   └── backup.py       export and backup files
│   ├── db/
│   │   ├── database.py     connect, pragmas, migrations, backup copies
│   │   ├── films.py        FilmRepository
│   │   ├── categories.py   CategoryRepository
│   │   ├── suggestions.py  SuggestionRepository
│   │   ├── blocklist.py    BlocklistRepository: the do-not-watch list
│   │   ├── verdicts.py     VerdictRepository
│   │   └── backups.py      BackupRepository: when each backup was posted
│   └── tmdb/
│       └── client.py       search and details, with a cache
└── tests/
    ├── conftest.py         in-memory database, fake TMDB client
    ├── test_picker.py
    └── test_watchlist.py
```

**Startup, in order**

1. `python -m moviebot` runs `asyncio.run(main())` in `__main__.py`, which loads `Settings` from the environment and sets up logging.
2. `main()` opens the database and applies any pending migrations.
3. It builds the TMDB client and the services, creates the bot with them, and starts it.
4. In `setup_hook`, the bot loads the cogs, registers its persistent buttons, and starts its daily background tasks: the backup check, when `BACKUP_CHANNEL_ID` is set, and the TMDB refresh. M7 adds the health check ping.
5. The bot connects to Discord. Slash commands are registered only when you send the owner-only `@MovieBot sync` message, never on every start.

## Data model

Six SQLite tables hold everything: categories, films, suggestion history, verdicts, the do-not-watch list, and a log of the backups posted. Times are stored as ISO 8601 UTC text, and Discord IDs as integers, which SQLite stores at the 64 bits they need.

```sql
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
```

The unique index on title and year backs up FR-4. SQLite treats NULLs as distinct, so two films with the same title and no year are allowed; the service layer warns about those.

```sql
-- migrations/0002_backups.sql
CREATE TABLE backups (
    id         INTEGER PRIMARY KEY,
    made_at    TEXT NOT NULL,                   -- when the copy was made, ISO 8601 UTC
    size_bytes INTEGER NOT NULL
);
```

`backups` gets one row for each weekly backup that reached the backup channel, so the bot knows when the next one is due (FR-16).

**Pragmas, set on every connection**

```sql
PRAGMA journal_mode = WAL;    -- reads don't block the writer
PRAGMA foreign_keys = ON;     -- SQLite leaves foreign keys off by default
PRAGMA busy_timeout = 5000;   -- wait up to 5 seconds for a lock
```

**Migrations**

1. Each schema change is a new numbered file in `migrations/`, such as `0002_add_hall_of_fame.sql`. A file is never edited once it has run anywhere.
2. At startup, `db/database.py` reads `PRAGMA user_version`, then runs every file with a higher number, in order. Each file runs inside one transaction and ends by setting `PRAGMA user_version` to its number.
3. Tests run the same migrations on an in-memory database, so tests and production share one schema.

## Commands and interactions

Users work the bot through twelve slash commands and four kinds of button. "Private" means an ephemeral reply only the user sees; "public" posts in the channel.

**Slash commands**

| Command | Options | Who can use it | Reply | What it does |
| --- | --- | --- | --- | --- |
| `/add` | `title` (TMDB search as you type), `year` (optional, for a title not picked from TMDB), `category` (optional choice), `note` (optional, up to 500 characters) | Everyone | Public | Saves the film and posts its card. Refuses duplicates. For a do-not-watch film, shows the reason and asks to confirm. |
| `/list` | `show` (unwatched, watched or all; default unwatched), `category` (optional) | Everyone | Public | 10 films a page, with Previous, Next and Suggest buttons. |
| `/suggest` | `category`, `genre`, `side` (all optional) | Everyone | Public | Picks a film and posts its card, with Another and We're watching this buttons. |
| `/watched` | `film` (search unwatched films) | Everyone | Public | Marks the film watched. |
| `/verdict` | `film` (search the list), `verdict` (Liked, Mixed or Didn't like), `comment` (optional, up to 500 characters) | Everyone | Public | Saves your verdict on the film, replacing any earlier one. Marks the film watched if it wasn't. |
| `/remove` | `film` (search the list) | Everyone | Private | Asks to confirm, then deletes the film and posts publicly who removed it. |
| `/edit` | `film` (search the list), `category` (optional) | Everyone | Private | Opens a pop-up form with the note filled in, then saves the note and category. |
| `/unwatch` | `film` (search watched films) | Everyone | Private | Undoes `/watched`. |
| `/export` | none | Admins | Private | Sends the whole list as a JSON file. |
| `/import` | `file` (a JSON attachment, up to 2 MB) | Admins | Private | Shows what the file would change, then applies it after Confirm. |
| `/ping` | none | Everyone | Private | Replies with the bot's latency in milliseconds. |
| `/about` | none | Everyone | Private | Credits, including TMDB's notice. |

The bot owner also has one text command, `@MovieBot sync`, which registers the slash commands on the server. It works without the restricted message-content permission because the message mentions the bot.

**Buttons**

| Button | `custom_id` | Survives a restart | What it does |
| --- | --- | --- | --- |
| Suggest | `mb:suggest` | Yes | Same as `/suggest` with no filters. |
| Another | `mb:another:<film_id>`, plus `:<category>:<genre>:<side>` when `/suggest` had filters | Yes | Picks again with the same filters, leaving out that film, and updates the card in place. |
| We're watching this | `mb:watch:<film_id>` | Yes | Marks the film watched, records the suggestion as chosen, disables the card's buttons and posts "Tonight: \<title>". |
| Previous, Next, Confirm, Cancel | generated | No | Paging and confirm dialogs. They expire after 10 minutes, and only the person who ran the command can click Confirm or Cancel. |

The three persistent buttons are `discord.ui.DynamicItem` classes. Their `custom_id` template carries the film id, and `setup_hook` registers them with `bot.add_dynamic_items(...)`, so buttons on old messages keep working after a restart.

**Response rules**

- Errors, confirmations and admin output are private. Lists, cards and tonight's pick are public.
- A handler that calls TMDB, or might take more than a second, calls `interaction.response.defer()` first and answers with a follow-up.
- Autocomplete can't be deferred, so it answers within 2 seconds, from the cache when possible. It returns at most 25 choices, each labelled "Title (Year)" in 100 characters or fewer.
- `/add`, `/suggest`, the Suggest button and Another have a cooldown of one use per 3 seconds per user.
- Admin commands use `app_commands.default_permissions(manage_guild=True)` to hide them, and the service checks permission again, because hidden isn't the same as secure.
- A film card shows the poster, "Title (Year)", runtime, category, note, `why_watch` text and who added it, with "Film data from TMDB" in the footer.

## Business rules

These rules live in the service layer and each one gets a unit test. The suggestion algorithm is the one to get exactly right.

**Suggestion algorithm (FR-7, FR-10)**

1. Start with every film where `watched_at` is NULL, narrowed by any filters given: category, genre, side. For the side filter, a film's side is its own, or its category's when it has none, and a film on side `both` counts for either side.
2. Leave out films in the last 10 rows of `suggestions`, and the film being re-rolled away from when Another was clicked.
3. If nothing is left, drop the last-10 rule but still leave out the film being re-rolled away from, unless it is the only film left. If there is still nothing, reply privately: "Nothing left to suggest. Add some films with /add."
4. Pick one candidate, uniformly at random, with the `random.Random` the service was given.
5. Insert a `suggestions` row with `chosen = 0`. We're watching this later sets `chosen = 1` and the film's `watched_at` to now.

**Adding a film (FR-2, FR-4, FR-5, FR-17)**

- The title is trimmed and must be 1 to 200 characters. A note may be up to 500, and a year, when given, is between 1888 and 2100.
- When the user picks a TMDB result, the bot stores TMDB's title and year, plus `tmdb_id`, `poster_path` and `runtime_min`.
- When the user types a title instead of picking a result, the bot searches TMDB once. If exactly one result has the same title, ignoring case and punctuation, and a year within 1 of any year given, it is used as if picked. Otherwise the film is saved as typed, without TMDB details, and the reply says so.
- `/add` defers privately, replies privately with a confirmation and any warnings, then posts the film's card publicly.
- It is a duplicate if the `tmdb_id` exists, or if the lower-cased title and the year match an existing film. The reply names the existing entry.
- A film added without a year is never a duplicate, but if a film with the same title is already listed, the reply warns and names it.
- The slug is the lower-cased title with every run of other characters turned into a hyphen, then the year: `heropanti-2014`. If it's taken, add `-2`, `-3` and so on.
- If the film is on the do-not-watch list, the bot shows the stored reason privately and adds the film only after Confirm. Titles match ignoring case and punctuation, and the years must be equal unless the film or the entry has no year.

**Who can change what (FR-11 to FR-13)**

| Action | Who |
| --- | --- |
| Add, list, suggest, mark watched or unwatched, edit, remove, leave a verdict | Everyone in the server |
| Export, import | Admins |

Anyone can change any film because the bot serves one friends' server. `/remove` still asks to confirm, and it posts publicly who removed what, so nothing disappears silently.

**Seed import (FR-15)**

- Stop the bot, then run `uv run python scripts/import_seed.py watchlist_seed.json` from the repo folder. It writes to the database at `DATABASE_PATH`.
- It checks the whole file first, and refuses a broken one with the entry and the problem.
- It inserts categories by `key` and films by `slug`, and puts both the `do_not_watch` and `didnt_land` lists into `blocklist`, with each note as the reason.
- A film marked `watched: true` gets `watched_at` set to the import time, and its note is stored as `why_watch`, because an AI wrote it.
- Every insert leaves existing rows alone, so a second run changes nothing and never overwrites edits made since. Categories and films use `ON CONFLICT DO NOTHING`, so a film already on the list, by slug, TMDB id, or title and year, is left out. The blocklist uses `WHERE NOT EXISTS`, because its unique constraint lets two NULL years through.
- With `--match-tmdb`, it looks up each seed film that has no TMDB id yet. It searches by title and year, then by title alone, because TMDB's year can be one off, and accepts the first result whose year is within 1 and whose title matches when case and punctuation are ignored. It stores TMDB's id, poster and runtime, and keeps the seed's own title and year. A TMDB film that already belongs to another film on the list is skipped and reported.
- It prints the films it couldn't match. They still work, just without a poster. Fix them by listing `slug,tmdb_id` pairs in a CSV file, one pair per line, and running the script again with `--map fixes.csv`. A semicolon or a tab works as the separator too.
- If TMDB stops answering, matching stops, and running the script again carries on.

## External APIs

The bot talks to two APIs: Discord, through discord.py's gateway connection, and TMDB, over HTTPS with a bearer token. Neither needs a paid plan.

**Discord application setup**

1. In the Discord Developer Portal, create an application called Movie Night Bot.
2. On the Bot page, reset the token and copy it into `.env` as `DISCORD_TOKEN`. Turn off Public Bot, so only you can add it to a server.
3. Leave all three privileged intents off: Presence, Server Members and Message Content. The code uses `discord.Intents.default()`.
4. Generate an invite link with the `bot` and `applications.commands` scopes, and the View Channels, Send Messages, Embed Links and Attach Files permissions.
5. Make a private test server and invite the bot there. Turn on Developer Mode in Discord's settings, right-click the server, and copy its ID into `GUILD_ID`.
6. The v2 Hall of Fame will need Message Content. Apps with fewer than 10,000 users can switch it on in the portal without a review.

**TMDB setup**

1. Create a TMDB account. In Settings, under API, request a key for personal, non-commercial use, and describe it as a Discord bot for one private server.
2. Copy the API Read Access Token, the long one, into `.env` as `TMDB_READ_TOKEN`.
3. Send it on every request as `Authorization: Bearer <token>`, together with `accept: application/json`.

**TMDB endpoints the bot uses** (base URL `https://api.themoviedb.org`)

| Endpoint | Used for | Notes |
| --- | --- | --- |
| `GET /3/search/movie?query=...&include_adult=false&page=1` | Autocomplete on `/add`, and seed matching | Add `primary_release_year` when the year is known. Return at most 25 results. |
| `GET /3/movie/{movie_id}` | Details after the user picks a film | Gives `title`, `release_date`, `runtime` and `poster_path`. |
| `https://image.tmdb.org/t/p/w500{poster_path}` | The poster in film cards | Discord fetches the image itself, so the bot only sends the URL. |

**Client rules**

- The bot shares one `aiohttp.ClientSession`, and every request has a 5-second total timeout.
- On HTTP 429 or a 5xx error, it waits for `Retry-After` (or 1 second) and retries once. If TMDB asks for more than 5 seconds, it gives up instead. TMDB's soft limit is about 40 requests a second, far above what this bot needs.
- If TMDB is down, `/add` still works: it saves the typed title without a poster and says so.
- Search results are cached in memory for 10 minutes, keyed by the lower-cased query, up to 500 entries.
- TMDB's terms allow cached data to be kept for up to six months. A daily task re-fetches the poster and runtime of films whose `tmdb_synced_at` is more than five months (150 days) old, up to 50 a day, oldest first. A film TMDB can't give is tried again the next day, and after 3 failures the task stops until then.

**Attribution (NFR-8)**

`/about` shows an approved TMDB logo, smaller and less prominent than the bot's own name, and this exact notice: "This product uses the TMDB API but is not endorsed or certified by TMDB." Discord embeds can't show SVG, so use a PNG version of the logo.

## Configuration and secrets

All configuration comes from eight environment variables, loaded from a `.env` file that never enters Git. The repo commits `.env.example` instead, with every name and no values.

| Variable | Required | Example | Purpose |
| --- | --- | --- | --- |
| `DISCORD_TOKEN` | Yes | from the Developer Portal | The bot's login. Never commit it or paste it anywhere. |
| `TMDB_READ_TOKEN` | Yes | from TMDB settings | TMDB bearer token. |
| `GUILD_ID` | Yes | `123456789012345678` | The one server the bot serves. Commands sync here. |
| `ADMIN_ROLE_ID` | No | `234567890123456789` | A role counted as admin, besides Manage Server. |
| `BACKUP_CHANNEL_ID` | From M6 | `345678901234567890` | The private channel that receives weekly backups. Without it the bot still runs, and logs that backups are off. |
| `HEALTHCHECK_URL` | From M7 | `https://hc-ping.com/<your-check-id>` | Pinged every 5 minutes. |
| `DATABASE_PATH` | No | `data/moviebot.db` | Where the SQLite file lives. |
| `LOG_LEVEL` | No | `INFO` | Use `DEBUG` while developing. |

```
# .env.example: copy to .env and fill in. Never commit .env.
DISCORD_TOKEN=
TMDB_READ_TOKEN=
GUILD_ID=
ADMIN_ROLE_ID=
BACKUP_CHANNEL_ID=
HEALTHCHECK_URL=
DATABASE_PATH=data/moviebot.db
LOG_LEVEL=INFO
```

**Rules**

- `config.py` reads the variables once into a frozen `Settings` dataclass, and stops at startup with a clear message if a required one is missing.
- `.gitignore` lists `.env`, `data/` and `*.db` from the very first commit.
- On the server, `.env` belongs to the bot's own user and has mode 600, so only that user can read it.
- Never log a token, and never paste one into an AI chat. Show the AI `.env.example` instead.
- If a token leaks, reset it in the Developer Portal or TMDB settings straight away, then update `.env` and restart the bot.

## Build plan

Nine milestones take the bot from an empty repo to a monitored deployment, then add the AI round trip. Pass each milestone's "done when" test and commit before starting the next.

**M0 · Project setup**

- [ ] Create a GitHub repo named moviebot and clone it. The folder name becomes the Python package name.
- [ ] Inside it, run `uv init --package` and `uv python pin 3.12`.
- [ ] Run `uv add aiohttp aiosqlite discord.py python-dotenv` and `uv add --dev ruff pytest pytest-asyncio pytest-cov`.
- [ ] Configure ruff and pytest in `pyproject.toml`, including `asyncio_mode = "auto"`.
- [ ] Add `.gitignore`, `.env.example`, `README.md`, `AGENTS.md`, and this guide as `docs/SPEC.md`.
- [ ] Add the CI workflow from Testing and code quality, plus one trivial test.

Done when: CI is green on GitHub, and `git log -p` shows no token anywhere.

**M1 · Hello bot (FR-1)**

- [ ] `config.py` with the `Settings` dataclass.
- [ ] `bot.py`: a `commands.Bot` subclass with `Intents.default()`, `commands.when_mentioned` as the prefix, and `setup_hook`.
- [ ] `__main__.py` with `asyncio.run(main())` and `discord.utils.setup_logging()`.
- [ ] The owner-only `@MovieBot sync` command, which copies the commands to `GUILD_ID` and syncs them.
- [ ] `/ping` in `cogs/admin.py`.
- [ ] A global `tree.on_error` handler that logs the traceback and replies privately "Something went wrong."

Done when: `/ping` answers in the test server, and an exception raised on purpose shows the friendly message and a logged traceback.

**M2 · Database and the basic list (FR-2 to FR-4)**

- [ ] `db/database.py`: connect, set the pragmas, run migrations with `PRAGMA user_version`.
- [ ] `migrations/0001_init.sql`, from the Data model section.
- [ ] `FilmRepository` with add, get, find duplicate, list one page, and delete.
- [ ] `WatchlistService.add_film` and `list_films`, with unit tests on an in-memory database.
- [ ] `/add` with a plain-text title and an optional year, and `/list` with Previous and Next.

Done when: films survive a restart, a duplicate is refused, and the tests pass in CI.

**M3 · TMDB (FR-5, FR-6)**

- [ ] `tmdb/client.py` with search, details, the timeout, one retry and the 10-minute cache.
- [ ] A `FakeTmdbClient` for tests.
- [ ] Autocomplete on `/add`, and posters and runtime on film cards.
- [ ] `/about` with TMDB's notice and logo.

Done when: typing "Herop" offers "Heropanti (2014)", the card shows its poster, and `/add` still saves a film when the TMDB token is deliberately wrong.

**M4 · Suggest (FR-7 to FR-10)**

- [ ] `PickerService` with the five-step algorithm and an injected `random.Random`.
- [ ] Tests: it never picks a watched film, never repeats within 10 picks, falls back when the pool is small, and honours filters.
- [ ] `/suggest` and the suggestion card.
- [ ] The persistent Suggest, Another and We're watching this buttons, built with `DynamicItem`.
- [ ] Cooldowns on `/suggest` and Another.

Done when: a card's buttons still work after the bot restarts, and with 20 or more unwatched films, 20 clicks of Another never repeat a film within 10 clicks.

**M5 · Editing (FR-11 to FR-13)**

- [ ] `/remove` with a confirm dialog and a public note of who removed what, `/edit` with a pop-up form, and `/watched` and `/unwatch`.
- [ ] Autocomplete on every `film` option, searching the list.

Done when: anyone can remove a film after confirming, while Cancel keeps it; edit its note in the pop-up and move it to another category; and mark it watched or unwatched.

**M6 · Data safety and the seed (FR-14 to FR-17)**

- [ ] `/export`, as JSON in the Appendix format, for admins.
- [ ] `scripts/import_seed.py`, with `--match-tmdb` and `--map`.
- [ ] The do-not-watch warning on `/add`.
- [ ] `why_watch` on film and suggestion cards, moved up from M8 so the imported films show their notes.
- [ ] The weekly backup: right after startup and then once a day, the bot checks whether a week has passed since the last backup. If so, it copies the database with SQLite's backup API in a worker thread and posts the copy to `BACKUP_CHANNEL_ID`.
- [ ] The TMDB refresh, a daily task.

Done when: importing the seed twice leaves exactly 196 films, and a downloaded backup opens in DB Browser for SQLite.

**M7 · Deploy and monitor (NFR-1, NFR-3, NFR-4, NFR-7)**

- [ ] The Oracle VM, set up as in Deployment and operations.
- [ ] The systemd service running, with logs visible in `journalctl`.
- [ ] A health check ping every 5 minutes, with Healthchecks.io emailing you when it stops.
- [ ] A README runbook for deploying, updating and restoring.

Done when: rebooting the VM brings the bot back by itself, and stopping the bot sends you the email within 15 minutes.

**M8 · Verdicts and the AI round trip (FR-19 to FR-24)**

- [ ] `/verdict`, saved with an upsert on film and member.
- [ ] An `ImportService` with a dry run and an apply step, used by `/import` and by `scripts/import_seed.py`, which converts the seed format first.
- [ ] `/import` with its summary and Confirm.
- [ ] Tests: an import never changes member data, a second import changes nothing, and matching goes slug, then TMDB id, then title and year.

Done when: you export, paste the file into Claude with "Follow the instructions in this file", save its reply as a .json file and import it. New why-watch texts appear on the cards, every verdict is unchanged, and importing the same file again reports no changes.

**After v1 (FR-18):** stats, the Hall of Fame (it needs the Message Content intent), and optionally a FastAPI web page that reuses the same services.

## Testing and code quality

Most tests target the service layer, with no network and no Discord, and CI runs them with ruff on every push. The bar is NFR-5: ruff clean, and 80% or more coverage of `moviebot.services`.

**What gets tested where**

- Service tests, the bulk: a real in-memory SQLite database with the real migrations, a `FakeTmdbClient`, a fixed clock and a seeded `random.Random`.
- Repository tests, a few: they prove the SQL itself, such as duplicates, paging and `ON CONFLICT`.
- Manual tests: each milestone's "done when" check, in the private test server.
- Cogs stay thin enough that they need no tests of their own. Don't test discord.py itself.

**Tests to write first**

- `test_suggest_never_picks_watched`
- `test_suggest_skips_last_10_suggestions`
- `test_suggest_falls_back_when_pool_is_small`
- `test_suggest_respects_filters`
- `test_add_rejects_duplicate_tmdb_id` and `test_add_rejects_duplicate_title_and_year`
- `test_add_warns_on_blocklisted_film`
- `test_seed_import_is_idempotent`
- `test_migrations_apply_in_order`

**CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.0
        with:
          enable-cache: true
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest --cov=moviebot.services --cov-fail-under=80
```

uv reads `.python-version` and installs Python 3.12 by itself. Dependabot then keeps the action versions and your dependencies current with monthly pull requests:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
  - package-ecosystem: uv
    directory: /
    schedule:
      interval: monthly
```

**Coding standards**

- Type hints on every function, and dataclasses for the models in `models.py`.
- `ruff check` and `ruff format` both clean, with a line length of 100.
- Nothing blocks the event loop: no `requests`, no `time.sleep`, no plain `sqlite3` calls. Unavoidable blocking work goes through `asyncio.to_thread`.
- SQL uses `?` placeholders only, never f-strings or string concatenation.
- Every module logs through `logging.getLogger(__name__)`. No `print`, and never a token in a log line.
- Small functions, and one commit per working step, with a message that says what changed and why.

**Security checklist**

- [ ] `.env` is in `.gitignore`, and `git log -p` shows no secret.
- [ ] Every SQL statement uses placeholders.
- [ ] The invite grants only the four permissions from External APIs, and Public Bot is off.
- [ ] Admin actions are checked in the service, not only hidden with `default_permissions`.
- [ ] User text has length limits, and the bot is created with `allowed_mentions=discord.AllowedMentions.none()`, so a title like "@everyone" can't ping the server.
- [ ] On the VM, the bot runs as a non-root user, SSH accepts keys only, and no inbound port is open except 22.
- [ ] Dependabot alerts are switched on for the repo.

## Deployment and operations

The bot runs 24/7 on Oracle Cloud's Always Free AMD micro VM for €0, including its public IP. Oracle may reclaim a free VM that looks idle for a week, which a small bot will, so health checks and off-server backups are part of the setup, not extras.

**One-time server setup**

1. Sign up for Oracle Cloud Free Tier. Choose Frankfurt, the region nearest Munich, as your home region, because it's fixed at signup. The card is only for verification.
2. Create an instance with the Canonical Ubuntu 24.04 image and the `VM.Standard.E2.1.Micro` shape, marked Always Free. Keep a public IPv4 address, and paste in an SSH public key made with `ssh-keygen -t ed25519`.
3. Log in with `ssh ubuntu@<public-ip>`. Oracle's Ubuntu image accepts SSH keys only; keep it that way.
4. Update the system and add 1 GB of swap, because 1 GB of RAM is tight while installing:

```bash
sudo apt update && sudo apt upgrade -y
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

5. Create a user just for the bot, then install uv for everyone. Ubuntu keeps the bot's home folder private, so the commands after this use full paths instead of cd:

```bash
sudo useradd --system --create-home --home-dir /opt/moviebot --shell /usr/sbin/nologin moviebot
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
```

6. Fetch the code and install the locked dependencies. For a private repo, add a read-only deploy key on GitHub first.

```bash
sudo -u moviebot -H git clone https://github.com/<you>/moviebot.git /opt/moviebot/app
sudo -u moviebot -H uv --directory /opt/moviebot/app sync --locked --no-dev
```

7. Add the secrets and the data folder:

```bash
sudo -u moviebot cp /opt/moviebot/app/.env.example /opt/moviebot/app/.env
sudo -u moviebot nano /opt/moviebot/app/.env
sudo chmod 600 /opt/moviebot/app/.env
sudo -u moviebot mkdir -p /opt/moviebot/app/data
```

8. Save this as `/etc/systemd/system/moviebot.service`. The last five service lines lock the bot down so it can write only to its `data` folder.

```ini
[Unit]
Description=Movie Night Bot
After=network-online.target
Wants=network-online.target

[Service]
User=moviebot
WorkingDirectory=/opt/moviebot/app
EnvironmentFile=/opt/moviebot/app/.env
ExecStart=/opt/moviebot/app/.venv/bin/python -m moviebot
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/opt/moviebot/app/data

[Install]
WantedBy=multi-user.target
```

9. Start it, and follow the logs:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now moviebot
journalctl -u moviebot -f
```

10. Leave Oracle's default network rules alone. They allow only SSH in, and the bot needs no incoming connections.

**Updating the bot**

```bash
sudo -u moviebot -H git -C /opt/moviebot/app pull
sudo -u moviebot -H uv --directory /opt/moviebot/app sync --locked --no-dev
sudo systemctl restart moviebot
```

If any slash command changed, send `@MovieBot sync` in Discord afterwards.

**Monitoring**

- On Healthchecks.io, create a check with a 5-minute period and a 10-minute grace time, and put its ping URL in `HEALTHCHECK_URL`. The bot calls it every 5 minutes, and you get an email when the calls stop.
- Once a week, run `journalctl -u moviebot --since "7 days ago" -p warning` to see any warnings.
- If Oracle reclaims the VM: when it was only stopped, start it again in the Oracle console. When it was deleted, rebuild it with this runbook and restore the latest backup.

**Backups and restore**

- The bot checks once a day, and posts a new backup when the last one is a week old, so a restart never skips or repeats one.
- The weekly backup file arrives in the private admin channel. To restore, stop the bot, replace `data/moviebot.db` with the downloaded file, and start it again.
- Practise a restore once on your laptop. That is the check for NFR-6.

**If Oracle doesn't work out**

| Option | Cost | Trade-off |
| --- | --- | --- |
| An old PC or laptop at home | €0 | The bot is offline whenever the machine is. No router changes are needed, since the bot only connects outward. |
| Google Cloud e2-micro, in us-west1, us-central1 or us-east1, with a 30 GB standard persistent disk | About $3.65 a month, for the public IPv4 address | The most reliable option, with no idle reclaim. |

## Building it with AI

An AI coding tool can write most of this bot, but only with the spec, strict rules and one milestone at a time. You stay the architect and the reviewer: nothing gets merged that you can't explain.

**Which tool to use**

- Build it with Claude Code, which comes with the Pro and Max plans. It works inside the repo: it reads `docs/SPEC.md` and `AGENTS.md` itself, edits the files, and runs uv, pytest and ruff, so it can follow the loop below.
- Don't build it in a claude.ai Project. A Project can read a GitHub repo, but only updates when you click Sync, and it can't change files or run your tests, so you'd be copying code back and forth by hand. A Project is fine for questions and learning on the side.

**Set up the repo for AI**

- Save this guide as `docs/SPEC.md` and keep it current. When a decision changes, edit the spec first, then the code.
- Put the rules below in `AGENTS.md` at the repo root. Many AI coding tools read it automatically, and Claude Code reads it whenever the repo has no `CLAUDE.md`.
- Record decisions in `docs/decisions.md`, one dated line each, so a fresh AI session knows why things are the way they are.

**The rules file**

```markdown
# AGENTS.md: rules for AI assistants

Read docs/SPEC.md before any change. It is the source of truth.

## Stack (don't change without asking)
- Python 3.12, discord.py 2.7, aiosqlite, aiohttp, python-dotenv
- uv for everything: `uv add`, `uv run pytest`, `uv run ruff check .`
- SQLite, with numbered migrations in migrations/

## Architecture
- Layers: cogs and ui -> services -> db and tmdb. Calls point down only.
- Only db/ contains SQL. Only tmdb/ makes HTTP calls. Only cogs/ and ui/ import discord.
- Services get their dependencies through the constructor and raise domain errors from models.py.

## Always
- Slash commands and buttons only. The one text command is the owner-only sync.
- Async all the way. Never use requests, time.sleep or plain sqlite3 on the event loop.
- SQL with ? placeholders only.
- Acknowledge every interaction within 3 seconds, and defer slow work.
- Persistent buttons use discord.ui.DynamicItem.
- Create the bot with allowed_mentions=discord.AllowedMentions.none().
- Add or update tests with every service change. `uv run pytest` and ruff must pass.

## Never
- Read, print or ask for real secrets. Use the names in .env.example.
- Enable privileged intents or use discord.Intents.all().
- Sync the command tree in on_ready or setup_hook.
- Add a dependency, framework or layer without asking first.
- Edit a migration that has already run. Add a new one instead.

## Workflow
- One milestone from docs/SPEC.md at a time.
- Before coding, write a short plan: files to change and tests to add. Wait for approval.
- Keep changes small, and run the tests after each step.
```

**The loop for each milestone**

1. Start a fresh session and point the AI at `docs/SPEC.md` and `AGENTS.md`.
2. Ask for a plan for one milestone only. Push back on anything the spec doesn't ask for.
3. Have it write the tests first, then the code that makes them pass.
4. Run everything yourself: `uv run pytest`, `uv run ruff check .`, then the milestone's "done when" check in the test server.
5. Ask it to review its own diff against `AGENTS.md`: blocking calls, SQL placeholders, layer rules, secrets.
6. Read the diff, ask about anything unclear, then commit.

**Prompts to copy**

```
PLAN
Read docs/SPEC.md and AGENTS.md. We are doing milestone M4 (Suggest) only.
Write a plan: the files you will create or change, the tests you will add
(use the names under "Tests to write first"), and any question where the
spec is unclear. Don't write code yet.

BUILD
The plan is approved. Implement step 1 only: PickerService and its tests.
Follow AGENTS.md. Run `uv run pytest` and show me the output.

REVIEW
Review this milestone's diff against AGENTS.md and the security checklist
in docs/SPEC.md. List every violation with its file and line. Don't fix
anything yet.

LEARN
Explain picker.py line by line, as if I had to defend it in a job
interview. Then ask me three questions to check that I understood it.
```

**Mistakes AI tools commonly make on this kind of bot**

- Old discord.py 1.x patterns: `@bot.command` prefix commands, or reading message text. Point it at discord.py 2.7 and slash commands.
- `discord.Intents.all()` to "fix" an error. That turns on privileged intents this bot must not use.
- `requests` or plain `sqlite3` inside async code, which freezes the whole bot.
- SQL built with f-strings.
- `await bot.tree.sync()` inside `on_ready`, so it runs on every restart.
- Buttons that stop working after a restart, because the view has a timeout or isn't registered at startup.
- Invented TMDB fields or discord.py methods. Check anything unfamiliar against the official docs.
- Quietly adding Docker, an ORM, Redis or a web framework. Say no unless the spec changes first.

**Your own rules**

- Never paste a token, your `.env` or a backup file into an AI chat.
- Commit after every working step, so a bad AI change is one `git restore .` away.
- If you can't explain a file, don't merge it. Interviewers will ask about this project.
- Write M0 and M2 by hand even if the AI writes the rest. Setup and the database layer teach the most.

## Appendix: the seed file

`watchlist_seed.json` holds 196 films in 15 categories, 17 of them already watched, plus 13 blocklist entries: 4 under `didnt_land` and 9 under `do_not_watch`. Its top-level keys are `source`, `exported`, `grades`, `categories`, `films`, `didnt_land` and `do_not_watch`.

**Film fields**

| Field | Type | Example | Imported into |
| --- | --- | --- | --- |
| `id` | string | `heropanti-2014` | `films.slug` |
| `title` | string | `Heropanti` | `films.title` |
| `year` | integer | `2014` | `films.year` |
| `category` | string | `launch` | `films.category_key` |
| `side` | `bad`, `good` or `both` | `bad` | `films.side` |
| `genre` | `masala`, `drama` or `horror` | `masala` | `films.genre` |
| `indian` | boolean | `true` | `films.is_indian` |
| `grade` | string, see below | `yours` | `films.grade` |
| `note` | string | a sentence about the film | `films.why_watch` |
| `watched` | boolean | `true` | `films.watched_at`, set at import |

Each entry in `categories` has `key`, `number`, `name`, `side` and `blurb`. Each entry in `didnt_land` and `do_not_watch` has `title`, `year` and `note`.

**Grades**

| Grade | Meaning | Films |
| --- | --- | --- |
| `bullseye` | A sincere, clean hate-watch. Nobody involved is joking. | 114 |
| `good` | A genuinely good film. | 45 |
| `yours` | Already watched and liked. | 17 |
| `rough` | Fun, but crude or grimy enough to get in the way. | 10 |
| `sequel` | A franchise extension: the untested sequel idea. | 7 |
| `knowing` | Winks at itself, the riskiest tier. | 3 |

## Appendix: the export file

`/export` and `/import` share one JSON format, so the same file can go to an AI and come back. The AI may only write `why_watch` and add films; the import ignores any other change (FR-23).

```json
{
  "format_version": 1,
  "exported_at": "2026-10-21T09:00:00Z",
  "instructions": "Movie Night Bot export. Verdicts show what members thought of films they watched, and comments say why. You may change only two things. 1) Write or rewrite why_watch on any film: up to 1,000 characters on why this group should watch it. 2) Add new films to films with title, year and why_watch, plus category, side, genre, indian and grade if you can; leave out slug. Do not add films already in films or do_not_watch. Do not edit or remove anything else, because the import ignores it. Reply with the whole file as valid JSON in this format.",
  "categories": [
    {"key": "launch", "name": "The launch", "side": "bad", "blurb": "A production house spends real money introducing a new face."}
  ],
  "films": [
    {
      "slug": "heropanti-2014",
      "title": "Heropanti",
      "year": 2014,
      "tmdb_id": null,
      "category": "launch",
      "side": "bad",
      "genre": "masala",
      "indian": true,
      "grade": "yours",
      "note": null,
      "why_watch": "Tiger's debut, built from the ground up to launch him.",
      "added_by": "AI",
      "watched_at": "2026-10-20T10:09:24Z",
      "verdicts": [
        {"by": "Ayaz", "verdict": "liked", "comment": "What you thought, in your own words", "date": "2026-10-20"}
      ]
    }
  ],
  "do_not_watch": [
    {"title": "Humshakals", "year": 2014, "reason": "Three hours in which nothing happens to anyone, crudely."}
  ]
}
```

- `slug` is a film's permanent key. New films from the AI leave it out, and the import creates one.
- `added_by` is a member's display name, or "AI" for films from the seed file or an import.
- `verdict` is `liked`, `mixed` or `disliked`. The file holds display names, never Discord ids.
- `watched_at` is `null` for films not watched yet. All times are UTC.

## Sources

- [discord.py on PyPI](https://pypi.org/project/discord-py/): version 2.7.1 and supported Python versions.
- [Discord: privileged intent review](https://docs.discord.com/developers/gateway/getting-started-with-privileged-intent-review.md): intents and slash commands.
- [TMDB API FAQ](https://developer.themoviedb.org/docs/faq): non-commercial use and attribution.
- [How to get a TMDB API key (Apidog)](https://apidog.com/blog/tmdb-api-key/): the read access token, rate limits and the six-month caching rule.
- [TMDB rate limits (API Evangelist)](https://apis.io/rate-limits/tmdb/tmdb-rate-limits/): HTTP 429 and the soft limit.
- [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm): the micro VM, its public IP, outbound traffic and idle reclaim.
- [Free VPS options in 2026 (Klymentiev)](https://klymentiev.com/blog/free-vps): micro VM specs.
- [Best free VPS tiers in 2026 (Mr Plan B)](https://www.mrplanb.com/datacenter/free-vps-tiers): the home region is fixed at signup.
- [Google Cloud network pricing](https://cloud.google.com/vpc/network-pricing): the public IPv4 charge.
- [GCP free tier hosting guide (DEV Community)](https://dev.to/jeaniscoding/how-to-host-your-side-projects-for-0-the-ultimate-gcp-free-tier-guide-3p07): the standard disk requirement.
- [GitHub Actions pricing update](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/): free minutes.
- [uv in 2026 (CODERCOPS)](https://blog.codercops.com/blog/uv-python-package-manager-2026): uv and its lockfile.
- [Healthchecks.io pricing (Capterra)](https://www.capterra.com/p/249957/Healthchecksio/pricing/): the free Hobbyist plan.
- [Claude Code memory docs](https://code.claude.com/docs/en/memory.md): how CLAUDE.md and AGENTS.md are read.
