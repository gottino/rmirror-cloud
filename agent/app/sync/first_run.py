"""
First-run suggestion: which notebooks to sync first so the sync fits the quota.

Pure logic, no I/O. Used by ``GET /api/v2/first-run/suggestion``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.remarkable.library import DocumentInfo

REASON_OK = "ok"
REASON_NO_NOTEBOOKS = "no_notebooks"
REASON_QUOTA_EXHAUSTED = "quota_exhausted"
REASON_NOT_SIGNED_IN = "not_signed_in"
REASON_FOLDER_UNAVAILABLE = "folder_unavailable"


@dataclass
class Suggestion:
    reason: str
    notebooks: list[DocumentInfo] = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return sum(nb.page_count for nb in self.notebooks)


def choose_notebooks(
    documents: Sequence[DocumentInfo], remaining: int | None, max_count: int
) -> list[DocumentInfo]:
    """The most recently opened notebooks (fallback: last modified) that together fit ``remaining``.

    - Notebooks without pages are never suggested.
    - A notebook that does not fit what is left is skipped and the next one tried.
    - ``remaining`` None means unlimited: the ``max_count`` most recent notebooks.
    - The sum of the chosen page counts never exceeds ``remaining``.
    """
    if max_count <= 0:
        return []
    ordered = sorted(
        (doc for doc in documents if doc.page_count > 0),
        key=lambda doc: (doc.recency, doc.uuid),
        reverse=True,
    )
    chosen: list[DocumentInfo] = []
    left = remaining
    for doc in ordered:
        if len(chosen) >= max_count:
            break
        if left is not None:
            if doc.page_count > left:
                continue
            left -= doc.page_count
        chosen.append(doc)
    return chosen


def suggest_first_sync(
    *,
    signed_in: bool,
    folder_ok: bool,
    documents: Sequence[DocumentInfo],
    remaining: int | None,
    max_count: int,
) -> Suggestion:
    """Full rule including the reason code (first matching reason wins)."""
    if not signed_in:
        return Suggestion(REASON_NOT_SIGNED_IN)
    if not folder_ok:
        return Suggestion(REASON_FOLDER_UNAVAILABLE)
    if not any(doc.page_count > 0 for doc in documents):
        return Suggestion(REASON_NO_NOTEBOOKS)
    if remaining is not None and remaining <= 0:
        return Suggestion(REASON_QUOTA_EXHAUSTED)
    return Suggestion(REASON_OK, choose_notebooks(documents, remaining, max_count))
