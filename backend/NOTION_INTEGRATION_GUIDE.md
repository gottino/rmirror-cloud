# Notion Integration Implementation Guide

## Overview

This document provides a complete guide for implementing the Notion integration with OAuth and database creation support for rMirror Cloud.

## What Has Been Implemented (Backend)

### 1. Environment Configuration ✅
**File**: `backend/.env`

Added Notion OAuth credentials:
```env
NOTION_CLIENT_ID=your_client_id_here
NOTION_CLIENT_SECRET=your_client_secret_here
NOTION_REDIRECT_URI=http://localhost:3000/integrations/notion/callback
```

### 2. Notion OAuth Service ✅
**File**: `backend/app/services/notion_oauth.py`

Complete OAuth service with:
- `get_authorization_url(state)` - Generate OAuth URL
- `exchange_code_for_token(code)` - Exchange auth code for access token
- `list_databases(access_token)` - List all accessible databases
- `list_pages(access_token)` - List pages for parent selection
- `create_rmirror_database(access_token, parent_page_id, database_title)` - Create configured database
- `validate_database(access_token, database_id)` - Validate database access
- `get_database_info(access_token, database_id)` - Get database details

### 3. Notion OAuth API Endpoints ✅
**File**: `backend/app/api/notion_oauth.py`

Complete REST API:
- `GET /integrations/notion/oauth/authorize` - Get authorization URL
- `POST /integrations/notion/oauth/callback` - Handle OAuth callback
- `GET /integrations/notion/databases` - List databases
- `GET /integrations/notion/pages` - List pages
- `POST /integrations/notion/databases/create` - Create new database
- `POST /integrations/notion/databases/{database_id}/select` - Select existing database

### 4. Router Registration ✅
**File**: `backend/app/api/__init__.py`

Registered Notion OAuth router with the main API.

## What Needs to Be Implemented

### Backend Tasks

#### 1. Update NotionSyncTarget for OAuth ⏳
**File**: `backend/app/integrations/notion_sync.py`

**Current State**: Uses manual API token + database_id
**Needed**: Support OAuth access tokens from encrypted config

**Changes Required**:
```python
def __init__(self, access_token: str, database_id: str, verify_ssl: bool = False):
    """Updated to use OAuth access_token instead of api_token."""
    super().__init__("notion")
    self.access_token = access_token  # Changed from api_token
    self.database_id = database_id

    if verify_ssl:
        self.client = NotionClient(auth=access_token)
    else:
        http_client = httpx.Client(verify=False)
        self.client = NotionClient(auth=access_token, client=http_client)
```

Update integration test endpoint in `backend/app/api/integrations.py`:
```python
# Line 316-326 currently uses api_token
# Should use access_token from OAuth flow
config_dict = config.get_config()  # Now uses encrypted storage
access_token = config_dict.get("access_token")
database_id = config_dict.get("database_id")

target = NotionSyncTarget(access_token=access_token, database_id=database_id)
```

#### 2. Implement Page-Level Sync ⏳
**File**: `backend/app/integrations/notion_sync.py`
**Method**: `_sync_page_text()`

**Current**: Returns SKIPPED
**Goal**: Update existing Notion pages with new content blocks

**Implementation**:
```python
async def _sync_page_text(self, item: SyncItem) -> SyncResult:
    """Sync individual page text as blocks to existing Notion page."""
    try:
        page_data = item.data
        page_text = page_data.get("text", "")
        page_number = page_data.get("page_number")
        notebook_uuid = page_data.get("notebook_uuid")

        # Find the parent Notion page for this notebook
        parent_page_id = await self.find_existing_page(notebook_uuid)

        if not parent_page_id:
            return SyncResult(
                status=SyncStatus.FAILED,
                error_message=f"Parent notebook page not found for {notebook_uuid}"
            )

        # Get existing children blocks for this page number
        # Update or append new content
        # Convert text to Notion blocks
        blocks = self._text_to_blocks(page_text)

        # Append blocks to the page
        self.client.blocks.children.append(
            block_id=parent_page_id,
            children=blocks
        )

        return SyncResult(
            status=SyncStatus.SUCCESS,
            target_id=parent_page_id,
            metadata={
                "action": "page_content_updated",
                "page_number": page_number,
                "blocks_added": len(blocks)
            }
        )

    except Exception as e:
        return SyncResult(status=SyncStatus.FAILED, error_message=str(e))
```

#### 3. Implement Todo Sync ⏳
**File**: `backend/app/integrations/notion_sync.py`
**Method**: `_sync_todo()`

**Current**: Returns SKIPPED
**Goal**: Create Notion checkbox (to_do) blocks

