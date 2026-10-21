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
