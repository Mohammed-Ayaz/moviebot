"""Who counts as an admin, and how /export is hidden from everyone else."""

from types import SimpleNamespace
from typing import Any, cast

import pytest

from moviebot.bot import MovieBot
from moviebot.cogs.admin import is_admin

ADMIN_ROLE = 555


def member(*, manage_guild: bool = False, roles: tuple[int, ...] = ()) -> Any:
    """Just enough of discord.Member for is_admin."""
    return SimpleNamespace(
        guild_permissions=SimpleNamespace(manage_guild=manage_guild),
        roles=[SimpleNamespace(id=role) for role in roles],
    )


@pytest.mark.parametrize(
    ("user", "admin_role_id", "expected"),
    [
        (member(manage_guild=True), None, True),
        (member(roles=(ADMIN_ROLE,)), ADMIN_ROLE, True),
        (member(roles=(ADMIN_ROLE,)), None, False),
        (member(roles=(1, 2)), ADMIN_ROLE, False),
        (SimpleNamespace(), ADMIN_ROLE, False),  # a user outside the server has no roles
    ],
)
def test_an_admin_has_manage_server_or_the_admin_role(
    user: Any, admin_role_id: int | None, expected: bool
) -> None:
    assert is_admin(cast(Any, user), admin_role_id) is expected


def test_export_is_hidden_from_members_without_manage_server(bot: MovieBot) -> None:
    command = bot.tree.get_command("export")

    assert command is not None
    permissions = getattr(command, "default_permissions", None)
    assert permissions is not None
    assert permissions.manage_guild