**Implementation**:
```python
async def _sync_todo(self, item: SyncItem) -> SyncResult:
    """Sync todo as a checkbox block in Notion."""
    try:
        todo_data = item.data
        todo_text = todo_data.get("text", "")
        is_completed = todo_data.get("is_completed", False)
        notebook_uuid = todo_data.get("notebook_uuid")

        # Find parent Notion page
        parent_page_id = await self.find_existing_page(notebook_uuid)

        if not parent_page_id:
            return SyncResult(
                status=SyncStatus.FAILED,
                error_message=f"Parent notebook not found for {notebook_uuid}"
            )

        # Create to_do block
        todo_block = {
            "object": "block",
            "type": "to_do",
            "to_do": {
                "rich_text": [{"type": "text", "text": {"content": todo_text}}],
                "checked": is_completed,
            }
        }

        # Append to page
        response = self.client.blocks.children.append(
            block_id=parent_page_id,
            children=[todo_block]
        )

        block_id = response["results"][0]["id"]

        return SyncResult(
            status=SyncStatus.SUCCESS,
            target_id=block_id,
            metadata={
                "action": "todo_created",
                "parent_page_id": parent_page_id,
                "checked": is_completed
            }
        )

    except Exception as e:
        return SyncResult(status=SyncStatus.FAILED, error_message=str(e))
```

### Frontend Tasks

#### 4. Create Integration Settings Page ⏳
**Location**: `dashboard/src/app/settings/integrations/page.tsx`

**Features Needed**:
- List all configured integrations
- Button to "Connect to Notion"
- Show connection status (connected/disconnected)
- Enable/disable toggle
- Delete integration button

**API Calls**:
```typescript
// List integrations
GET /v1/integrations/

// Start Notion OAuth
GET /v1/integrations/notion/oauth/authorize

// Delete integration
DELETE /v1/integrations/{target_name}
```

#### 5. OAuth Callback Handler ⏳
**Location**: `dashboard/src/app/integrations/notion/callback/page.tsx`

**Purpose**: Handle OAuth redirect from Notion

**Implementation**:
```typescript
"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

export default function NotionOAuthCallback() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code || !state) {
      setStatus("error");
      return;
    }

    // Call backend to exchange code for token
    fetch("/v1/integrations/notion/oauth/callback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, state }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          setStatus("success");
          // Redirect to database selection
          window.location.href = "/settings/integrations/notion/setup";
        } else {
          setStatus("error");
        }
      })
      .catch(() => setStatus("error"));
  }, [searchParams]);

  return (
    <div>
      {status === "loading" && <div>Connecting to Notion...</div>}
      {status === "success" && <div>Connected! Redirecting...</div>}
      {status === "error" && <div>Connection failed. Please try again.</div>}
    </div>
  );
}
```

#### 6. Database Selection/Creation UI ⏳
**Location**: `dashboard/src/app/settings/integrations/notion/setup/page.tsx`

**Features**:
- List existing databases (GET /v1/integrations/notion/databases)
- Radio buttons to select a database
- "Create New Database" option
  - Input for database title
  - Optional parent page selection
  - Submit to POST /v1/integrations/notion/databases/create
- "Select Database" button to POST /v1/integrations/notion/databases/{id}/select

#### 7. Sync Status Monitoring ⏳
**Location**: `dashboard/src/components/SyncStatus.tsx`

**Features**:
- Real-time sync status badge
- Last synced timestamp
- Sync progress indicator
- Manual sync trigger button
- Error display

**API Calls**:
```typescript
// Get sync stats
GET /v1/sync/stats?target_name=notion

// Trigger manual sync
POST /v1/sync/trigger
{
  "target_name": "notion",
  "notebook_uuids": ["uuid1", "uuid2"]  // optional
}

// Get sync status
GET /v1/sync/status/notion
```

## Setup Instructions

### 1. Create Notion Integration

1. Go to https://www.notion.so/my-integrations
2. Click "+ New integration"
3. Fill in details:
   - Name: "rMirror Cloud"
   - Logo: (optional)
   - Associated workspace: Select your workspace
4. Under "Capabilities", enable:
   - Read content
   - Update content
   - Insert content
5. Under "Integration type", select:
   - Public integration
6. Set redirect URIs:
   - Development: `http://localhost:3000/integrations/notion/callback`
   - Production: `https://yourdomain.com/integrations/notion/callback`
7. Copy the OAuth credentials:
   - Client ID → `NOTION_CLIENT_ID`
   - Client Secret → `NOTION_CLIENT_SECRET`

### 2. Update Environment Variables

**Backend** (`backend/.env`):
```env
NOTION_CLIENT_ID=your_actual_client_id
NOTION_CLIENT_SECRET=your_actual_client_secret
NOTION_REDIRECT_URI=http://localhost:3000/integrations/notion/callback
```

**Frontend** (`dashboard/.env.local` - if needed):
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Deploy to Production

Add GitHub Secrets for deployment:
```bash
gh secret set NOTION_CLIENT_ID --body "your_client_id"
gh secret set NOTION_CLIENT_SECRET --body "your_client_secret"
```

Update `.github/workflows/deploy.yml`:
```yaml
env:
  NOTION_CLIENT_ID: ${{ secrets.NOTION_CLIENT_ID }}
  NOTION_CLIENT_SECRET: ${{ secrets.NOTION_CLIENT_SECRET }}

run: |
  update_env backend/.env NOTION_CLIENT_ID \"$NOTION_CLIENT_ID\" && \
  update_env backend/.env NOTION_CLIENT_SECRET \"$NOTION_CLIENT_SECRET\" && \
```

