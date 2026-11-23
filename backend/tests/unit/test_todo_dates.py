"""Todos carry the date written on their page.

The OCR puts a page's handwritten date first ("**Date: dd-mm-yyyy**"). Todo
extraction stores it as ``todos.date_extracted`` and the todo targets get it
(Notion: "Date Written"). A todo whose page date appears or changes is
synced again; todos without a date keep their sync fingerprint.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from app.models.page import Page
from app.models.sync_record import SyncQueue
from app.processors.todo_extractor import extract_page_date
from app.services.fingerprinting import fingerprint_todo
from scripts.backfill_todo_dates import backfill
from tests.test_config import test_app  # noqa: F401 - fixture
from tests.unit.test_todo_pipeline import (  # noqa: F401 - fixture
    FakeTodoist,
    _enable,
    _run_worker,
    _todos,
    api,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("**Date: 20-11-2026**\n---\n- [ ] Buy milk", datetime(2026, 11, 20)),
        ("Date: 3.4.2026\n- [ ] x", datetime(2026, 4, 3)),
        ("\n\n**Date:** 05/01/26\n", datetime(2026, 1, 5)),
        ("# Errands\n**Date: 01-02-2026**", datetime(2026, 2, 1)),
        ("- [ ] Buy milk", None),
        ("**Date: 31-02-2026**", None),  # impossible date
        ("a\nb\nc\nd\ne\nDate: 01-02-2026", None),  # too far down the page
        ("Call about the date: 12-12-2026 meeting", None),  # not a date line
        (None, None),
    ],
)
def test_extract_page_date(text, expected):
    assert extract_page_date(text) == expected


def test_fingerprint_unchanged_without_a_date():
    assert fingerprint_todo("Buy milk", False, "nb", 1) == fingerprint_todo(
        "Buy milk", False, "nb", 1, None
    )
    assert fingerprint_todo("Buy milk", False, "nb", 1) != fingerprint_todo(
        "Buy milk", False, "nb", 1, datetime(2026, 11, 20)
    )


@pytest.mark.asyncio
async def test_new_todos_get_the_page_date_and_sync_it(db, api):  # noqa: F811
    upload, _, user = api
    _enable(db, user.id, "todoist")

    upload("**Date: 20-11-2026**\n---\n- [ ] Buy milk")

    [todo] = _todos(db)
    assert todo.date_extracted == datetime(2026, 11, 20)
    fake = FakeTodoist()
    await _run_worker(db, fake)
    assert [c["date_extracted"] for c in fake.created] == ["2026-11-20"]


@pytest.mark.asyncio
async def test_date_added_later_updates_the_same_task(db, api):  # noqa: F811
    upload, _, user = api
    _enable(db, user.id, "todoist")
    upload("- [ ] Buy milk")
    fake = FakeTodoist()
    await _run_worker(db, fake)
    assert fake.created[0]["date_extracted"] is None

    upload("**Date: 20-11-2026**\n---\n- [ ] Buy milk")
    await _run_worker(db, fake)

    [todo] = _todos(db)
    assert todo.date_extracted == datetime(2026, 11, 20)
    assert len(fake.created) == 1
    assert [(ext, data["date_extracted"]) for ext, data in fake.updated] == [("task_1", "2026-11-20")]


@pytest.mark.asyncio
async def test_page_without_date_line_keeps_the_todo_date(db, api):  # noqa: F811
    upload, _, user = api
    _enable(db, user.id, "todoist")
    upload("**Date: 20-11-2026**\n- [ ] Buy milk")
    fake = FakeTodoist()
    await _run_worker(db, fake)

    upload("- [ ] Buy milk\nmore notes")
    await _run_worker(db, fake)

    [todo] = _todos(db)
    assert todo.date_extracted == datetime(2026, 11, 20)
    assert fake.updated == []


@pytest.mark.asyncio
async def test_backfill_sets_missing_dates_and_queues_them(db, api):  # noqa: F811
    upload, _, user = api
    _enable(db, user.id, "todoist")
    fake = FakeTodoist()
    # As before this change: the page date was not read, todos stored and
    # synced without it.
    with patch("app.processors.todo_extractor.extract_page_date", return_value=None):
        upload("**Date: 20-11-2026**\n- [ ] Buy milk\n- [ ] Call Bob")
    await _run_worker(db, fake)
    assert all(t.date_extracted is None for t in _todos(db))

    dry = backfill(db, apply=False)
    assert dry == {"todos_without_date": 2, "pages": 1, "dated": 2, "pages_dated": 1}
    assert all(t.date_extracted is None for t in _todos(db))

    applied = backfill(db, apply=True)
    assert applied["dated"] == 2
    assert {t.date_extracted for t in _todos(db)} == {datetime(2026, 11, 20)}
    await _run_worker(db, fake)
    assert sorted(data["date_extracted"] for _, data in fake.updated) == ["2026-11-20"] * 2

    # Running it again finds nothing to do.
    assert backfill(db, apply=True)["todos_without_date"] == 0


def test_backfill_skips_pages_without_a_date(db, api):  # noqa: F811
    upload, _, _ = api
    upload("- [ ] Buy milk")

    counts = backfill(db, apply=True)

    assert counts == {"todos_without_date": 1, "pages": 1, "dated": 0, "pages_dated": 0}
    assert db.query(SyncQueue).filter_by(item_type="todo").count() == 0
    assert db.query(Page).count() == 1
