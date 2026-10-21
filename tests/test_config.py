"""Settings: required variables, defaults, validation, and tokens kept out of every message."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from moviebot.config import ConfigError, Settings, load_settings

FULL_ENV = {
    "DISCORD_TOKEN": "discord-test-token",
    "TMDB_READ_TOKEN": "tmdb-test-token",
    "GUILD_ID": "123456789012345678",
    "ADMIN_ROLE_ID": "234567890123456789",
    "BACKUP_CHANNEL_ID": "345678901234567890",
    "HEALTHCHECK_URL": "https://hc-ping.com/test-check",
    "DATABASE_PATH": "data/test.db",
    "LOG_LEVEL": "debug",
}

# Only the required values filled in. A line like "ADMIN_ROLE_ID=" in .env reads as "".
MINIMAL_ENV = {
    "DISCORD_TOKEN": "discord-test-token",
    "TMDB_READ_TOKEN": "tmdb-test-token",
    "GUILD_ID": "123456789012345678",
    "ADMIN_ROLE_ID": "",
    "BACKUP_CHANNEL_ID": "",
    "HEALTHCHECK_URL": "",
    "DATABASE_PATH": "",
    "LOG_LEVEL": "",
}


def test_settings_load_from_env() -> None:
    settings = Settings.from_env(FULL_ENV)

    assert settings.discord_token == FULL_ENV["DISCORD_TOKEN"]
    assert settings.tmdb_read_token == FULL_ENV["TMDB_READ_TOKEN"]
    assert settings.guild_id == 123456789012345678
    assert settings.admin_role_id == 234567890123456789
    assert settings.backup_channel_id == 345678901234567890
    assert settings.healthcheck_url == "https://hc-ping.com/test-check"
    assert settings.database_path == Path("data/test.db")
    assert settings.log_level == "DEBUG"
    with pytest.raises(FrozenInstanceError):
        settings.guild_id = 1  # type: ignore[misc]


def test_blank_optional_values_use_defaults() -> None:
    settings = Settings.from_env(MINIMAL_ENV)

    assert settings.admin_role_id is None
    assert settings.backup_channel_id is None
    assert settings.healthcheck_url is None
    assert settings.database_path == Path("data/moviebot.db")
    assert settings.log_level == "INFO"


def test_missing_required_names_every_variable() -> None:
    env = {**MINIMAL_ENV, "DISCORD_TOKEN": "", "GUILD_ID": "   "}
    del env["TMDB_READ_TOKEN"]

    with pytest.raises(ConfigError) as caught:
        Settings.from_env(env)

    assert caught.value.problems == [
        "DISCORD_TOKEN is missing",
        "TMDB_READ_TOKEN is missing",
        "GUILD_ID is missing",
    ]


@pytest.mark.parametrize("name", ["GUILD_ID", "ADMIN_ROLE_ID", "BACKUP_CHANNEL_ID"])
@pytest.mark.parametrize(
    "value",
    ["abc", "12.5", "-5", "0", pytest.param("１２３", id="full-width-digits")],
)
def test_invalid_id_is_rejected(name: str, value: str) -> None:
    with pytest.raises(ConfigError, match=f"{name} must be a Discord ID"):
        Settings.from_env({**MINIMAL_ENV, name: value})


def test_unknown_log_level_is_rejected() -> None:
    with pytest.raises(ConfigError, match="LOG_LEVEL must be one of"):
        Settings.from_env({**MINIMAL_ENV, "LOG_LEVEL": "verbose"})


def test_tokens_never_appear_in_repr_or_errors() -> None:
    settings = Settings.from_env(MINIMAL_ENV)
    assert "discord-test-token" not in repr(settings)
    assert "tmdb-test-token" not in repr(settings)

    # A token pasted into the wrong line must not be printed back in the error.
    env = {**MINIMAL_ENV, "GUILD_ID": "discord-test-token", "LOG_LEVEL": "tmdb-test-token"}
    with pytest.raises(ConfigError) as caught:
        Settings.from_env(env)
    assert "discord-test-token" not in str(caught.value)
    assert "tmdb-test-token" not in str(caught.value)


def test_load_settings_reads_env_file_and_environment_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in FULL_ENV.items()), encoding="utf-8")
    for name in FULL_ENV:
        monkeypatch.delenv(name, raising=False)  # keep your real environment out of this test
    monkeypatch.setenv("GUILD_ID", "999")  # a real environment variable beats the file
    monkeypatch.setenv("DATABASE_PATH", "")  # a blank one doesn't

    settings = load_settings(env_file)

    assert settings.discord_token == FULL_ENV["DISCORD_TOKEN"]
    assert settings.guild_id == 999
    assert settings.database_path == Path("data/test.db")
