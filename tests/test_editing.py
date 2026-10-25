"""Confirm and Cancel under /remove, and the /edit pop-up, driven the way Discord drives them."""

from typing import Any, cast

import discord
import pytest

from moviebot.models import Category, Film, FilmNotFound
from moviebot.services.watchlist import WatchlistService
from moviebot.ui.modals import EditFilmModal
from moviebot.ui.views import ConfirmRemoveView

ASKER = 111
SOMEONE_ELSE = 222


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.mention = f"<@{user_id}>"


class FakeResponse:
    def __init__(self) -> None:
        self.done = False
        self.edits: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []

    def is_done(self) -> bool:
        return self.done

    async def edit_message(self, **fields: Any) -> None:
        self.done = True
        self.edits.append(fields)

    async def send_message(self, content: str, **fields: Any) -> None:
        self.done = True
        self.sent.append({"content": content, **fields})


class FakeFollowup:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, content: str, **fields: Any) -> None:
        self.sent.append({"content": content, **fields})


class FakeInteraction:
    """Just enough of discord.Interaction for a click, a form, or the /remove it answers."""

    def __init__(self, user_id: int = ASKER) -> None:
        self.user = FakeUser(user_id)
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.command = None
        self.original_edits: list[dict[str, Any]] = []

    async def edit_original_response(self, **fields: Any) -> None:
        self.original_edits.append(fields)


def real(interaction: FakeInteraction) -> discord.Interaction:
    return cast(discord.Interaction, interaction)


def type_into(field: discord.ui.TextInput, text: str) -> None:
    """What discord.py does with what the person typed when the form comes back."""
    field._value = text


async def add(
    watchlist: WatchlistService, title: str = "Heropanti", note: str | None = None
) -> Film:
    return (await watchlist.add_film(title=title, year=2014, note=note)).film


async def test_confirm_removes_the_film_and_says_publicly_who_did(
    watchlist: WatchlistService,
) -> None:
    film = await add(watchlist)
    view = ConfirmRemoveView(watchlist, film, user_id=ASKER)
    click = FakeInteraction()

    await view.confirm.callback(real(click))

    assert click.response.edits == [{"content": "Removed Heropanti (2014).", "view": None}]
    assert click.followup.sent == [{"content": "<@111> removed Heropanti (2014) from the list."}]
    assert view.is_finished()
    with pytest.raises(FilmNotFound):
        await watchlist.get_film(film.id)


async def test_cancel_keeps_the_film(watchlist: WatchlistService) -> None:
    film = await add(watchlist)
    view = ConfirmRemoveView(watchlist, film, user_id=ASKER)
    click = FakeInteraction()

    await view.cancel.callback(real(click))

    assert click.response.edits == [{"content": "Kept Heropanti (2014).", "view": None}]
    assert click.followup.sent == []
    assert view.is_finished()
    assert (await watchlist.get_film(film.id)).title == "Heropanti"


async def test_confirm_after_someone_else_removed_it_says_so(
    watchlist: WatchlistService,
) -> None:
    film = await add(watchlist)
    view = ConfirmRemoveView(watchlist, film, user_id=ASKER)
    await watchlist.remove_film(film.id)
    click = FakeInteraction()

    await view.confirm.callback(real(click))

    assert click.response.edits == [
        {"content": "That film isn't on the list any more.", "view": None}
    ]
    assert click.followup.sent == []


async def test_only_the_person_who_asked_can_answer(watchlist: WatchlistService) -> None:
    view = ConfirmRemoveView(watchlist, await add(watchlist), user_id=ASKER)

    assert await view.interaction_check(real(FakeInteraction(ASKER)))
    assert not await view.interaction_check(real(FakeInteraction(SOMEONE_ELSE)))


async def test_an_expired_question_loses_its_buttons(watchlist: WatchlistService) -> None:
    film = await add(watchlist)
    view = ConfirmRemoveView(watchlist, film, user_id=ASKER)
    asked = FakeInteraction()
    view.interaction = real(asked)

    await view.on_timeout()

    assert asked.original_edits == [
        {"content": "Nothing was removed: this question expired.", "view": None}
    ]
    assert (await watchlist.get_film(film.id)).title == "Heropanti"


async def test_the_edit_form_starts_with_the_current_note(watchlist: WatchlistService) -> None:
    film = await add(watchlist, note="Peak Tiger Shroff.")

    modal = EditFilmModal(watchlist, film, category_key=None)

    assert modal.title == "Edit Heropanti (2014)"
    assert modal.note.default == "Peak Tiger Shroff."


async def test_a_long_title_is_shortened_to_fit_the_form(watchlist: WatchlistService) -> None:
    modal = EditFilmModal(watchlist, await add(watchlist, title="A" * 80), category_key=None)

    assert len(modal.title) == 45
    assert modal.title.endswith("…")


async def test_saving_the_form_changes_the_note_and_the_category(
    watchlist: WatchlistService, launch: Category
) -> None:
    film = await add(watchlist, note="Old note")
    modal = EditFilmModal(watchlist, film, category_key="launch")
    type_into(modal.note, "New note")
    submit = FakeInteraction()

    await modal.on_submit(real(submit))

    saved = await watchlist.get_film(film.id)
    assert (saved.note, saved.category_key) == ("New note", "launch")
    [reply] = submit.response.sent
    assert (reply["content"], reply["ephemeral"]) == ("Saved.", True)
    assert reply["embed"].description == "New note"


async def test_emptying_the_note_clears_it(watchlist: WatchlistService) -> None:
    film = await add(watchlist, note="Old note")
    modal = EditFilmModal(watchlist, film, category_key=None)
    type_into(modal.note, "")

    await modal.on_submit(real(FakeInteraction()))

    assert (await watchlist.get_film(film.id)).note is None
