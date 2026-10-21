"""What the services hand back, and the errors they raise. Plain dataclasses: no discord, no SQL."""

from dataclasses import dataclass, field
from typing import Literal

Show = Literal["unwatched", "watched", "all"]


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


@dataclass(frozen=True)
class AddedFilm:
    """What adding a film returns."""

    film: Film
    category: Category | None
    same_title: Film | None  # added without a year: a film with the same title already listed


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
