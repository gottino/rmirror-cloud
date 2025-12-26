# Initial Sync Feature

## Overview

The Initial Sync feature allows users to upload all selected notebooks to the rMirror Cloud backend. This is useful for first-time setup, catching up after being offline, or re-syncing after changing notebook selections.

## How It Works

### Backend (Python)

**File: `app/sync/initial_sync.py`**

The `InitialSync` class:
1. Scans the reMarkable folder for notebooks using `MetadataScanner`
2. Filters by selected notebook UUIDs (respects configuration)
3. For each notebook:
   - Uploads all `.rm` page files
   - Uploads the `.content` file to establish page ordering
4. Returns statistics: notebooks synced, pages uploaded, failures

**File: `app/web/routes.py`**

The `/api/sync/initial` endpoint:
- POST endpoint that triggers initial sync
- Requires authentication
- Respects `sync_all_notebooks` and `selected_notebooks` configuration
- Returns JSON with success status and statistics

### Frontend (HTML/JavaScript)

**File: `app/web/templates/index.html`**

The UI includes:
- **Initial Sync Button**: Prominent button in the Actions card
- **Loading State**: Shows spinning animation while syncing
- **Success Message**: Displays statistics after completion
- **Help Text**: Explains when to use initial sync

```javascript
async function triggerInitialSync() {
  // 1. Disable button and show loading state
  // 2. POST to /api/sync/initial
  // 3. Display success message with stats
  // 4. Refresh status
}
```

## Usage

### Via Web UI (Recommended)

1. Open the agent web interface at `http://localhost:5555`
2. Sign in with your rMirror account
3. Select which notebooks to sync (or "Sync all notebooks")
4. Click the **"Initial Sync"** button
5. Wait for completion message

### Via API

```bash
curl -X POST http://localhost:5555/api/sync/initial
```

Response:
```json
{
  "success": true,
  "message": "Initial sync complete",
  "stats": {
    "notebooks": 10,
    "pages": 250,
    "failed": 0
  }
}
```

## Configuration

Initial sync respects the notebook selection configuration:

**Sync All Notebooks:**
```python
config.sync.sync_all_notebooks = True
# Syncs ALL notebooks
```

**Selective Sync:**
```python
config.sync.sync_all_notebooks = False
config.sync.selected_notebooks = ["uuid1", "uuid2", ...]
# Only syncs selected notebooks
```

## Use Cases

### 1. First-Time Setup
When setting up the agent for the first time:
- Select which notebooks to sync
- Click "Initial Sync" to upload everything

### 2. After Being Offline
If the agent hasn't been running for a while:
- New pages may have been added to notebooks
- Click "Initial Sync" to catch up

### 3. After Changing Selection
If you change which notebooks are selected:
- Previously unsynced notebooks need to be uploaded
- Click "Initial Sync" to upload newly selected notebooks

## Console Output

```
======================================================================
  📚 Initial Sync - Uploading Notebooks
======================================================================

Found 10 notebook(s) to sync

[1/10] Project Notes
   UUID: abc123...
   Pages: 25
   📤 Uploading 25 page(s)...
   📋 Uploading .content file...
   ✓ Mapped 25 pages
   ✓ Uploaded 25 page(s)

[2/10] Meeting Notes
   UUID: def456...
   Pages: 15
   📤 Uploading 15 page(s)...
   📋 Uploading .content file...
   ✓ Mapped 15 pages
   ✓ Uploaded 15 page(s)

...

======================================================================
  ✅ Initial Sync Complete
     Notebooks: 10
     Pages: 250
======================================================================
```

## Technical Details

### File Upload Order

For each notebook:
1. **Pages first** (`.rm` files) - Creates page records in database
2. **Content file second** (`.content` file) - Maps pages to correct order

This ensures the backend has the complete notebook structure.

### Error Handling

- If a notebook directory doesn't exist, it's skipped
- If a page upload fails, the error is logged and sync continues
- If the `.content` file upload fails (e.g., notebook doesn't exist in backend yet), it's logged but not considered a failure
- Final statistics include failure count

### Performance

- Uploads are sequential per notebook
- Each notebook is processed one at a time
- Average time: ~2-5 seconds per notebook (depends on number of pages)

## Future Enhancements (Backlog)

1. **Smart Sync**: Compare backend state vs local state, only upload missing/changed files
2. **Progress Tracking**: Real-time progress updates via WebSocket
3. **Auto-Detection**: Automatically trigger initial sync on first run
4. **Parallel Uploads**: Upload multiple notebooks concurrently
5. **Resume Support**: Resume interrupted syncs
