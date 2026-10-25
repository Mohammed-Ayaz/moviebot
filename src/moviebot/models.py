"""What the services hand back, and the errors they raise. Plain dataclasses: no discord, no SQL."""

from dataclasses import dataclass, field
from typing import Literal

Show = Literal["unwatched", "watched", "all"]
TmdbResult = Literal["found", "not_found", "unavailable"]  # how TMDB went when adding a film


@dataclass(frozen=True)
class Category:
    """One row of the categories table, such as key 'launch', name 'The launch'."""

    key: str
    name: str
    position: int
    side: str
    blurb: str | None = None


@dataclass(frozen=True)
class Film:
    """One row of the films table."""

    id: int
    slug: str
    tmdb_id: int | None
    title: str
    year: int | None
    category_key: str | None
    side: str | None
    genre: str | None
    is_indian: bool
    grade: str | None
    note: str | None
    why_watch: str | None
    poster_path: str | None
    runtime_min: int | None
    tmdb_synced_at: str | None
    added_by: int | None
    added_at: str
    watched_at: str | None

    @property
    def label(self) -> str:
        """'Title (Year)', or just the title when the year isn't known."""
        return self.title if self.year is None else f"{self.title} ({self.year})"


@dataclass(frozen=True)
class TmdbMovie:
    """A film as TMDB describes it. Search results leave runtime_min empty; details fill it in."""

    id: int
    title: str
    year: int | None
    poster_path: str | None
    runtime_min: int | None = None

    @property
    def label(self) -> str:
        """'Title (Year)', or just the title when TMDB has no release date."""
        return self.title if self.year is None else f"{self.title} ({self.year})"


@dataclass(frozen=True)
class NewFilm:
    """A film to insert. The database fills in its id and added_at."""

    slug: str
    title: str
    year: int | None
    tmdb_id: int | None = None
    category_key: str | None = None
    note: str | None = None
    added_by: int | None = None
    watched_at: str | None = None
    poster_path: str | None = None
    runtime_min: int | None = None
    tmdb_synced_at: str | None = None
    side: str | None = None
    genre: str | None = None


@dataclass(frozen=True)
class AddedFilm:
    """What adding a film returns."""

    film: Film
    category: Category | None
    same_title: Film | None  # added without a year: a film with the same title already listed
    tmdb: TmdbResult


@dataclass(frozen=True)
class FilmInfo:
    """A film with its category, which is what a film card needs."""

    film: Film
    category: Category | None


@dataclass(frozen=True)
class FilmPage:
    """One page of /list, with the filters that produced it."""

    films: tuple[Film, ...]
    page: int
    page_count: int
    per_page: int
    total: int
    show: Show
    category: Category | None
    category_names: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SuggestFilters:
    """What /suggest was narrowed to. Another keeps the same filters."""

    category_key: str | None = None
    genre: str | None = None
    side: str | None = None  # "bad" for a hate-watch, "good" for actually good

    @property
    def active(self) -> bool:
        """Whether any filter is set."""
        return any((self.category_key, self.genre, self.side))


@dataclass(frozen=True)
class Suggestion:
    """A film the picker chose, with what its card needs."""

    film: Film
    category: Category | None
    filters: SuggestFilters


class DomainError(Exception):
    """A business rule said no. str(error) is a short message that is safe to show users."""


class InvalidFilm(DomainError):
    """The title, year or note isn't acceptable."""


class UnknownCategory(DomainError):
    """No category has this key."""

    def __init__(self, key: str) -> None:
        super().__init__(f'There\'s no category called "{key}".')
        self.key = key


class DuplicateFilm(DomainError):
    """The film is already on the list (FR-4)."""

    def __init__(self, existing: Film) -> None:
        super().__init__(f"{existing.label} is already on the list.")
        self.existing = existing


class TmdbUnavailable(DomainError):
    """TMDB didn't answer while adding a film picked from its suggestions."""

    def __init__(self) -> None:
        super().__init__(
            "TMDB isn't answering right now, so the film you picked can't be added. "
            "Try again in a minute, or type the title without picking a suggestion."
        )


class NothingToSuggest(DomainError):
    """No unwatched film is left to suggest (FR-7)."""

    def __init__(self, *, filtered: bool) -> None:
        super().__init__(
            "No unwatched films match those filters."
            if filtered
            else "Nothing left to suggest. Add some films with /add."
        )


class FilmNotFound(DomainError):
    """The film isn't on the list, for example because it was removed."""

    def __init__(self) -> None:
        super().__init__("That film isn't on the list any more.")


class AlreadyWatched(DomainError):
    """The film was already marked as watched."""

    def __init__(self, film: Film) -> None:
        super().__init__(f"{film.label} is already marked as watched.")
        self.film = film


class UnknownFilm(DomainError):
    """No film on the list has the title someone typed."""

    def __init__(self, title: str) -> None:
        super().__init__(
            f'There\'s no film called "{title}" on the list. Pick one from the suggestions.'
        )
        self.title = title


class AmbiguousFilm(DomainError):
    """Several films on the list have the title someone typed."""

    def __init__(self, title: str) -> None:
        super().__init__(f'Several films are called "{title}". Pick one from the suggestions.')
        self.title = title


class NotWatched(DomainError):
    """The film isn't marked as watched."""

    def __init__(self, film: Film) -> None:
        super().__init__(f"{film.label} isn't marked as watched.")
        self.film = film
