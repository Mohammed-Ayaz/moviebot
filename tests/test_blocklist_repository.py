"""BlocklistRepository: the do-not-watch list's SQL, on a fresh in-memory database."""

from moviebot.db.blocklist import BlocklistRepository


async def test_add_leaves_an_existing_entry_alone(blocklist: BlocklistRepository) -> None:
    assert await blocklist.add("Humshakals", 2014, "Nothing happens.")
    assert not await blocklist.add("Humshakals", 2014, "Said again")
    assert await blocklist.add("No Year", None, "First")
    assert not await blocklist.add("No Year", None, "Second")  # even without a year

    entries = await blocklist.list_all()

    assert [(entry.label, entry.reason) for entry in entries] == [
        ("Humshakals (2014)", "Nothing happens."),
        ("No Year", "First"),
    ]
