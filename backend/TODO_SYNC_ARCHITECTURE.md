# Todo Sync Architecture

## Overview

Todos extracted from notebooks should be synced as **separate integrations** rather than being bundled with notebook sync. This provides maximum flexibility for users.

## Architecture Decision

### Separate Integration Model

Users can configure **independent integrations** for different content types:

1. **Notebook Integration** (e.g., "Notion Notebooks")
   - Syncs notebook pages and content
   - Target: Notion database with notebook schema

2. **Todo Integration** (e.g., "Notion Todos", "Todoist", "TickTick")
   - Syncs extracted todos from all notebooks
   - Target: Todo-specific database or service
   - Can be a different service than notebooks!

### Benefits

1. **Flexibility**: User can sync notebooks to Notion but todos to Todoist
2. **Simplicity**: Each integration has a single, clear purpose
3. **Extensibility**: Easy to add new todo services (Todoist, TickTick, etc.)
4. **User Control**: Users can enable/disable todo sync independently
5. **Better UX**: Clear separation in settings UI

## Implementation Plan

### Database Schema (Already Exists!)

The `IntegrationConfig` table already supports this:

```sql
CREATE TABLE integration_configs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    target_name VARCHAR(50) NOT NULL,  -- "notion", "notion-todos", "todoist", etc.
    is_enabled BOOLEAN DEFAULT TRUE,
    config_encrypted TEXT NOT NULL,
    UNIQUE(user_id, target_name)
);
```

### Integration Types

We'll have these `target_name` values:

- `notion` - Notebooks sync to Notion
- `notion-todos` - Todos sync to Notion database
- `todoist` - Todos sync to Todoist (future)
- `ticktick` - Todos sync to TickTick (future)
- `readwise` - Highlights sync to Readwise (future)

### SyncTarget Implementations

Each integration is a separate `SyncTarget`:

```python
# Existing
class NotionSyncTarget(SyncTarget):
    """Syncs notebooks and pages to Notion database."""
    target_name = "notion"
    supported_types = [SyncItemType.NOTEBOOK, SyncItemType.PAGE_TEXT]

# New
class NotionTodosSyncTarget(SyncTarget):
    """Syncs todos to Notion database."""
    target_name = "notion-todos"
    supported_types = [SyncItemType.TODO]

# Future
class TodoistSyncTarget(SyncTarget):
    """Syncs todos to Todoist."""
    target_name = "todoist"
    supported_types = [SyncItemType.TODO]
```

### Sync Queue Behavior

When a todo is extracted from OCR:

1. System calls `queue_todo_sync(db, user_id, todo_id, ...)`
2. Queue service looks up **all enabled integrations** for this user
3. For each integration where `target_name` supports `SyncItemType.TODO`:
   - Queue a sync job
4. Background worker processes queue and calls appropriate `SyncTarget`

**Example**: User has both `notion` and `notion-todos` enabled:
- Notebook pages → synced to `notion` integration
- Todos → synced to `notion-todos` integration
- Result: Same Notion workspace, two different databases

### Configuration Flow

#### Option 1: Notion for Both (Two Databases)

1. User connects "Notion" integration
   - OAuth flow
   - Create/select **notebooks database**
   - Stores config with `database_id`

2. User connects "Notion Todos" integration
   - Reuse same OAuth token (already have it!)
   - Create/select **todos database**
   - Stores config with `todos_database_id`

#### Option 2: Mixed Services

1. User connects "Notion" for notebooks
2. User connects "Todoist" for todos
   - Different OAuth flow
   - Todoist API credentials
   - Syncs to Todoist projects

### API Endpoints

#### Generic Integration Endpoints (Already Exist)
```
POST   /v1/integrations/                    # Create any integration
GET    /v1/integrations/                    # List all integrations
DELETE /v1/integrations/{target_name}       # Delete integration
```

#### Notion-Specific Endpoints
```
# Shared OAuth (both "notion" and "notion-todos" use same token)
GET  /v1/integrations/notion/oauth/authorize
POST /v1/integrations/notion/oauth/callback

# Database selection (specify type in request)
GET  /v1/integrations/notion/databases
POST /v1/integrations/notion/databases/create  # type: "notebooks" or "todos"
POST /v1/integrations/notion/databases/{id}/select  # type: "notebooks" or "todos"
```

#### Future: Todoist Endpoints
```
GET  /v1/integrations/todoist/oauth/authorize
POST /v1/integrations/todoist/oauth/callback
GET  /v1/integrations/todoist/projects
```

### Frontend UX

**Settings → Integrations Page**

