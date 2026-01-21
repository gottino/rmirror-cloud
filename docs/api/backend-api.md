# rMirror Cloud API Reference

Complete API reference for the rMirror Cloud backend service.

**Last Updated:** January 2026

**Base URL:** `http://your-server/v1`

**Authentication:** Most endpoints require Bearer token authentication. Include the token in the `Authorization` header:
```
Authorization: Bearer <your_token>
```

---

## Table of Contents

1. [Authentication](#authentication)
2. [User Management](#user-management)
3. [Quota Management](#quota-management)
4. [Notebooks](#notebooks)
5. [Processing & OCR](#processing--ocr)
6. [Todos](#todos)
7. [Agent Management](#agent-management)
8. [Integrations](#integrations)
9. [Sync](#sync)

---

## Authentication

### Login

Get an access token for API authentication.

**Endpoint:** `POST /auth/login`

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "your-password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe",
    "is_active": true
  }
}
```

### Register

Create a new user account.

**Endpoint:** `POST /auth/register`

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "secure-password",
  "full_name": "John Doe"
}
```

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "is_active": true,
  "created_at": "2025-11-17T12:00:00Z"
}
```

---

## User Management

### Get Current User

Get information about the authenticated user.

**Endpoint:** `GET /users/me`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "subscription_tier": "free",
  "is_active": true,
  "created_at": "2025-11-17T12:00:00Z"
}
```

### Update User

Update user profile information.

**Endpoint:** `PATCH /users/me`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "full_name": "John Smith",
  "email": "newemail@example.com"
}
```

---

## Quota Management

### Get Quota Status

Get current quota status for the authenticated user.

**Endpoint:** `GET /v1/quota/status`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "quota_type": "ocr_pages",
  "used": 25,
  "limit": 30,
  "remaining": 5,
  "percentage_used": 83.33,
  "is_exhausted": false,
  "reset_at": "2026-02-01T00:00:00Z",
  "period_start": "2026-01-01T00:00:00Z"
}
```

**Response Fields:**
- `quota_type`: Type of quota (currently only "ocr_pages")
- `used`: Number of pages processed this period
- `limit`: Total quota limit for the period
- `remaining`: Pages remaining (limit - used)
- `percentage_used`: Percentage of quota consumed (0-100)
- `is_exhausted`: Boolean indicating if quota is fully consumed
- `reset_at`: Timestamp when quota resets (start of next month)
- `period_start`: Timestamp when current quota period began

**Subscription Tiers:**
- **Free**: 30 pages/month
- **Pro** (planned): Higher limits with Stripe integration
- **Enterprise** (planned): Custom limits

**Quota Behavior:**
When quota is exhausted:
1. File uploads are still accepted
2. PDFs are generated and stored
3. OCR processing is deferred
4. Pages are marked with `pending_quota` status
5. Integration syncs are blocked
6. Dashboard shows "OCR Pending" state
7. Retroactive processing occurs when quota resets (newest pages first)

---

## Notebooks

### List Notebooks

Get all notebooks for the authenticated user.

**Endpoint:** `GET /notebooks/`

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**
- `limit` (optional): Maximum number of results (default: 100, max: 500)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
[
  {
    "id": 1,
    "notebook_uuid": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
    "visible_name": "Meeting Notes",
    "parent_uuid": null,
    "last_modified": "2025-11-15T10:30:00Z",
    "created_at": "2025-11-01T08:00:00Z"
  }
]
```

### Get Notebook by UUID

Get a specific notebook by its reMarkable UUID.

**Endpoint:** `GET /notebooks/uuid/{notebook_uuid}`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "id": 1,
  "notebook_uuid": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "visible_name": "Meeting Notes",
  "parent_uuid": null,
  "last_modified": "2025-11-15T10:30:00Z",
  "page_count": 15,
  "pages_with_ocr": 12,
  "created_at": "2025-11-01T08:00:00Z"
}
```

### Get Notebook by ID

Get a specific notebook by its database ID.

**Endpoint:** `GET /notebooks/{notebook_id}`

**Headers:** `Authorization: Bearer <token>`

**Response:** Same as Get Notebook by UUID

### Get Notebook Pages

Get all pages for a specific notebook.

**Endpoint:** `GET /notebooks/{notebook_id}/pages`

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**
- `limit` (optional): Maximum number of results (default: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
[
  {
    "id": 1,
    "notebook_id": 1,
    "page_uuid": "9a8b7c6d-5e4f-3210-abcd-ef1234567890",
    "page_number": 1,
    "ocr_text": "Meeting notes from...",
    "processed_at": "2025-11-15T11:00:00Z",
    "created_at": "2025-11-01T08:00:00Z"
  }
]
```

### Get Notebook Content (Markdown)

Get the full notebook content in markdown format with OCR text.

**Endpoint:** `GET /notebooks/{notebook_id}/content`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "notebook_id": 1,
  "visible_name": "Meeting Notes",
  "markdown": "# Page 1\n\n- [ ] Invite People Leads to Meeting Notes call\n\n# Page 2\n\n..."
}
```

### Upload Content File for Initial Sync

Upload and parse a `.content` file to update the notebook_pages mapping table. This endpoint is used during Initial Sync to establish the correct page order for a notebook.

**Endpoint:** `POST /notebooks/{notebook_uuid}/content`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
- Form data with file field: `content_file` (the `.content` JSON file)

**Response:**
```json
{
  "success": true,
  "message": "Content file processed successfully",
  "notebook_uuid": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "pages_in_content": 15,
  "pages_mapped": 15
}
```

**What it does:**
1. Accepts a `.content` JSON file for a notebook
2. Parses the pages array (handles both old and new reMarkable formats)
3. Updates the `notebook_pages` mapping table with correct page order
4. Stores the `.content` JSON in the notebooks table

**Use cases:**
- Initial Sync: Bulk uploading all pages for a notebook
- Catch-up Sync: Syncing pages added while agent was offline
- Re-ordering pages after reMarkable changes

---

## Processing & OCR

### Process .rm File with OCR Deduplication

Process a reMarkable `.rm` file: convert to PDF, extract text via OCR, and save to database. This endpoint uses SHA-256 file hashing to avoid re-processing unchanged files.

**Endpoint:** `POST /v1/processing/rm-file`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
- Form data with file fields:
  - `rm_file`: The `.rm` file from reMarkable tablet (required)
  - `metadata_file`: Optional `.metadata` JSON file for notebook metadata

**Response (Success):**
```json
{
  "success": true,
  "extracted_text": "Your handwritten text here...",
  "page_count": 1,
  "metadata": {
    "visible_name": "My Notebook",
    "document_type": "DocumentType",
    "last_modified": "2025-12-26T12:00:00"
  },
  "notebook_id": 123,
  "page_id": 456,
  "status": "completed"
}
```

**Response (Quota Exhausted):**
```json
{
  "success": true,
  "extracted_text": "",
  "page_count": 1,
  "metadata": {
    "visible_name": "My Notebook",
    "document_type": "DocumentType",
    "last_modified": "2025-12-26T12:00:00"
  },
  "notebook_id": 123,
  "page_id": 456,
  "status": "pending_quota",
  "message": "Upload successful, OCR deferred due to quota limit"
}
```

**Behavior:**
- **New file**: Calculates hash, runs OCR (if quota available), stores hash and text
- **Unchanged file**: Compares hash, skips OCR, returns cached text (90% cost reduction)
- **Modified file**: Detects hash change, runs OCR (if quota available), updates hash and text
- **Failed OCR**: Retries OCR even if hash matches
- **Quota exhausted**: Accepts upload, generates PDF, defers OCR, sets status to `pending_quota`

**What it does:**
1. Accepts a `.rm` file (and optional `.metadata` file)
2. Checks quota status (does not block upload if exhausted)
3. Calculates SHA-256 hash and checks if file changed
4. Converts .rm → SVG → PDF
5. Sends PDF to Claude Vision for OCR (if quota available and file changed)
6. Consumes quota only after successful OCR
7. Creates/updates Notebook and Page records in database
8. Stores `.rm` file and PDF in storage
9. Returns extracted text with database IDs

**Performance benefits:**
- Avoids redundant OCR for unchanged pages
- 90-95% cost reduction for OCR API calls
- 85-90% faster sync operations

**Page Status Values:**
- `not_synced`: Page registered but content not uploaded
- `pending`: Content uploaded, OCR queued
- `completed`: OCR finished successfully
- `failed`: OCR processing failed
- `pending_quota`: Quota exhausted, OCR deferred until quota resets

### Update Notebook Metadata (Lightweight Sync)

Lightweight metadata-only sync for notebooks. Updates Notion properties without processing content. This is 50-100x faster than full content sync (~100ms vs ~5s).

**Endpoint:** `POST /v1/processing/metadata/update`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "notebook_uuid": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "visible_name": "Meeting Notes",
  "last_opened_at": "2026-01-15T10:30:00Z",
  "last_modified_at": "2026-01-15T10:30:00Z",
  "page_count": 15,
  "full_path": "Work/Projects/Meeting Notes"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Metadata updated successfully",
  "notebook_uuid": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "sync_type": "NOTEBOOK_METADATA"
}
```

**Response (Notebook Not Yet Synced):**
```json
{
  "success": true,
  "message": "Skipped: Notebook not yet synced to Notion",
  "notebook_uuid": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "sync_type": "SKIPPED"
}
```

**What it does:**
1. Accepts notebook metadata without content
2. Checks if notebook exists and has been synced to Notion
3. If not synced, returns SKIPPED (no error)
4. If synced, updates only Notion properties:
   - Title (visible_name)
   - Last Opened
   - Last Modified
   - Page Count
   - Full Path
5. Does not process pages or consume OCR quota
6. Returns immediately after property update

**Use Cases:**
- Periodic metadata refresh from agent (every 5 minutes)
- Update notebook properties after reMarkable changes
- Keep Notion properties in sync without triggering full OCR
- Lightweight sync for frequently accessed notebooks

**Performance:**
- ~100ms response time (vs ~5s for full sync)
- No OCR processing
- No quota consumption
- Higher rate limit (100/minute vs 10/minute for content sync)

### Trigger OCR Processing

Trigger OCR processing for a specific notebook.

**Endpoint:** `POST /processing/notebooks/{notebook_id}/ocr`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "success": true,
  "message": "OCR processing started for notebook 1",
  "notebook_id": 1
}
```

### Get Processing Status

Check the status of OCR processing for a notebook.

**Endpoint:** `GET /processing/notebooks/{notebook_id}/status`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "notebook_id": 1,
  "status": "completed",
  "total_pages": 15,
  "processed_pages": 15,
  "pages_with_ocr": 12,
  "last_processed": "2025-11-15T11:30:00Z"
}
```

---

## Todos

### List Todos

Get todos for the authenticated user with optional filters.

**Endpoint:** `GET /todos/`

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**
- `notebook_id` (optional): Filter by notebook ID
- `completed` (optional): Filter by completion status (true/false)
- `limit` (optional): Maximum number of results (default: 100, max: 500)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
[
  {
    "id": 1,
    "notebook_id": 341,
    "page_id": 4649,
    "page_number": 15,
    "page_uuid": "9a8b7c6d-5e4f-3210-abcd-ef1234567890",
    "title": "Review quarterly goals",
    "text": "Review quarterly goals",
    "completed": false,
    "confidence": 1.0,
    "source_file": "Meeting Notes",
    "created_at": "2025-11-17T20:00:00Z",
    "updated_at": "2025-11-17T20:00:00Z"
  }
]
```

### Get Todo by ID

Get a specific todo item.

**Endpoint:** `GET /todos/{todo_id}`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "id": 1,
  "notebook_id": 341,
  "page_id": 4649,
  "page_number": 15,
  "page_uuid": "9a8b7c6d-5e4f-3210-abcd-ef1234567890",
  "title": "Review quarterly goals",
  "text": "Review quarterly goals",
  "completed": false,
  "confidence": 1.0,
  "source_file": "Meeting Notes",
  "created_at": "2025-11-17T20:00:00Z",
  "updated_at": "2025-11-17T20:00:00Z"
}
```

### Update Todo

Update a todo item (mark as completed, edit text, etc.).

**Endpoint:** `PATCH /todos/{todo_id}`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "completed": true,
  "text": "Updated task description"
}
```

**Response:**
```json
{
  "id": 1,
  "notebook_id": 341,
  "text": "Updated task description",
  "completed": true,
  "updated_at": "2025-11-17T21:00:00Z"
}
```

### Delete Todo

Delete a todo item.

**Endpoint:** `DELETE /todos/{todo_id}`

**Headers:** `Authorization: Bearer <token>`

**Response:** `204 No Content`

### Extract Todos from Notebooks

Trigger todo extraction from notebook OCR text. This scans for checkbox patterns and creates todo items.

**Endpoint:** `POST /todos/extract`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "notebook_ids": [1, 2, 3],
  "force_reprocess": false
}
```

**Parameters:**
- `notebook_ids` (optional): List of specific notebook IDs to process. If omitted, processes all notebooks.
- `force_reprocess` (optional): If true, reprocess notebooks even if todos already exist (default: false)

**Response:**
```json
{
  "success": true,
  "message": "Todo extraction started for 3 notebook(s)",
  "notebooks_processed": 0,
  "todos_extracted": 0
}
```

**Note:** Extraction runs in the background. Use the stats endpoint to check progress.

### Get Todo Statistics

Get statistics about todos for the current user.

**Endpoint:** `GET /todos/stats/summary`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "total_todos": 15,
  "completed_todos": 8,
  "pending_todos": 7,
  "notebooks_with_todos": 3
}
```

---

## Agent Management

### Get Agent Status

Get current agent connection status for the authenticated user.

**Endpoint:** `GET /agents/status`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "has_agent_connected": true,
  "first_connected_at": "2025-12-01T10:30:00Z",
  "onboarding_state": "agent_connected"
}
```

**Onboarding States:**
- `signed_up`: User created account
- `agent_downloaded`: User downloaded the macOS agent
- `agent_connected`: Agent successfully connected to backend
- `complete`: Onboarding completed

### Mark Agent as Downloaded

Track when a user downloads the macOS agent. Updates onboarding state and tracks download timestamp.

**Endpoint:** `POST /agents/agent-downloaded`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "message": "Agent download tracked successfully"
}
```

**What it does:**
- Records agent download timestamp
- Updates onboarding state from `signed_up` to `agent_downloaded`
- Used by download page to track onboarding progress

### Exchange Clerk Token for Agent Token

Exchange a short-lived Clerk session token for a long-lived agent token. Used by the macOS agent to authenticate API requests.

**Endpoint:** `POST /v1/auth/agent-token`

**Headers:** `Authorization: Bearer <clerk_session_token>`

**Request Body:** None (token provided in Authorization header)

**Response:**
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 2592000,
  "user_id": "user_abc123"
}
```

**Response Fields:**
- `access_token`: JWT token valid for 30 days
- `token_type`: Always "bearer"
- `expires_in`: Token lifetime in seconds (2592000 = 30 days)
- `user_id`: Clerk user ID associated with the token

**Security:**
- Only accepts tokens from localhost callbacks (`http://localhost:*`)
- Validates Clerk session token with Clerk API
- Generates JWT signed with backend secret key
- Token stored securely in system keychain by agent

