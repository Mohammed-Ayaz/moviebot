"""CategoryRepository: all the SQL for the categories table."""

from moviebot.db.database import Database
from moviebot.models import Category


class CategoryRepository:
    """Reads and adds categories. The seed import (M6) fills this table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_all(self) -> list[Category]:
        """Every category, in display order."""
        rows = await self._db.conn.execute_fetchall(
            "SELECT * FROM categories ORDER BY position, key"
        )
        return [Category(**dict(row)) for row in rows]

    async def get(self, key: str) -> Category | None:
        """The category with this key, if there is one."""
        rows = await self._db.conn.execute_fetchall(
            "SELECT * FROM categories WHERE key = ?", (key,)
        )
        return next((Category(**dict(row)) for row in rows), None)

    async def add(self, category: Category) -> bool:
        """Insert a category, leaving an existing key as it is. Returns whether it was added."""
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO categories (key, name, position, side, blurb)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (key) DO NOTHING
                """,
                (category.key, category.name, category.position, category.side, category.blurb),
            )
            added = cursor.rowcount > 0
            await cursor.close()
        return added
