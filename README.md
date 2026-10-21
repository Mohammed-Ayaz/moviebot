# Movie Night Bot

A Discord bot for our movie nights: a shared watchlist with posters from TMDB, a Suggest button that picks tonight's film, verdicts on what everyone thought, and a JSON export an AI can study and fill with reasons to watch.

Status: in development. The plan, requirements and milestones are in [docs/SPEC.md](docs/SPEC.md).

## Run it locally

1. Install [uv](https://docs.astral.sh/uv/).
2. Run `uv sync` to install Python 3.12 and the dependencies.
3. Copy `.env.example` to `.env` and fill in your tokens. Never commit `.env`.
4. Run `uv run python -m moviebot` (works from milestone M1).

## Develop

- Tests: `uv run pytest`
- Lint and format: `uv run ruff check .` and `uv run ruff format .`
- Rules for AI coding tools: [AGENTS.md](AGENTS.md)
- Design decisions: [docs/decisions.md](docs/decisions.md)

## Credits

This product uses the TMDB API but is not endorsed or certified by TMDB.