**What it does:**
1. Accepts Clerk session token from OAuth callback
2. Validates token with Clerk API
3. Generates 30-day JWT for agent use
4. Returns long-lived token for background sync operations

**Use Cases:**
- Initial agent authentication after Clerk OAuth flow
- Token renewal when agent token expires
- Switching between user accounts in agent

**Error Responses:**
- `401 Unauthorized`: Invalid or expired Clerk token
- `403 Forbidden`: Token not from localhost callback

### Trigger Agent (Future)

*Note: These endpoints are planned for future releases when agent triggering is implemented.*

**Endpoint:** `POST /agents/{target_name}/trigger` (Planned)

Trigger a specific agent operation (e.g., force sync).

**Endpoint:** `GET /agents/{target_name}/test` (Planned)

Test agent connectivity and configuration.

---

## Integrations

### List Integrations

Get all configured integrations for the user.

**Endpoint:** `GET /integrations/`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
[
  {
    "id": 1,
    "user_id": 1,
    "integration_type": "notion",
    "config": {
      "workspace_name": "My Workspace",
      "database_id": "abc123..."
    },
    "is_active": true,
    "created_at": "2025-11-17T10:00:00Z"
  }
]
```

### Configure Notion Integration

Set up or update Notion integration.

**Endpoint:** `POST /integrations/notion`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "access_token": "secret_...",
  "workspace_id": "workspace-123",
  "workspace_name": "My Workspace"
}
```

