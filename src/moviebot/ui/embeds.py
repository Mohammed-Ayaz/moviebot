"""Embeds: the film card and one page of /list."""

import discord

from moviebot.models import Category, Film, FilmPage

LIST_TITLES = {"unwatched": "Unwatched films", "watched": "Watched films", "all": "All films"}
EMPTY_LIST = "Nothing here yet. Add a film with /add."


def film_card(film: Film, category: Category | None) -> discord.Embed:
    """A film's card. Its poster and runtime arrive with TMDB in M3, why_watch in M8."""
    embed = discord.Embed(title=film.label, description=film.note)
    if category is not None:
        embed.add_field(name="Category", value=category.name)
    if film.added_by is not None:
        embed.add_field(name="Added by", value=f"<@{film.added_by}>")
    return embed


def list_embed(page: FilmPage) -> discord.Embed:
    """One page of /list: numbered 'Title (Year)' lines, with the page number in the footer."""
    title = LIST_TITLES[page.show]
    if page.category is not None:
        title = f"{title} · {page.category.name}"
    first = (page.page - 1) * page.per_page + 1
    lines = [_list_line(number, film, page) for number, film in enumerate(page.films, first)]
    embed = discord.Embed(title=title, description="\n".join(lines) or EMPTY_LIST)
    films = "film" if page.total == 1 else "films"
    embed.set_footer(text=f"Page {page.page} of {page.page_count} · {page.total} {films}")
    return embed


def _list_line(number: int, film: Film, page: FilmPage) -> str:
    line = f"{number}. {discord.utils.escape_markdown(film.label)}"
    if page.category is None and film.category_key is not None:
        name = page.category_names.get(film.category_key)
        if name:
            line += f" · {name}"
    if page.show == "all" and film.watched_at is not None:
        line += " (watched)"
    return line