```
┌─────────────────────────────────────────┐
│ Integrations                            │
├─────────────────────────────────────────┤
│                                         │
│ Notebooks                               │
│ ┌─────────────────────────────────────┐ │
│ │ [Notion Logo] Notion                │ │
│ │ Status: Connected                   │ │
│ │ Database: "My Notebooks"            │ │
│ │ [Configure] [Disconnect]            │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ Todos                                   │
│ ┌─────────────────────────────────────┐ │
│ │ [Notion Logo] Notion Todos          │ │
│ │ Status: Connected                   │ │
│ │ Database: "rMirror Tasks"           │ │
│ │ [Configure] [Disconnect]            │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ [Todoist Logo] Todoist              │ │
│ │ Status: Not connected               │ │
│ │ [Connect]                           │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ Highlights (Coming Soon)                │
│ ┌─────────────────────────────────────┐ │
│ │ [Readwise Logo] Readwise            │ │
│ │ Status: Coming soon                 │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### Implementation Steps

1. ✅ Keep existing `NotionSyncTarget` for notebooks
2. ✅ Update OAuth service to support `database_type` parameter
3. ✅ Create `NotionTodosSyncTarget` class
4. 🔄 Update integration config to distinguish `notion` vs `notion-todos`
5. 🔄 Update sync queue to route todos to todo-specific integrations
6. 🔄 Frontend: Separate "Connect Notion Todos" button
7. 🔄 Frontend: Database setup wizard for todos

### Code Changes Needed

#### 1. Create NotionTodosSyncTarget

```python
# app/integrations/notion_todos_sync.py
class NotionTodosSyncTarget(SyncTarget):
    """Notion integration for syncing todos to a dedicated database."""

    def __init__(self, access_token: str, database_id: str):
        super().__init__("notion-todos")
        self.access_token = access_token
        self.database_id = database_id
        self.client = NotionClient(auth=access_token)

    async def sync_item(self, item: SyncItem) -> SyncResult:
        if item.item_type != SyncItemType.TODO:
            return SyncResult(
                status=SyncStatus.SKIP PED,
                metadata={"reason": "This integration only syncs todos"}
            )

        return await self._sync_todo(item)

    async def _sync_todo(self, item: SyncItem) -> SyncResult:
        """Create a page in the todos database."""
        todo_data = item.data
        todo_text = todo_data.get("text", "")
        is_completed = todo_data.get("is_completed", False)
        notebook_uuid = todo_data.get("notebook_uuid", "")
        notebook_name = todo_data.get("notebook_name", "")
        page_number = todo_data.get("page_number")

        # Determine status based on completion
        status = "Done" if is_completed else "Not started"

        # Create page in todos database
        properties = {
            "Task": {"title": [{"text": {"content": todo_text[:2000]}}]},
            "Status": {"status": {"name": status}},
            "Notebook": {"rich_text": [{"text": {"content": notebook_name}}]},
            "Notebook UUID": {"rich_text": [{"text": {"content": notebook_uuid}}]},
            "Page": {"number": page_number} if page_number else {},
            "Synced At": {"date": {"start": datetime.utcnow().isoformat()}},
        }

        response = self.client.pages.create(
            parent={"database_id": self.database_id},
            properties=properties
        )

        return SyncResult(
            status=SyncStatus.SUCCESS,
            target_id=response["id"],
            metadata={"action": "todo_page_created", "status": status}
        )
```

#### 2. Update Integration Test Endpoint

```python
# app/api/integrations.py

# Update to handle both "notion" and "notion-todos"
if target_name == "notion":
    database_id = config_dict.get("database_id")
    target = NotionSyncTarget(access_token=access_token, database_id=database_id)

elif target_name == "notion-todos":
    database_id = config_dict.get("database_id")  # todos database
    use_status_property = config_dict.get("use_status_property", False)
    target = NotionTodosSyncTarget(
        access_token=access_token,
        database_id=database_id,
        use_status_property=use_status_property,  # True for existing dbs with Status
    )
```

#### 3. Update Sync Queue Routing

```python
# app/services/sync_queue.py

def queue_todo_sync(...):
    # Get ALL enabled integrations that support todos
    integrations = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == user_id,
            IntegrationConfig.is_enabled == True,
            IntegrationConfig.target_name.in_(['notion-todos', 'todoist', 'ticktick'])
        )
        .all()
    )

    # Queue for each todo integration
    for integration in integrations:
        queue_sync(
            db=db,
            user_id=user_id,
            item_type='todo',
            item_id=str(todo_id),
            content_hash=content_hash,
            target_name=integration.target_name,  # "notion-todos", etc.
            ...
        )
```

### Migration Path

For users who already have Notion configured:

1. Keep existing `notion` integration for notebooks
2. When they want to enable todo sync:
   - Click "Connect Notion Todos"
   - Reuse existing OAuth token
   - Select/create todos database
   - Creates new `notion-todos` integration config
3. Both integrations share the same access token but use different database IDs

## Conclusion

This architecture:
- ✅ Separates concerns (notebooks vs todos vs highlights)
- ✅ Allows mixing services (Notion for notebooks, Todoist for todos)
- ✅ Extensible for future integrations
- ✅ Clear user experience
- ✅ Minimal code changes (mostly additive)

Next steps:
1. Implement `NotionTodosSyncTarget`
2. Update API to distinguish `notion` vs `notion-todos`
3. Update frontend to show separate integrations
4. Test complete flow
