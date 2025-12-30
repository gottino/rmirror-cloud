# Unified Multi-Service Sync Architecture

## Executive Summary

This document outlines the architectural design for a comprehensive, multi-service sync system for rmirror-cloud. The architecture is inspired by the proven remarkable-integration system while being adapted for the cloud-based, multi-user environment.

**Primary Focus**: Complete Notion integration first, then expand to other services
**Sync Model**: Real-time push-based (reMarkable → Agent → rmirror-cloud → Service)
**Master**: rmirror-cloud is the single source of truth (no conflict resolution needed)

**Status**: ✅ Foundation exists (sync tables, Notion integration) | 🚧 Needs enhancement and expansion

---

## 1. Current State Assessment

### What We Have ✅

**Database Tables:**
- `sync_records` - Main sync tracking with content-hash deduplication
- `page_sync_records` - Granular page-level sync tracking
- `integration_configs` - User integration credentials and settings

**Core Infrastructure:**
- `SyncTarget` abstract base class for extensible integrations
- `UnifiedSyncManager` for orchestrating multi-target sync
- `ContentFingerprint` service for deterministic content hashing
- `NotionSyncTarget` - Partial Notion integration (notebooks only)
- Sync API endpoints (`/sync/trigger`, `/sync/stats`, `/sync/status/{target}`)
- Integration management API (`/integrations/*`)

**Content Models:**
- `Notebook`, `Page`, `Highlight`, `Todo` with proper relationships
- OCR tracking with status states
- File hash tracking for change detection

### What's Missing 🚧

**Integrations:**
- ❌ **Complete Notion integration** (todos, highlights, page-level sync) - **PRIORITY**
- ❌ Readwise sync implementation - **LATER**
- ❌ Other services (Obsidian, Roam, Apple Notes, etc.) - **FUTURE**

**Sync Features:**
- ❌ Page-level sync (currently returns SKIPPED)
- ❌ Todo sync to Notion
- ❌ Highlight sync to Notion
- ❌ Real-time OCR-triggered sync
- ❌ Catch-up sync for reconnection scenarios
- ❌ Rate limiting and throttling
- ❌ Dry-run/preview mode
- ❌ Frontend integration configuration UI
- ❌ Frontend todo view with sync status

**Infrastructure:**
- ❌ OCR completion triggers for real-time sync
- ❌ Sync queue processor for background operations
- ❌ Health monitoring and stale sync detection
- ❌ Retry queue with exponential backoff
- ❌ Credential encryption at rest

---

## 2. Architectural Principles

### 2.1 Source of Truth
**rmirror-cloud is the single source of truth for all content.**
- User's reMarkable content syncs to rmirror → rmirror syncs to downstream services
- Sync is primarily unidirectional (rmirror → targets)
- Bidirectional sync is optional and service-specific (e.g., todo completion status)

### 2.2 Content-Addressed Architecture
**All content is identified by deterministic hash, not just IDs.**
- Enables deduplication across targets and retries
- Prevents duplicate syncs of unchanged content
- Supports eventual consistency across failures

### 2.3 Real-Time Push Architecture
**Sync is triggered immediately when content changes.**
- OCR completion → immediate sync trigger
- New notebook uploaded → sync queued
- No scheduled/polling sync needed
- Catch-up sync for disconnection recovery only

### 2.4 Multi-Tenancy by Design
**Every sync operation is scoped to a user.**
- All sync tables have `user_id` foreign key
- Integration configs are per-user, per-service
- No cross-user data leakage possible

### 2.5 Target Agnostic
**New services can be added without schema changes.**
- `target_name` string identifies service (not foreign keys)
- `metadata_json` stores target-specific data (Notion page IDs, etc.)
- Abstract `SyncTarget` interface ensures consistency

### 2.6 Page-Level Granularity
**Sync at the page content level, not notebook level.**
- Each page, todo, highlight syncs independently
- Content hash per item enables deduplication
- Partial failures tracked per-page
- Frontend shows per-page sync status

### 2.7 Fault Tolerance
**Failures are expected and handled gracefully.**
- Retry logic with exponential backoff
- Error messages stored and displayed per-page
- Partial sync success (some pages sync, others retry)
- Health checks detect stale/stuck syncs

---

## 3. Database Schema Design

### 3.1 Unified Sync Records Table (Consolidation ✅)

**Decision**: Consolidate `sync_records` and `page_sync_records` into a single `sync_records` table

