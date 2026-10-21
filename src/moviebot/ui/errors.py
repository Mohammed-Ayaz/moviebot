"""Turning errors into private replies, for slash commands and buttons alike."""

import logging
import math

import discord
from discord import app_commands

from moviebot.models import DomainError

log = logging.getLogger(__name__)

ERROR_REPLY = "Something went wrong."


async def report_error(interaction: discord.Interaction, error: Exception) -> None:
    """Tell the user privately what went wrong. Never raises.

    A broken rule (a DomainError) or a cooldown is expected, so the user sees its message and
    nothing is logged. Anything else is a bug: its traceback is logged, and the user only sees
    "Something went wrong."
    """
    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original
    if isinstance(error, DomainError):
        text = str(error)
    elif isinstance(error, app_commands.CommandOnCooldown):
        seconds = max(1, math.ceil(error.retry_after))
        text = f"Slow down: try again in {seconds} second{'' if seconds == 1 else 's'}."
    else:
        where = f"/{interaction.command.qualified_name}" if interaction.command else "a button"
        log.error("Error in %s", where, exc_info=error)
        text = ERROR_REPLY
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        log.warning("Couldn't send the error reply", exc_info=True)
