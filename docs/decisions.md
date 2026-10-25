# Decisions

One dated line per design decision, newest last. When a decision changes, update docs/SPEC.md first, then the code.

- 2026-10-20: Python 3.12, discord.py 2.7 and SQLite through aiosqlite. One Discord server only.
- 2026-10-20: Four layers (bot, services, repositories, TMDB client). Calls point down only.
- 2026-10-20: Slash commands and buttons only; no privileged intents.
- 2026-10-20: Hosting on Oracle Cloud's Always Free AMD micro VM, with Healthchecks.io and weekly backups to Discord.
- 2026-10-21: Verdicts (liked, mixed, disliked) replace the planned two-axis ratings.
- 2026-10-21: AI work happens by hand through /export and /import. The bot never calls an AI, and an import may only add films and write why_watch.
- 2026-10-21: The layer packages exist from M0, so CI measures service coverage from the start.
- 2026-10-21: aiohttp is a direct dependency because the TMDB client imports it.
- 2026-10-21: bot.py and __main__.py count as the bot layer, so they may import discord. config.py never does.
- 2026-10-21: setup_hook adds each cog with add_cog and passes its dependencies to the constructor, instead of loading cogs as extensions.
- 2026-10-21: The default help command is removed, so @MovieBot sync stays the only text command.
- 2026-10-21: Settings read .env without changing os.environ. Real environment variables win over the file, and a blank value counts as not set.
- 2026-10-21: One shared aiosqlite connection. Writes go through Database.transaction(), which holds an asyncio lock, so two commands can't mix their writes into one transaction.
- 2026-10-21: The migration runner is the only code that builds SQL text. It wraps each file in BEGIN and COMMIT and sets PRAGMA user_version from the file's number, because PRAGMA can't take ? placeholders. Both come from the repo, never from users.
- 2026-10-21: migrations/ stays at the repo root, as in the spec. database.py finds it relative to the source tree, which works because the bot always runs from a checkout.
- 2026-10-21: Categories get their own small repository, db/categories.py, because /add and /list need them before the seed import exists.
- 2026-10-21: Services raise DomainError subclasses with plain-text messages. ui/errors.py turns those, and cooldowns, into private replies for commands and buttons alike, so cogs need no try/except.
- 2026-10-21: /add takes an optional year. From M3 it covers titles that aren't picked from TMDB.
- 2026-10-21: TMDB suggestions carry "tmdb:<id>" as their value. Anything else in /add's title is a typed title.
- 2026-10-21: A typed title is searched on TMDB once. Exactly one result with the same title, ignoring case and punctuation and within a year of any year given, is used as if picked; otherwise the film is saved as typed.
- 2026-10-21: /add defers privately, confirms privately, then posts the card publicly as a second message, so errors after the defer stay private.
- 2026-10-21: TMDB suggestions give up after 1.8 seconds, inside Discord's 3-second limit, and show nothing rather than an error.
- 2026-10-21: The TMDB client gives up instead of waiting when Retry-After asks for more than 5 seconds.
- 2026-10-21: The TMDB logo ships inside the package, in src/moviebot/assets/, and /about attaches it as a small thumbnail.
- 2026-10-21: Test doubles live in tests/fakes.py, and conftest.py hands them to tests as fixtures.
