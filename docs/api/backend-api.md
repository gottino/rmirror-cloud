# rMirror Cloud API Reference

Complete API reference for the rMirror Cloud backend service.

**Base URL:** `http://your-server/v1`

**Authentication:** Most endpoints require Bearer token authentication. Include the token in the `Authorization` header:
```
Authorization: Bearer <your_token>
```

---

## Table of Contents

1. [Authentication](#authentication)
2. [User Management](#user-management)
3. [Notebooks](#notebooks)
4. [Processing & OCR](#processing--ocr)
5. [Todos](#todos)
6. [Integrations](#integrations)
7. [Sync](#sync)

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

---

## Processing & OCR

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
  "total_notebooks": 393,
  "synced_notebooks": 25,
  "pending_notebooks": 368,
  "total_syncs": 50,
  "successful_syncs": 48,
  "failed_syncs": 2
}
```

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
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `422` - Validation Error
- `500` - Internal Server Error

**Error Response Format:**
```json
{
  "detail": "Error message describing what went wrong"
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

---

## Rate Limiting

API endpoints are subject to rate limiting:
- Authentication endpoints: 5 requests per minute
- Data retrieval endpoints: 100 requests per minute
- Processing endpoints: 10 requests per minute

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1700000000
```

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