## User Flow

### First-Time Setup

1. **User navigates to Settings → Integrations**
2. **Clicks "Connect to Notion"**
   - Frontend calls `GET /v1/integrations/notion/oauth/authorize`
   - Redirects to Notion OAuth page
3. **User authorizes in Notion**
   - Notion redirects to callback URL with code
4. **Frontend receives callback**
   - Calls `POST /v1/integrations/notion/oauth/callback`
   - Backend stores encrypted access token
5. **User selects/creates database**
   - Option A: Select existing database
     - Lists via `GET /v1/integrations/notion/databases`
     - Selects via `POST /v1/integrations/notion/databases/{id}/select`
   - Option B: Create new database
     - Optionally list pages via `GET /v1/integrations/notion/pages`
     - Creates via `POST /v1/integrations/notion/databases/create`
6. **Integration enabled**
   - Ready to sync notebooks

### Syncing

1. **Manual Trigger**
   - User clicks "Sync Now" button
   - Calls `POST /v1/sync/trigger` with target_name="notion"
2. **Automatic Sync** (future)
   - Background worker processes sync_queue
   - Syncs on OCR completion

## Testing

### Test OAuth Flow
```bash
# 1. Get authorization URL
curl http://localhost:8000/v1/integrations/notion/oauth/authorize \
  -H "Authorization: Bearer YOUR_TOKEN"

# 2. Visit URL in browser, authorize

# 3. Handle callback (simulated)
curl -X POST http://localhost:8000/v1/integrations/notion/oauth/callback \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code": "OAUTH_CODE", "state": "STATE_FROM_STEP_1"}'
```

### Test Database Operations
```bash
# List databases
curl http://localhost:8000/v1/integrations/notion/databases \
  -H "Authorization: Bearer YOUR_TOKEN"

# Create database
curl -X POST http://localhost:8000/v1/integrations/notion/databases/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"database_title": "rMirror Notebooks", "parent_page_id": null}'

# Select database
curl -X POST http://localhost:8000/v1/integrations/notion/databases/DATABASE_ID/select \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Architecture Decisions

### Why OAuth Instead of Internal Integrations?

**Chosen**: Public OAuth Integration
**Alternative**: Internal Integration with API token

**Reasons**:
1. **User Experience**: One-click authorization vs. manual token copying
2. **Security**: Tokens stored encrypted, user can revoke access
3. **Permissions**: OAuth scopes clearly defined
4. **Scalability**: Works for multi-user SaaS
5. **Best Practice**: Industry standard for integrations

### Why Let Users Create Databases?

**Chosen**: Database creation wizard
**Alternative**: Require pre-existing database

**Reasons**:
1. **Onboarding**: Simplified setup - no manual database creation
2. **Schema Guarantee**: Database has correct properties
3. **Flexibility**: Users can organize in workspace or specific page
4. **Professional**: Matches how other integrations work (Zapier, Make, etc.)

## Next Steps

1. ✅ Backend OAuth service and endpoints (DONE)
2. ⏳ Update NotionSyncTarget for OAuth
3. ⏳ Implement page-level and todo sync
4. ⏳ Build frontend integration UI
5. ⏳ End-to-end testing
6. ⏳ Production deployment

## API Reference

### Complete Endpoint List

```
# OAuth Flow
GET  /v1/integrations/notion/oauth/authorize          # Get auth URL
POST /v1/integrations/notion/oauth/callback           # Handle callback

# Database Management
GET  /v1/integrations/notion/databases                # List databases
GET  /v1/integrations/notion/pages                    # List pages
POST /v1/integrations/notion/databases/create         # Create database
POST /v1/integrations/notion/databases/{id}/select    # Select database

# Integration Management (existing)
POST   /v1/integrations/                              # Create integration
GET    /v1/integrations/                              # List integrations
GET    /v1/integrations/{target_name}                 # Get integration
PUT    /v1/integrations/{target_name}                 # Update integration
DELETE /v1/integrations/{target_name}                 # Delete integration
POST   /v1/integrations/{target_name}/test            # Test connection

# Sync Operations (existing)
POST /v1/sync/trigger                                 # Trigger sync
GET  /v1/sync/stats                                   # Get stats
GET  /v1/sync/status/{target_name}                    # Get status
```

## Security Considerations

1. **State Parameter**: CSRF protection in OAuth flow
   - TODO: Store state in Redis/session cache
   - Validate on callback

2. **Token Encryption**: All tokens encrypted with user-specific keys
   - Uses Fernet symmetric encryption
   - User-derived keys from master key + user_id

3. **HTTPS Only**: Production must use HTTPS
   - Update redirect URI for production
   - No sensitive data over HTTP

4. **Permission Scopes**: Request minimal necessary permissions
   - Only pages:write, databases:read/write, blocks:write

5. **Token Refresh**: Notion OAuth tokens don't expire
   - But implement refresh if Notion changes this
   - Handle token invalidation gracefully