**Response:**
```json
{
  "id": 1,
  "integration_type": "notion",
  "is_active": true,
  "created_at": "2025-11-17T10:00:00Z"
}
```

### Test Notion Connection

Test if the Notion integration is working.

**Endpoint:** `GET /integrations/notion/test`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "success": true,
  "message": "Connection successful",
  "workspace": "My Workspace"
}
```

---

## Sync

### Trigger Initial Sync

Trigger initial sync for a user. Creates notebook pages in Notion first, then queues pages for processing. This two-phase approach prevents duplicate page creation.

**Endpoint:** `POST /v1/sync/initial`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "page_limit": 30,
  "force": false
}
```

**Parameters:**
- `page_limit` (optional): Maximum number of pages to sync (default: 30, matches free tier quota)
- `force` (optional): Force sync even if user has already done initial sync (default: false)

**Response:**
```json
{
  "success": true,
  "message": "Initial sync started",
  "notebooks_queued": 25,
  "pages_to_process": 350,
  "page_limit_applied": 30
}
```

**What it does:**
1. Checks if user has Notion integration configured
2. Checks if user has already completed initial sync (unless `force=true`)
3. Gets all notebooks from database (sorted by last_modified, newest first)
4. **Phase 1**: Creates empty notebook pages in Notion for all notebooks
   - Prevents duplicate page creation
   - Establishes Notion page IDs upfront
   - Stores mapping in `sync_records` table