#### `sync_records` - Universal Content Sync Tracking
```sql
CREATE TABLE sync_records (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Content identification
    item_type VARCHAR(50) NOT NULL,     -- 'page_text', 'todo', 'highlight', 'notebook_metadata'
    item_id VARCHAR(255) NOT NULL,      -- Source ID: page.id, todo.id, highlight.id, notebook.id
    content_hash VARCHAR(64) NOT NULL,  -- SHA-256 of normalized content

    -- Location context (for page_text, todo, highlight types)
    notebook_uuid VARCHAR(255),          -- Which notebook this belongs to
    page_number INTEGER,                 -- Which page (for page_text, todos)

    -- Target identification
    target_name VARCHAR(50) NOT NULL,   -- 'notion', 'readwise', 'obsidian', etc.
    external_id VARCHAR(500),            -- ID in target system (Notion page ID, Readwise highlight ID, etc.)

    -- Status tracking
    status VARCHAR(20) NOT NULL,        -- 'pending', 'success', 'failed', 'retry', 'skipped'
    error_message TEXT,                  -- User-visible error details
    retry_count INTEGER DEFAULT 0,

    -- Target-specific metadata (JSON)
    metadata_json TEXT,                  -- {"notion_page_id": "...", "notion_block_id": "...", "parent_id": "..."}

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    synced_at TIMESTAMP,

    -- Prevent duplicate syncs: same content to same target
    CONSTRAINT unique_content_target UNIQUE(content_hash, target_name, user_id)
);

-- Indices for performance
CREATE INDEX idx_sync_records_user ON sync_records(user_id);
CREATE INDEX idx_sync_records_status ON sync_records(status);
CREATE INDEX idx_sync_records_target ON sync_records(target_name);
CREATE INDEX idx_sync_records_item ON sync_records(item_type, item_id);
CREATE INDEX idx_sync_records_notebook ON sync_records(notebook_uuid);
CREATE INDEX idx_sync_records_page ON sync_records(notebook_uuid, page_number);
CREATE INDEX idx_sync_records_hash_target ON sync_records(content_hash, target_name);
```

**Design Rationale:**

**Why One Table?**
- All sync records follow the same lifecycle (pending → success/failed/retry)
- Same status tracking, retry logic, timestamps for all content types
- Simpler queries: `SELECT * FROM sync_records WHERE notebook_uuid = ? AND target_name = ?`
- Easier statistics: `GROUP BY item_type, status` shows all content types
- Extensible: New content types just need new `item_type` values

**item_type Values:**
- `page_text` - Individual page OCR text (most common)
- `todo` - Todo item extracted from handwriting
- `highlight` - Highlight from PDF/EPUB
- `notebook_metadata` - Notebook-level metadata (title, structure) for initial sync

**metadata_json Examples:**
```json
// Notion page_text sync
{
  "notion_page_id": "abc123",        // Parent notebook page
  "notion_block_id": "def456",       // Specific toggle block for this page
  "parent_type": "toggle_block"
}

// Notion todo sync
{
  "notion_page_id": "abc123",
  "notion_block_id": "todo789",      // Checkbox block ID
  "parent_type": "todo_list"
}

// Readwise highlight sync
{
  "readwise_highlight_id": "12345",
  "source_type": "pdf"
}
```

**How This Replaces page_sync_records:**
- Old: Separate table with notebook_uuid, page_number, notion_page_id, notion_block_id
- New: `item_type='page_text'` + `notebook_uuid` + `page_number` + `metadata_json` contains Notion IDs
- Query: `WHERE item_type='page_text' AND notebook_uuid=? AND page_number=?`
- Frontend: Shows sync status per page by joining on page.id = sync_records.item_id

#### `integration_configs` - User Service Credentials (Encrypted ✅)
```sql
CREATE TABLE integration_configs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Service identification
    target_name VARCHAR(50) NOT NULL,   -- 'notion', 'readwise', etc.
    is_enabled BOOLEAN DEFAULT TRUE,

    -- Configuration (ENCRYPTED at rest using Fernet)
    config_encrypted TEXT NOT NULL,      -- Encrypted JSON: {"api_token": "...", "database_id": "...", ...}

    -- Usage tracking
    last_synced_at TIMESTAMP,
    sync_count INTEGER DEFAULT 0,
    total_items_synced INTEGER DEFAULT 0,

    -- OAuth tokens (if applicable)
    access_token_encrypted TEXT,         -- For OAuth-based integrations
    refresh_token_encrypted TEXT,
    token_expires_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_user_target UNIQUE(user_id, target_name)
);

CREATE INDEX idx_integration_user ON integration_configs(user_id);
CREATE INDEX idx_integration_target ON integration_configs(target_name);
CREATE INDEX idx_integration_enabled ON integration_configs(is_enabled) WHERE is_enabled = TRUE;
```

