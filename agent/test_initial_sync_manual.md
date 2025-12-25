# Testing Initial Sync

The initial sync feature allows you to upload all notebooks when the agent first starts or needs to catch up after being offline.

## How to use:

1. **Start the agent**:
   ```bash
   poetry run python -m app.main --foreground
   ```

2. **Access the web UI**:
   Open http://localhost:5555 in your browser

3. **Authenticate**:
   - Click "Sign in with Clerk" or use password auth
   - The agent will authenticate with the backend

4. **Trigger initial sync via API**:
   ```bash
   curl -X POST http://localhost:5555/api/sync/initial
   ```

## What happens:

1. The agent scans all `.metadata` files in the reMarkable folder
2. Filters notebooks based on your selection (or all if sync_all_notebooks=true)
3. For each notebook:
   - Uploads all `.rm` page files
   - Uploads the `.content` file to establish page ordering
4. Returns statistics:
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

## Use cases:

- **First-time setup**: Upload all notebooks when setting up a new machine
- **After being offline**: Catch up on changes made while the agent wasn't running
- **Selective sync changes**: Re-sync after changing which notebooks to sync

## Example output:

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
   ...

======================================================================
  ✅ Initial Sync Complete
     Notebooks: 10
     Pages: 250
======================================================================
```