5. **Phase 2**: Queues individual pages for OCR processing
   - Respects `page_limit` parameter
   - Processes newest pages first
   - Pages beyond limit are registered but not processed (status: `not_synced`)
6. Marks user's initial sync as complete
7. Returns queue statistics

**Two-Phase Sync Prevents Duplicates:**
- Old approach: Queue notebooks → worker creates Notion pages → race condition → duplicates
- New approach: Create Notion pages first → queue pages → worker updates existing pages → no duplicates

**Use Cases:**
- First-time setup after installing agent and configuring Notion
- Re-syncing after clearing Notion workspace
- Catch-up sync after being offline for extended period

**Error Responses:**
- `400 Bad Request`: Notion integration not configured
- `409 Conflict`: Initial sync already completed (use `force=true` to override)
- `402 Payment Required`: Quota exhausted (accepts request but defers OCR)

### Trigger Notebook Sync

Sync a notebook to connected integrations (e.g., Notion).

**Endpoint:** `POST /sync/notebook/{notebook_id}`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "target": "notion",
  "force": false
}
```

**Parameters:**
- `target` (optional): Specific integration to sync to. If omitted, syncs to all active integrations.
- `force` (optional): Force sync even if content hasn't changed (default: false)

**Response:**
```json
{
  "success": true,
  "message": "Sync started for notebook 1",
  "notebook_id": 1,
  "targets": ["notion"]
}
```

### Get Sync Status

Get sync status for a notebook and integration.

**Endpoint:** `GET /sync/status/{target}`

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**
- `notebook_id` (optional): Filter by specific notebook

**Response:**
```json
{
  "target": "notion",
  "total_syncs": 15,
  "successful_syncs": 14,
  "failed_syncs": 1,
  "last_sync": "2025-11-17T15:30:00Z"
}
```

### Get Sync Statistics

Get overall sync statistics for the user.

**Endpoint:** `GET /sync/stats`

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**
- `target_name` (optional): Filter by integration type (e.g., "notion")

**Response:**
```json
{
  "target_name": "notion",
  "total_records": 50,
  "status_counts": {
    "synced": 48,
    "pending": 2,
    "failed": 0
  },
  "target_counts": {
    "notion": 50
  },
  "type_counts": {
    "notebook": 45,
    "todo": 5
  }
}
```

### Get Sync Summary

Get a summary of sync statistics across all integrations.

**Endpoint:** `GET /sync/stats/summary`

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "total_notebooks": 393,
  "synced_notebooks": 25,
  "pending_notebooks": 368,
  "total_syncs": 50,
  "successful_syncs": 48,
  "failed_syncs": 2,
  "last_sync_at": "2025-12-26T15:30:00Z"
}
```