**Design Rationale:**
- One config per user per service
- **All credentials encrypted at rest** using Fernet symmetric encryption
- Encryption key derived from user-specific salt + app master key
- `config_encrypted` stores service-specific settings (API keys, database IDs, etc.)
- Supports OAuth flow with access/refresh tokens
- Usage metrics for monitoring and debugging

**Encryption Implementation:**
```python
from cryptography.fernet import Fernet
import os
import hashlib

class CredentialEncryption:
    """Encrypt/decrypt integration credentials"""

    @staticmethod
    def _get_encryption_key(user_id: int) -> bytes:
        """Derive user-specific encryption key"""
        master_key = os.getenv('INTEGRATION_MASTER_KEY')  # Set in env
        user_salt = hashlib.sha256(f"user_{user_id}".encode()).hexdigest()

        # Derive Fernet key from master + salt
        key_material = hashlib.sha256(
            f"{master_key}:{user_salt}".encode()
        ).digest()
        return base64.urlsafe_b64encode(key_material)

    @staticmethod
    def encrypt_config(user_id: int, config: dict) -> str:
        """Encrypt config dict to string"""
        cipher = Fernet(CredentialEncryption._get_encryption_key(user_id))
        config_json = json.dumps(config)
        encrypted = cipher.encrypt(config_json.encode())
        return encrypted.decode()

    @staticmethod
    def decrypt_config(user_id: int, encrypted: str) -> dict:
        """Decrypt config string to dict"""
        cipher = Fernet(CredentialEncryption._get_encryption_key(user_id))
        decrypted = cipher.decrypt(encrypted.encode())
        return json.loads(decrypted.decode())
```

