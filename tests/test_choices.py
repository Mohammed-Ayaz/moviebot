"""category_choices: what /add, /list and /suggest offer while someone types a category."""

from moviebot.models import Category
from moviebot.ui.choices import category_choices

CATEGORIES = [
    Category(key="launch", name="The launch", position=1, side="bad"),
    Category(key="noir", name="A nobody in over his head", position=12, side="good"),
]


def test_category_choices_match_the_name_or_the_key() -> None:
    assert [choice.value for choice in category_choices(CATEGORIES, "LAUN")] == ["launch"]
    assert [choice.value for choice in category_choices(CATEGORIES, "nobody")] == ["noir"]
    assert [choice.value for choice in category_choices(CATEGORIES, "")] == ["launch", "noir"]
    assert [choice.name for choice in category_choices(CATEGORIES, "noir")] == [
        "A nobody in over his head"
    ]