### Update Sync Progress (Agent)

Update sync progress from the macOS agent. This endpoint is called by the agent to report sync progress during bulk operations.

**Endpoint:** `POST /sync/progress`

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "operation": "initial_sync",
  "notebooks_total": 100,
  "notebooks_completed": 25,
  "pages_uploaded": 350,
  "current_notebook": "Meeting Notes"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Progress updated successfully"
}
```

**What it does:**
- Receives progress updates from agent during long-running operations
- Can be polled by frontend to show progress UI
- Used during Initial Sync to show real-time progress

---

## Supported Todo Patterns

The todo extraction feature recognizes the following checkbox patterns in OCR text:

**Markdown-style:**
- `- [ ]` - Uncompleted task
- `- [x]` - Completed task
- `- [X]` - Completed task
- `- [✓]` - Completed task
- `- [☑]` - Completed task

**Unicode symbols:**
- `☐` - Uncompleted task
- `☑` - Completed task
- `✓` - Completed task
- `□` - Uncompleted task

**Note:** Lines starting with `↳` are treated as sub-points, not tasks.

---

## Error Responses

All endpoints return appropriate HTTP status codes:

- `200` - Success
- `201` - Created
- `204` - No Content (successful deletion)
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized (missing or invalid token)
- `402` - Payment Required (quota exceeded)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `409` - Conflict (resource already exists or operation not allowed)
- `422` - Validation Error
- `429` - Too Many Requests (rate limit exceeded)
- `500` - Internal Server Error

**Error Response Format:**
```json
{
  "detail": "Error message describing what went wrong"
}
```

**Quota Exceeded Error (HTTP 402):**
```json
{
  "detail": "OCR quota exceeded",
  "quota": {
    "used": 30,
    "limit": 30,
    "remaining": 0,
    "percentage_used": 100.0,
    "is_exhausted": true,
    "reset_at": "2026-02-01T00:00:00Z"
  }
}
```

**Validation Error Format:**
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

**Rate Limit Error (HTTP 429):**
```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds."
}
```

---

## Rate Limiting

API endpoints are subject to rate limiting to ensure fair usage and system stability.

**Rate Limits by Endpoint Type:**

| Endpoint Type | Rate Limit | Scope |
|--------------|------------|-------|
| Authenticated requests (default) | 300/minute | Per user |
| Unauthenticated requests | 30/minute | Per IP address |
| Authentication endpoints (`/auth/*`) | 10/minute | Per IP address |
| Processing endpoints (`/processing/rm-file`) | 10/minute | Per user |
| Metadata sync (`/processing/metadata/update`) | 100/minute | Per user |
| OCR processing (`/processing/notebooks/*/ocr`) | 10/minute | Per user |

**Rate Limit Headers:**

All responses include rate limit information in headers:

```
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 295
X-RateLimit-Reset: 1737475200
```

- `X-RateLimit-Limit`: Maximum requests allowed in the time window
- `X-RateLimit-Remaining`: Requests remaining in current window
- `X-RateLimit-Reset`: Unix timestamp when the rate limit resets

**Rate Limit Exceeded Response:**

When rate limit is exceeded, the API returns HTTP 429:

```json
{
  "detail": "Rate limit exceeded. Try again in 45 seconds."
}
```

**Best Practices:**
- Implement exponential backoff when receiving 429 responses
- Monitor `X-RateLimit-Remaining` header to avoid hitting limits
- Use metadata sync endpoint for frequent updates (higher limit)
- Batch operations when possible to reduce request count

---

## Example Usage

### Python Example

```python
import httpx

