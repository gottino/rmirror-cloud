"""Registry of sync targets: how to build each one and which items it accepts.

Every place that decides "which integrations get this item" or "which class
handles this integration" reads it from here, so adding a target means adding
one entry instead of editing if/elif chains and hard-coded name lists.

Item types are the ``SyncQueue.item_type`` values the worker processes:
``page_text`` (a page's OCR text), ``notebook_metadata`` (notebook properties
only) and ``todo``. A target with no push item types (Obsidian) is pull-based
and never gets queue rows.
"""

from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

from app.core.sync_engine import SyncTarget
from app.integrations.notion_sync import NotionSyncTarget
from app.integrations.notion_todos_sync import NotionTodosSyncTarget
from app.integrations.todoist_sync import TodoistSyncTarget

PAGE_TEXT = "page_text"
NOTEBOOK_METADATA = "notebook_metadata"
TODO = "todo"


@dataclass(frozen=True)
class TargetSpec:
    """How to build a target from its decrypted config, and what it accepts."""

    name: str
    factory: Optional[Callable[[dict], SyncTarget]]
    item_types: FrozenSet[str]
    required_config: Tuple[str, ...] = ()


# Factories are lambdas so the class is looked up when called (tests patch it here).
_TARGETS: Dict[str, TargetSpec] = {
    spec.name: spec
    for spec in (
        TargetSpec(
            name="notion",
            factory=lambda cfg: NotionSyncTarget(
                access_token=cfg.get("access_token"),
                database_id=cfg.get("database_id"),
            ),
            item_types=frozenset({PAGE_TEXT, NOTEBOOK_METADATA}),
            required_config=("access_token", "database_id"),
        ),
        TargetSpec(
            name="notion-todos",
            factory=lambda cfg: NotionTodosSyncTarget(
                access_token=cfg.get("access_token"),
                database_id=cfg.get("database_id"),
                use_status_property=cfg.get("use_status_property", False),
            ),
            item_types=frozenset({TODO}),
            required_config=("access_token", "database_id"),
        ),
        TargetSpec(
            name="todoist",
            factory=lambda cfg: TodoistSyncTarget(
                access_token=cfg.get("access_token"),
                project_id=cfg.get("project_id"),
            ),
            item_types=frozenset({TODO}),
            required_config=("access_token",),
        ),
        # Pull-based: the Obsidian plugin fetches through its own endpoints.
        TargetSpec(name="obsidian", factory=None, item_types=frozenset()),
    )
}


def get_spec(target_name: str) -> Optional[TargetSpec]:
    """The spec for a target name, or None for an unknown target."""
    return _TARGETS.get(target_name)


def supports(target_name: str, item_type: str) -> bool:
    """True if queue rows of ``item_type`` should be created for this target."""
    spec = _TARGETS.get(target_name)
    return spec is not None and item_type in spec.item_types


def targets_supporting(item_type: str) -> List[str]:
    """Names of all targets that accept ``item_type``."""
    return sorted(name for name, spec in _TARGETS.items() if item_type in spec.item_types)


def missing_config(target_name: str, config: dict) -> List[str]:
    """Required config keys that are absent or empty."""
    spec = _TARGETS.get(target_name)
    if spec is None:
        return []
    return [key for key in spec.required_config if not config.get(key)]


def create_target(target_name: str, config: dict) -> SyncTarget:
    """Build the push target for ``target_name``.

    Raises:
        ValueError: unknown target, or a pull-based target with no push class.
    """
    spec = _TARGETS.get(target_name)
    if spec is None or spec.factory is None:
        raise ValueError(f"Unknown target: {target_name}")
    return spec.factory(config)
