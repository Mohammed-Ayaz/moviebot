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