BASE_URL = "http://your-server/v1"

# Login
response = httpx.post(
    f"{BASE_URL}/auth/login",
    json={"email": "user@example.com", "password": "password"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get notebooks
notebooks = httpx.get(f"{BASE_URL}/notebooks/", headers=headers).json()

# Extract todos from first notebook
httpx.post(
    f"{BASE_URL}/todos/extract",
    headers=headers,
    json={"notebook_ids": [notebooks[0]["id"]]}
)

# List todos
todos = httpx.get(f"{BASE_URL}/todos/", headers=headers).json()
```

### cURL Example

```bash
# Login
TOKEN=$(curl -X POST http://your-server/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}' \
  | jq -r '.access_token')

# List notebooks
curl http://your-server/v1/notebooks/ \
  -H "Authorization: Bearer $TOKEN"

# Extract todos
curl -X POST http://your-server/v1/todos/extract \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notebook_ids":[1],"force_reprocess":false}'

# List todos
curl http://your-server/v1/todos/ \
  -H "Authorization: Bearer $TOKEN"
```

---

## Interactive API Documentation

FastAPI automatically generates interactive API documentation:

- **Swagger UI:** `http://your-server/docs`
- **ReDoc:** `http://your-server/redoc`

These provide a complete, interactive interface to explore and test all API endpoints.

---

## Support

For issues, questions, or feature requests, please visit:
- GitHub Issues: https://github.com/gottino/rmirror-cloud/issues
- Email: support@rmirror.cloud
