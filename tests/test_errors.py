"""report_error: what people see when a command or button fails, and what gets logged."""

import logging
from typing import Any, cast

import discord
import pytest
from discord import app_commands

from moviebot.models import InvalidFilm
from moviebot.ui.errors import ERROR_REPLY, report_error


class FakeResponse:
    def __init__(self, *, done: bool) -> None:
        self.done = done
        self.sent: list[tuple[str, bool]] = []

    def is_done(self) -> bool:
        return self.done

    async def send_message(self, content: str, *, ephemeral: bool = False) -> None:
        self.sent.append((content, ephemeral))


class ExpiredResponse(FakeResponse):
    async def send_message(self, content: str, *, ephemeral: bool = False) -> None:
        raise discord.NotFound(cast(Any, FakeHTTPResponse()), "Unknown interaction")


class FakeHTTPResponse:
    status = 404
    reason = "Not Found"


class FakeFollowup:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool = False) -> None:
        self.sent.append((content, ephemeral))


class FakeCommand:
    name = qualified_name = "add"


class FakeInteraction:
    """Just enough of discord.Interaction for report_error."""

    def __init__(self, *, answered: bool = False) -> None:
        self.response: FakeResponse = FakeResponse(done=answered)
        self.followup = FakeFollowup()
        self.command = FakeCommand()


async def report(interaction: FakeInteraction, error: Exception) -> None:
    await report_error(cast(discord.Interaction, interaction), error)


def raised_by_command(error: Exception) -> app_commands.CommandInvokeError:
    """How discord.py hands a command's own exception to the error handler."""
    return app_commands.CommandInvokeError(cast(Any, FakeCommand()), error)


async def test_broken_rule_is_shown_privately_and_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    interaction = FakeInteraction()

    await report(interaction, raised_by_command(InvalidFilm("The note can be at most 500.")))

    assert interaction.response.sent == [("The note can be at most 500.", True)]
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


async def test_cooldown_says_when_to_try_again() -> None:
    interaction = FakeInteraction()

    await report(interaction, app_commands.CommandOnCooldown(app_commands.Cooldown(1, 3.0), 2.2))

    assert interaction.response.sent == [("Slow down: try again in 3 seconds.", True)]


async def test_unexpected_error_is_logged_and_hidden(caplog: pytest.LogCaptureFixture) -> None:
    interaction = FakeInteraction()

    with caplog.at_level(logging.ERROR):
        await report(interaction, raised_by_command(RuntimeError("boom")))

    assert interaction.response.sent == [(ERROR_REPLY, True)]
    [record] = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert record.getMessage() == "Error in /add"
    assert record.exc_info is not None


async def test_reply_is_a_followup_once_the_interaction_was_answered() -> None:
    interaction = FakeInteraction(answered=True)

    await report(interaction, InvalidFilm("Nope."))

    assert interaction.followup.sent == [("Nope.", True)]
    assert interaction.response.sent == []


async def test_a_reply_that_fails_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    interaction = FakeInteraction()
    interaction.response = ExpiredResponse(done=False)

    await report(interaction, InvalidFilm("Nope."))

    assert any("Couldn't send" in record.getMessage() for record in caplog.records)
