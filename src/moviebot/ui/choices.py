"""Choices offered while someone types an option."""

from discord import app_commands

from moviebot.models import Category


def category_choices(categories: list[Category], typed: str) -> list[app_commands.Choice[str]]:
    """Up to 25 categories whose name or key contains what has been typed so far."""
    typed = typed.lower()
    return [
        app_commands.Choice(name=category.name, value=category.key)
        for category in categories
        if typed in category.name.lower() or typed in category.key
    ][:25]