**Environment Variables Required:**
```bash
# Add to .env
INTEGRATION_MASTER_KEY=<generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

### 3.2 New Table: `sync_queue` - Event Queue 🚧

**Purpose:** Decouple change detection from sync execution

```sql
CREATE TABLE sync_queue (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- What to sync
    item_type VARCHAR(50) NOT NULL,     -- 'notebook', 'page_text', 'todo', 'highlight'
    item_id VARCHAR(255) NOT NULL,      -- Source ID (notebook_uuid, page UUID, etc.)
    content_hash VARCHAR(64) NOT NULL,  -- Current content hash

    -- Sync request
    target_names TEXT,                   -- JSON array: ["notion", "readwise"] or NULL for all
    priority INTEGER DEFAULT 5,          -- 1 (high) to 10 (low)
    operation VARCHAR(20) NOT NULL,      -- 'create', 'update', 'delete'

    -- Processing
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed'
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    -- Metadata
    trigger_source VARCHAR(50),          -- 'manual', 'webhook', 'scheduled', 'file_watcher'

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sync_queue_user ON sync_queue(user_id);
CREATE INDEX idx_sync_queue_status ON sync_queue(status);
CREATE INDEX idx_sync_queue_priority ON sync_queue(priority);
CREATE INDEX idx_sync_queue_item ON sync_queue(item_id);
CREATE INDEX idx_sync_queue_pending ON sync_queue(status, priority) WHERE status = 'pending';
```

**Design Rationale:**
- Decouples change detection from sync execution
- Priority queue enables user-triggered syncs to jump ahead
- `target_names` allows selective sync (e.g., only to Notion)
- Can be processed by background workers

### 3.3 Enhanced Content Tables 🚧

**Add Change Tracking Fields:**

```sql
-- Add to notebooks table
ALTER TABLE notebooks ADD COLUMN content_hash VARCHAR(64);
ALTER TABLE notebooks ADD COLUMN last_hash_computed_at TIMESTAMP;

-- Add to pages table (via notebook_pages join table)
ALTER TABLE notebook_pages ADD COLUMN content_hash VARCHAR(64);
ALTER TABLE notebook_pages ADD COLUMN last_hash_computed_at TIMESTAMP;

-- Add to todos table
ALTER TABLE todos ADD COLUMN content_hash VARCHAR(64);

-- Add to highlights table
ALTER TABLE highlights ADD COLUMN content_hash VARCHAR(64);
```

**Triggers for Auto-Hash Computation:**

```sql
-- Example: Auto-compute page content hash on OCR completion
CREATE OR REPLACE FUNCTION compute_page_content_hash()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.ocr_status = 'completed' AND NEW.ocr_text IS NOT NULL THEN
        NEW.file_hash = encode(
            digest(
                NEW.notebook_id::text || ':' || NEW.page_number::text || ':' || NEW.ocr_text,
                'sha256'
            ),
            'hex'
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_compute_page_hash
    BEFORE INSERT OR UPDATE ON pages
    FOR EACH ROW
    EXECUTE FUNCTION compute_page_content_hash();
```

---

## 4. Content Fingerprinting Strategy

### 4.1 Hashing Algorithm

**Use SHA-256 for all content hashes** (already implemented in ContentFingerprint service)

### 4.2 Per-Content-Type Normalization

#### Notebooks
```python
def fingerprint_notebook(notebook: Notebook, pages: List[Page]) -> str:
    """Hash based on stable notebook metadata + all page content"""
    data = {
        'type': 'notebook',
        'title': notebook.visible_name.strip(),
        'document_type': notebook.document_type,
        'page_count': len(pages),
        'pages': [
            {
                'number': p.page_number,
                'text': (p.ocr_text or '').strip(),
                'confidence': p.confidence_score
            }
            for p in sorted(pages, key=lambda x: x.page_number)
        ]
    }
    return _sha256_hash(data)
```

#### Individual Pages
```python
def fingerprint_page(notebook_uuid: str, page_number: int, ocr_text: str) -> str:
    """Hash based on position + content"""
    data = {
        'type': 'page_text',
        'notebook_uuid': notebook_uuid,
        'page_number': page_number,
        'text': (ocr_text or '').strip()
    }
    return _sha256_hash(data)
```

#### Todos
```python
def fingerprint_todo(todo: Todo) -> str:
    """Hash based on text + location"""
    data = {
        'type': 'todo',
        'text': todo.text.strip(),
        'notebook_uuid': todo.notebook_uuid,
        'page_number': todo.page_number,
        # Exclude 'completed' status to allow bidirectional sync
    }
    return _sha256_hash(data)
```

#### Highlights
```python
def fingerprint_highlight(highlight: Highlight) -> str:
    """Hash based on text + position"""
    data = {
        'type': 'highlight',
        'original_text': highlight.original_text.strip(),
        'corrected_text': (highlight.corrected_text or '').strip(),
        'source_file': highlight.source_file,
        'page_number': highlight.page_number,
        'note': (highlight.note or '').strip()
    }
    return _sha256_hash(data)
```

**Key Principles:**
- Exclude timestamps and mutable IDs from hashes
- Sort arrays for deterministic ordering
- Strip whitespace for normalization
- Use JSON serialization with `sort_keys=True`

---

## 5. Service Integration Architecture

### 5.1 Abstract SyncTarget Interface ✅

**Already implemented in `/app/core/sync_engine.py`:**

```python
class SyncTarget(ABC):
    """Universal interface all sync targets must implement"""

    def __init__(self, target_name: str):
        self.target_name = target_name

    @abstractmethod
    async def sync_item(self, item: SyncItem) -> SyncResult:
        """Sync a single item to this target"""
        pass

    @abstractmethod
    async def check_duplicate(self, content_hash: str) -> Optional[str]:
        """Check if content already exists (returns external_id)"""
        pass

    @abstractmethod
    async def update_item(self, external_id: str, item: SyncItem) -> SyncResult:
        """Update existing item"""
        pass

    @abstractmethod
    async def delete_item(self, external_id: str) -> SyncResult:
        """Delete item from target"""
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Test target connection and credentials"""
        pass

    @abstractmethod
    def get_target_info(self) -> Dict[str, Any]:
        """Return capabilities and metadata"""
        pass
```

### 5.2 Concrete Implementations

#### Notion ✅ (Already Implemented)
**Location:** `/app/integrations/notion_sync.py`

**Capabilities:**
- ✅ Full notebook sync with pages as toggle blocks
- ✅ Markdown formatting support (headings, lists, bold, italic)
- ✅ Deduplication by notebook UUID property
- ✅ Update existing pages
- 🚧 Page-level incremental sync
- ❌ Todo sync
- ❌ Highlight sync

**Configuration:**
```json
{
  "api_token": "secret_xxx",
  "database_id": "abc123",
  "verify_ssl": true
}
```

#### Readwise 🚧 (To Be Implemented)
**Location:** `/app/integrations/readwise_sync.py` (create new)

**Capabilities:**
- ✅ Highlight sync with source attribution
- ✅ Note sync
- ❌ Notebook sync (not supported by Readwise)
- ❌ Todo sync

**Configuration:**
```json
{
  "api_token": "readwise_xxx"
}
```

**API Endpoints:**
- POST `/highlights` - Create highlights
- GET `/highlights` - List highlights (deduplication check)

#### Obsidian 🚧 (Future)
**Local file sync via WebDAV or Obsidian API**

**Capabilities:**
- Markdown file export per notebook
- Image embedding
- Folder structure

#### Apple Notes 🚧 (Future via Shortcuts/AppleScript)
#### Roam Research 🚧 (Future)
#### Bear 🚧 (Future)

### 5.3 Target Registration

```python
class UnifiedSyncManager:
    def __init__(self, db: Session):
        self.db = db
        self.targets: Dict[str, SyncTarget] = {}

    def register_target(self, target: SyncTarget):
        """Add sync target"""
        self.targets[target.target_name] = target

    async def get_or_create_target(self, user_id: int, target_name: str) -> SyncTarget:
        """Lazy-load target from user's integration config"""
        config = self._get_integration_config(user_id, target_name)
        if not config or not config.is_enabled:
            raise ValueError(f"Integration {target_name} not configured")

        # Factory pattern
        if target_name == 'notion':
            return NotionSyncTarget(
                api_token=config.config['api_token'],
                database_id=config.config['database_id']
            )
        elif target_name == 'readwise':
            return ReadwiseSyncTarget(
                api_token=config.config['api_token']
            )
        # ... etc
```

---

## 6. Sync Workflow & State Machine

### 6.1 Sync Lifecycle

```
1. CHANGE DETECTION
   ├─ OCR completion triggers page content hash update
   ├─ New notebook uploaded
   ├─ User manually requests sync
   └─ Creates entry in sync_queue

2. QUEUE PROCESSING (Background Worker)
   ├─ Poll sync_queue for pending items (ORDER BY priority, created_at)
   ├─ Mark item as 'processing'
   ├─ Load item data from source table
   └─ Calculate current content hash

3. DEDUPLICATION CHECK
   ├─ Query sync_records WHERE content_hash = ? AND target_name = ?
   ├─ If exists AND status = 'success' → SKIP
   ├─ If exists AND content changed → UPDATE operation
   └─ If not exists → CREATE operation

4. TARGET SYNC
   ├─ Get user's integration config for target
   ├─ Instantiate SyncTarget implementation
   ├─ Call sync_item(item) or update_item(external_id, item)
   └─ Receive SyncResult

5. RESULT RECORDING
   ├─ Update sync_records with:
   │   ├─ external_id (if new)
   │   ├─ status (success/failed)
   │   ├─ error_message (if failed)
   │   └─ synced_at (if success)
   ├─ Update page_sync_records (if page-level)
   └─ Mark sync_queue item as 'completed' or 'failed'

6. RETRY LOGIC (if failed)
   ├─ Increment retry_count
   ├─ Calculate backoff: min(30 * 2^retry_count, 3600) seconds
   ├─ If retry_count < max_retries (5):
   │   └─ Set status = 'retry', updated_at = now + backoff
   └─ Else:
       └─ Set status = 'failed' (permanent)
```

### 6.2 Status State Machine

```
sync_records.status values:

'pending'      Initial state, queued for sync
    ↓
'in_progress'  Currently syncing to target
    ↓
    ├─ SUCCESS → 'success' (terminal state)
    ├─ FAILURE → 'retry' (if retries remaining)
    │              ↓
    │          [exponential backoff]
    │              ↓
    │          'in_progress' (retry attempt)
    │              ↓
    │          ... (repeat until success or max retries)
    │              ↓
    └─ FAILURE (max retries) → 'failed' (terminal state)

'skipped'      Content already synced, no action needed (terminal state)
```

---

## 7. Implementation Plan

### Phase 1: Foundation Enhancement 🚧

**Goal:** Improve existing infrastructure for robustness

**Tasks:**
1. Create `sync_queue` table and migration
2. Implement background sync queue processor
3. Add content hash triggers to content tables
4. Create Pydantic schemas for sync operations
5. Implement health check and stale sync detection
6. Add comprehensive logging and monitoring

**Deliverables:**
- Migration file: `create_sync_queue_table.py`
- Service: `/app/core/sync_queue_processor.py`
- Trigger SQL: `/alembic/versions/xxx_add_content_hash_triggers.py`
- Schemas: `/app/schemas/sync.py`

### Phase 2: Page-Level Sync 🚧

**Goal:** Enable incremental notebook updates

**Tasks:**
1. Implement page-level sync in NotionSyncTarget
2. Use page_sync_records for tracking Notion block IDs
3. Handle page additions, updates, deletions
4. Respect Notion API rate limits (50 blocks/request)
5. Test with large notebooks (100+ pages)

**Deliverables:**
- Enhanced `NotionSyncTarget._sync_page_text()` method
- Page batch processor
- Integration tests

### Phase 3: Readwise Integration 🚧

**Goal:** Sync highlights to Readwise

**Tasks:**
1. Create `ReadwiseSyncTarget` class
2. Implement Readwise API client
3. Map highlights to Readwise format (source, text, note)
4. Handle Readwise deduplication
5. Test with real Readwise account

**Deliverables:**
- `/app/integrations/readwise_sync.py`
- Readwise API client: `/app/integrations/readwise_client.py`
- Integration tests

### Phase 4: Todo & Highlight Sync to Notion 🚧

**Goal:** Complete Notion integration

**Tasks:**
1. Implement todo sync as checkboxes in Notion
2. Implement highlight sync as callouts/quotes
3. Handle bidirectional todo completion (optional)
4. Test mixed content notebooks

**Deliverables:**
- Enhanced NotionSyncTarget with todo/highlight support
- Bidirectional sync option

### Phase 5: Additional Integrations 🚧

**Goal:** Expand service ecosystem

**Targets (prioritize based on user demand):**
1. Obsidian (local file sync)
2. Apple Notes (via Shortcuts API)
3. Roam Research
4. Bear Notes
5. Custom webhook targets

---

## 8. API Design

### 8.1 Existing Endpoints ✅

#### POST `/v1/sync/trigger`
Trigger sync to specific or all targets

**Request:**
```json
{
  "target_name": "notion",  // or null for all
  "item_type": "notebook",  // or null for all types
  "notebook_uuids": ["uuid1", "uuid2"],  // optional, specific notebooks
  "limit": 10  // max items to sync
}
```

**Response:**
```json
{
  "synced_count": 5,
  "failed_count": 1,
  "skipped_count": 2,
  "targets_processed": ["notion", "readwise"]
}
```

#### GET `/v1/sync/stats`
Get sync statistics

**Response:**
```json
{
  "total_syncs": 150,
  "status_counts": {
    "success": 120,
    "failed": 10,
    "pending": 15,
    "retry": 5
  },
  "target_counts": {
    "notion": 80,
    "readwise": 70
  },
  "type_counts": {
    "notebook": 50,
    "highlight": 100
  }
}
```

### 8.2 New Endpoints 🚧

#### GET `/v1/sync/queue`
View sync queue status

**Response:**
```json
{
  "pending": 15,
  "processing": 3,
  "failed": 2,
  "items": [
    {
      "id": 123,
      "item_type": "notebook",
      "item_id": "uuid-123",
      "target_names": ["notion"],
      "status": "pending",
      "priority": 5,
      "created_at": "2025-12-27T10:00:00Z"
    }
  ]
}
```

#### POST `/v1/sync/queue/{item_id}/retry`
Manually retry failed sync

#### DELETE `/v1/sync/queue/{item_id}`
Cancel pending sync

#### GET `/v1/sync/health`
System health check

**Response:**
```json
{
  "queue_processor": "running",
  "last_processed_at": "2025-12-27T10:15:00Z",
  "stale_syncs_count": 2,
  "targets": {
    "notion": {"status": "healthy", "last_sync": "..."},
    "readwise": {"status": "healthy", "last_sync": "..."}
  }
}
```

---

## 9. Error Handling & Retry Strategy

### 9.1 Retry Logic

**Exponential Backoff:**
```python
def calculate_retry_delay(retry_count: int) -> int:
    """Calculate retry delay in seconds"""
    base_delay = 30  # seconds
    max_delay = 3600  # 1 hour
    delay = min(base_delay * (2 ** retry_count), max_delay)
    return delay
```

**Max Retries:** 5 attempts

**Retry Triggers:**
- Network errors
- Target API rate limits (429)
- Transient server errors (5xx)

**No Retry (Permanent Failure):**
- Authentication errors (401)
- Invalid data (400)
- Resource not found (404)
- Quota exceeded (permanent)

### 9.2 Error Classification

```python
class SyncErrorType(Enum):
    NETWORK_ERROR = "network_error"           # Retry
    RATE_LIMIT = "rate_limit"                 # Retry with backoff
    AUTH_ERROR = "auth_error"                 # No retry, notify user
    INVALID_DATA = "invalid_data"             # No retry, log
    QUOTA_EXCEEDED = "quota_exceeded"         # No retry, notify user
    UNKNOWN_ERROR = "unknown_error"           # Retry
```

### 9.3 User Notifications

**When to Notify:**
- Integration authentication failure
- Quota exceeded
- Max retries exhausted
- First successful sync to new target

**Notification Methods:**
- Email (optional, user preference)
- In-app notification (dashboard)
- Webhook (for enterprise users)

---

## 10. Performance & Scalability

### 10.1 Batching

**Notebook Pages:**
- Notion: Max 50 blocks per request
- Batch pages into groups of 50 for create/update operations

**Highlights:**
- Readwise: Up to 500 highlights per request
- Batch in groups of 100 for safety

### 10.2 Rate Limiting

**Target-Specific Limits:**
- Notion: 3 requests/second
- Readwise: 20 requests/minute

**Implementation:**
```python
class RateLimiter:
    def __init__(self, requests_per_second: float):
        self.rate = requests_per_second
        self.last_request_time = 0

    async def acquire(self):
        """Wait if necessary to respect rate limit"""
        now = time.time()
        time_since_last = now - self.last_request_time
        required_interval = 1.0 / self.rate

        if time_since_last < required_interval:
            await asyncio.sleep(required_interval - time_since_last)

        self.last_request_time = time.time()
```

### 10.3 Concurrent Processing

**Sync Queue Processor:**
- Process up to 5 items concurrently per target
- Separate worker per target to prevent cross-contamination
- Async I/O for efficient API calls

---

## 11. Testing Strategy

### 11.1 Unit Tests

- ContentFingerprint hash consistency
- SyncTarget interface implementations
- Retry logic and backoff calculation
- Error classification

### 11.2 Integration Tests

- Mock target services for deterministic testing
- Test full sync lifecycle (queue → sync → record)
- Test deduplication scenarios
- Test retry and failure scenarios

### 11.3 E2E Tests

- Real notebook → Notion sync
- Real highlights → Readwise sync
- Large notebook (100+ pages) performance
- Network failure recovery

---

## 12. Monitoring & Observability

### 12.1 Metrics to Track

- Sync success/failure rates per target
- Average sync duration per item type
- Queue depth and processing lag
- Retry counts and failure reasons
- API call counts and rate limit hits

### 12.2 Logging

**Structured Logging:**
```python
logger.info(
    "Sync completed",
    extra={
        "user_id": user.id,
        "target_name": "notion",
        "item_type": "notebook",
        "item_id": notebook.uuid,
        "content_hash": content_hash,
        "status": "success",
        "duration_ms": duration,
        "external_id": result.target_id
    }
)
```

**Log Levels:**
- DEBUG: Detailed sync progress
- INFO: Sync start/complete, queue processing
- WARNING: Retries, rate limit hits
- ERROR: Permanent failures, auth errors

---

## 13. Security Considerations

### 13.1 Credential Storage

**Current:** `integration_configs.config_json` stores plaintext JSON

**Recommended Enhancement:**
```python
from cryptography.fernet import Fernet

class IntegrationConfig(Base):
    config_encrypted = Column(Text)  # Encrypted with user-specific key

    @property
    def config(self) -> dict:
        """Decrypt and return config"""
        cipher = Fernet(get_user_encryption_key(self.user_id))
        decrypted = cipher.decrypt(self.config_encrypted.encode())
        return json.loads(decrypted)

    @config.setter
    def config(self, value: dict):
        """Encrypt and store config"""
        cipher = Fernet(get_user_encryption_key(self.user_id))
        encrypted = cipher.encrypt(json.dumps(value).encode())
        self.config_encrypted = encrypted.decode()
```

### 13.2 API Key Rotation

- Support key rotation without downtime
- Store multiple keys per integration (active + backup)
- Automatic retry with backup key on auth failure

### 13.3 Access Control

- All sync operations scoped to user_id
- Verify user owns content before syncing
- No cross-user sync possible

---

## 14. Migration Path

### 14.1 Existing Users

**Scenario:** User already has notebooks in rmirror, wants to enable Notion sync

**Steps:**
1. User adds Notion integration via `/integrations/` API
2. System creates `integration_config` record
3. System queues all existing notebooks for sync
4. Background processor syncs notebooks to Notion
5. Future updates sync automatically

### 14.2 Backfill Strategy

**Large User Libraries:**
- Prioritize recent notebooks first
- Batch sync in groups of 10 notebooks
- Respect daily API limits
- Show progress in UI

---

## 15. Future Enhancements

### 15.1 Bidirectional Sync

**Use Case:** User completes todo in Notion, sync back to rmirror

**Architecture:**
- Webhook endpoints for target services
- `sync_queue` tracks bidirectional changes
- Conflict resolution (last-write-wins or manual)

### 15.2 Selective Sync

**Use Case:** User only wants certain notebooks synced

**Implementation:**
- `notebook_sync_settings` table
- Per-notebook, per-target enabled/disabled flag
- Sync rules (tag-based, folder-based)

### 15.3 Custom Transformations

**Use Case:** User wants custom formatting for Notion export

**Implementation:**
- Pluggable transformation pipeline
- User-defined templates
- Python code execution sandbox

---

## 16. Open Questions for Discussion

1. **Scheduled Sync:** Should we implement automatic recurring sync (hourly, daily)? Or rely on webhook triggers + manual sync?

2. **Quota Management:** How to handle Notion/Readwise free tier limits? Throttle syncs? Notify user?

3. **Conflict Resolution:** For bidirectional sync (todos), how to handle conflicts? Last-write-wins? Manual resolution UI?

4. **Large Notebooks:** Should we split very large notebooks (500+ pages) across multiple Notion pages? What's the threshold?

5. **Partial Failures:** If 10 pages sync but 1 fails, what's the overall notebook sync status? Success with warnings?

6. **Real-Time Sync:** Should we support real-time sync via WebSocket updates from reMarkable? Or is polling sufficient?

7. **Dry-Run Mode:** Should we provide a preview/dry-run mode before first sync? Shows what will be created?

8. **Export Format:** For services like Obsidian, should we support multiple export formats (Markdown, HTML, PDF)?

---

## 17. Success Criteria

### Phase 1 Complete When:
- ✅ Sync queue table created and indexed
- ✅ Background queue processor running reliably
- ✅ Content hashes auto-computed on content changes
- ✅ Health monitoring dashboard shows queue status
- ✅ All logs structured and queryable

### Phase 2 Complete When:
- ✅ Single page update syncs only that page to Notion (not full notebook)
- ✅ 100-page notebook syncs in <5 minutes
- ✅ Page additions/deletions reflected in Notion
- ✅ No duplicate pages created

### Phase 3 Complete When:
- ✅ Highlights sync to Readwise with correct attribution
- ✅ Readwise integration configured via UI
- ✅ 1000+ highlights sync successfully
- ✅ Deduplication prevents duplicate highlights

### Final Success:
- ✅ 99% sync success rate across all targets
- ✅ Average sync time <30 seconds for notebooks
- ✅ Zero data loss during failures
- ✅ Comprehensive error reporting for users
- ✅ 3+ service integrations working

---

## Appendix A: Database Schema ERD

```
users
  ├── notebooks (1:N)
  │     └── notebook_pages (N:M with pages)
  │           └── pages
  ├── highlights (1:N)
  ├── todos (1:N)
  ├── integration_configs (1:N) [per target_name]
  ├── sync_records (1:N) [universal sync tracking]
  ├── page_sync_records (1:N) [granular page tracking]
  └── sync_queue (1:N) [pending sync operations]
```

## Appendix B: Key Files to Create/Modify

**New Files:**
- `/backend/app/core/sync_queue_processor.py` - Background queue worker
- `/backend/app/integrations/readwise_sync.py` - Readwise integration
- `/backend/app/integrations/readwise_client.py` - Readwise API client
- `/backend/app/schemas/sync.py` - Pydantic models for sync operations
- `/backend/alembic/versions/xxx_create_sync_queue.py` - Migration
- `/backend/alembic/versions/xxx_add_content_hash_triggers.py` - Triggers

**Modify:**
- `/backend/app/core/unified_sync_manager.py` - Add queue integration
- `/backend/app/integrations/notion_sync.py` - Add page-level sync
- `/backend/app/api/sync.py` - Add queue endpoints
- `/backend/app/models/sync_record.py` - Add SyncQueue model

---

**End of Architecture Document**

This architecture provides a solid foundation for building a robust, scalable, multi-service sync system that can grow with rmirror's user base and integration ecosystem.