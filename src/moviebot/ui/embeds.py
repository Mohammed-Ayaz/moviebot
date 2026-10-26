"""Embeds and texts: the film card, the suggestion card, one page of /list, /about, and the
private reply to /add."""

import discord

from moviebot.models import AddedFilm, Category, Film, FilmPage, Suggestion

LIST_TITLES = {"unwatched": "Unwatched films", "watched": "Watched films", "all": "All films"}
EMPTY_LIST = "Nothing here yet. Add a film with /add."
POSTER_URL = "https://image.tmdb.org/t/p/w500{path}"
TMDB_NOTICE = "This product uses the TMDB API but is not endorsed or certified by TMDB."
LOGO_FILENAME = "tmdb-logo.png"
SIDE_LABELS = {"bad": "hate-watch", "good": "actually good"}


def film_card(film: Film, category: Category | None) -> discord.Embed:
    """A film's card: 'Title (Year)', the note, why to watch it, runtime, category, poster."""
    embed = discord.Embed(title=film.label, description=film.note)
    if film.why_watch:
        embed.add_field(name="Why watch it", value=film.why_watch, inline=False)
    if film.runtime_min:
        embed.add_field(name="Runtime", value=_runtime(film.runtime_min))
    if category is not None:
        embed.add_field(name="Category", value=category.name)
    if film.added_by is not None:
        embed.add_field(name="Added by", value=f"<@{film.added_by}>")
    if film.poster_path:
        embed.set_image(url=POSTER_URL.format(path=film.poster_path))
    if film.tmdb_id is not None:
        embed.set_footer(text="Film data from TMDB")
    return embed


def added_text(added: AddedFilm) -> str:
    """The private reply to /add: what was added, and anything the adder should know."""
    lines = [f"Added {discord.utils.escape_markdown(added.film.label)}."]
    if added.tmdb == "not_found":
        lines.append("It's saved without a poster. Next time, pick the film from the list.")
    elif added.tmdb == "unavailable":
        lines.append("TMDB isn't answering, so it's saved without a poster.")
    if added.same_title is not None:
        same = discord.utils.escape_markdown(added.same_title.label)
        lines.append(f"Heads up: {same} is already on the list, so this may be a duplicate.")
    return "\n".join(lines)


def suggestion_card(suggestion: Suggestion) -> discord.Embed:
    """A suggestion (FR-8): the film card, headed with anything the pick was narrowed to."""
    embed = film_card(suggestion.film, suggestion.category)
    filters = suggestion.filters
    narrowed = [
        suggestion.category.name if filters.category_key and suggestion.category else None,
        filters.genre,
        SIDE_LABELS.get(filters.side) if filters.side else None,
    ]
    parts = [part for part in narrowed if part]
    embed.set_author(name="Suggestion for tonight" + (f" · {', '.join(parts)}" if parts else ""))
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


def about_embed(*, with_logo: bool) -> discord.Embed:
    """/about: what the bot is, then TMDB's required notice and logo (FR-6, NFR-8).

    The logo is a small thumbnail beside the text, so it stays less prominent than the bot's name.
    """
    embed = discord.Embed(
        title="Movie Night Bot", description="A shared watchlist for our movie nights."
    )
    embed.add_field(name="Film data", value=TMDB_NOTICE, inline=False)
    if with_logo:
        embed.set_thumbnail(url=f"attachment://{LOGO_FILENAME}")
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


def _runtime(minutes: int) -> str:
    """146 -> '2 h 26 min'."""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} min"
    return f"{hours} h {rest} min" if rest else f"{hours} h"
