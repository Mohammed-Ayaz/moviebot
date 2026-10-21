"""Settings, read once from the environment at startup.

A missing or invalid variable stops the bot with a message that names the variable, never its
value. Only __main__ calls load_settings(); tests build Settings from a plain dict instead.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from dotenv import dotenv_values

ENV_FILE = Path(".env")
VARIABLES = (
    "DISCORD_TOKEN",
    "TMDB_READ_TOKEN",
    "GUILD_ID",
    "ADMIN_ROLE_ID",
    "BACKUP_CHANNEL_ID",
    "HEALTHCHECK_URL",
    "DATABASE_PATH",
    "LOG_LEVEL",
)
REQUIRED = ("DISCORD_TOKEN", "TMDB_READ_TOKEN", "GUILD_ID")
DISCORD_IDS = ("GUILD_ID", "ADMIN_ROLE_ID", "BACKUP_CHANNEL_ID")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_DATABASE_PATH = Path("data/moviebot.db")
DEFAULT_LOG_LEVEL = "INFO"


class ConfigError(Exception):
    """Some environment variables are missing or invalid. Lists every problem at once."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Settings:
    """Everything the bot reads from the environment. repr() leaves the tokens out."""

    discord_token: str = field(repr=False)
    tmdb_read_token: str = field(repr=False)
    guild_id: int
    admin_role_id: int | None = None
    backup_channel_id: int | None = None  # required from M6
    healthcheck_url: str | None = None  # required from M7
    database_path: Path = DEFAULT_DATABASE_PATH
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        """Build Settings from a mapping such as os.environ. Blank values count as not set."""
        values = {name: env.get(name, "").strip() for name in VARIABLES}

        problems = [f"{name} is missing" for name in REQUIRED if not values[name]]
        problems += [
            f"{name} must be a Discord ID, which is a whole number"
            for name in DISCORD_IDS
            if values[name] and not _is_discord_id(values[name])
        ]
        log_level = values["LOG_LEVEL"].upper() or DEFAULT_LOG_LEVEL
        if log_level not in LOG_LEVELS:
            problems.append(f"LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")
        if problems:
            raise ConfigError(problems)

        return cls(
            discord_token=values["DISCORD_TOKEN"],
            tmdb_read_token=values["TMDB_READ_TOKEN"],
            guild_id=int(values["GUILD_ID"]),
            admin_role_id=_optional_id(values["ADMIN_ROLE_ID"]),
            backup_channel_id=_optional_id(values["BACKUP_CHANNEL_ID"]),
            healthcheck_url=values["HEALTHCHECK_URL"] or None,
            database_path=Path(values["DATABASE_PATH"] or DEFAULT_DATABASE_PATH),
            log_level=log_level,
        )


def load_settings(env_file: Path = ENV_FILE) -> Settings:
    """Read Settings from the environment, filling gaps from env_file (./.env by default).

    Real environment variables win over the file, so systemd or your shell can override it, but
    a blank one doesn't count. The file is read without changing os.environ.
    """
    from_file = {name: value for name, value in dotenv_values(env_file).items() if value}
    from_environment = {name: value for name, value in os.environ.items() if value.strip()}
    return Settings.from_env(from_file | from_environment)


def _is_discord_id(value: str) -> bool:
    return value.isascii() and value.isdigit() and int(value) > 0


def _optional_id(value: str) -> int | None:
    return int(value) if value else None
