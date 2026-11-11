# Unified Multi-Service Sync Architecture v2

## Executive Summary

**Primary Focus**: Complete Notion integration first (todos, highlights, page-level sync), then expand
**Sync Model**: Real-time push (reMarkable → Agent → rmirror-cloud → Service on OCR completion)
**Master**: rmirror-cloud is single source of truth (no bidirectional sync, no conflict resolution)
**Delivery Format**: Markdown export to all services

---

## Key Decisions from Review

1. **Single sync_records table** - Replaces both sync_records and page_sync_records
2. **Page-level granularity** - Track sync status per page, show in frontend
3. **Encryption from day one** - All credentials encrypted at rest using Fernet
4. **Real-time triggers** - OCR completion immediately triggers sync
5. **Catch-up sync only** - No scheduled/polling sync except for disconnection recovery
6. **Fuzzy todo deduplication** - Prevent recreating todos on re-OCR

---

## Implementation Priorities

### Phase 1: Complete Notion Integration ✅ PRIORITY
- Page-level sync (incremental updates)
- Todo sync to checkboxes
- Highlight sync to callouts
- Frontend integration setup UI
- Frontend todo view with sync status

### Phase 2: Readwise Integration (LATER)
### Phase 3: Other Services (FUTURE - Obsidian, Apple Notes, etc.)

---

## Database Schema

### Consolidated sync_records Table

**Replaces**: Both `sync_records` AND `page_sync_records`

```sql
CREATE TABLE sync_records (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Content identification
    item_type VARCHAR(50) NOT NULL,     -- 'page_text', 'todo', 'highlight'
    item_id VARCHAR(255) NOT NULL,      -- Source: page.id, todo.id, highlight.id
    content_hash VARCHAR(64) NOT NULL,  -- SHA-256 for deduplication
    page_uuid VARCHAR(255),              -- reMarkable page UUID (when available)

    -- Location context
    notebook_uuid VARCHAR(255),          -- Which notebook
    page_number INTEGER,                 -- Which page (null for notebook-level)

    -- Target
    target_name VARCHAR(50) NOT NULL,   -- 'notion'
    external_id VARCHAR(500),            -- Notion page/block ID

    -- Status
    status VARCHAR(20) NOT NULL,        -- 'pending', 'success', 'failed', 'retry'
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    -- Target-specific data
    metadata_json TEXT,                  -- {"notion_page_id": "...", "notion_block_id": "..."}

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    synced_at TIMESTAMP,

    CONSTRAINT unique_content_target UNIQUE(content_hash, target_name, user_id)
);

CREATE INDEX idx_sync_user ON sync_records(user_id);
CREATE INDEX idx_sync_status ON sync_records(status);
CREATE INDEX idx_sync_item ON sync_records(item_type, item_id);
CREATE INDEX idx_sync_notebook_page ON sync_records(notebook_uuid, page_number);
CREATE INDEX idx_sync_page_uuid ON sync_records(page_uuid);
```

**Why one table?**
- Same lifecycle for all content (page_text, todos, highlights)
- Simple queries: `WHERE notebook_uuid=? AND target_name='notion'`
- Easy stats: `GROUP BY item_type, status`
- `metadata_json` stores target-specific IDs (Notion page/block IDs)

### Encrypted integration_configs

```sql
CREATE TABLE integration_configs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    target_name VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,

    -- ENCRYPTED credentials (Fernet)
    config_encrypted TEXT NOT NULL,

    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_user_target UNIQUE(user_id, target_name)
);
```

**Encryption**: User-specific key derived from master + user_id salt

### Fuzzy Todo Deduplication

**Problem**: OCR variations create duplicate todos
**Solution**: Fuzzy matching on insert/update

```sql
CREATE TABLE todos (
    -- existing fields
    content_hash VARCHAR(64),            -- Normalized hash
    fuzzy_signature VARCHAR(100),        -- Lowercase, no punctuation, sorted words

    CONSTRAINT unique_fuzzy_todo UNIQUE(fuzzy_signature, notebook_uuid, user_id)
);
```

```python
def generate_fuzzy_signature(text: str) -> str:
    """Create fuzzy-matchable signature"""
    # Lowercase, remove punctuation, sort words
    words = re.sub(r'[^\w\s]', '', text.lower()).split()
    return '_'.join(sorted(words))
```

On todo sync: Check if `fuzzy_signature` exists before creating new sync record

---

## Content Fingerprinting

### Page-Level Only (Recommendation)

**No notebook-level hash needed**

**Pros of page-level only:**
- ✅ Incremental sync - only changed pages sync
- ✅ Simpler logic - one hash strategy
- ✅ Better performance - don't rehash entire notebook
- ✅ Partial failures OK - some pages succeed, others retry

**Notebook-level changes** (title rename, etc.):
- ✅ Handled via `notebook_metadata` item_type in sync_records
- ✅ Notebook title/structure changes tracked separately from page content
- ✅ First sync iterates all pages (acceptable one-time cost)

**Decision**: Page-level only for content, separate `notebook_metadata` item_type for structural changes

### Hash Strategy

```python
# Page text
content_hash = sha256(f"{notebook_uuid}:{page_number}:{ocr_text.strip()}")

# Todo
fuzzy_sig = generate_fuzzy_signature(todo.text)
content_hash = sha256(f"{fuzzy_sig}:{notebook_uuid}:{page_number}")

# Highlight
content_hash = sha256(f"{original_text}:{corrected_text}:{source_file}:{page_num}")
```

---

## Sync Workflow

### Trigger: OCR Completion

```python
# In OCR processing job
async def on_ocr_complete(page_id: int):
    page = db.query(Page).get(page_id)

    # Calculate content hash
    content_hash = fingerprint_page(page)

    # Queue sync to all enabled targets
    for integration in user.integration_configs.filter(is_enabled=True):
        queue_sync(
            user_id=user.id,
            item_type='page_text',
            item_id=page.id,
            content_hash=content_hash,
            target_name=integration.target_name
        )
```

### Sync Queue Processing

```
1. OCR complete → queue_sync() → sync_queue table
2. Background worker polls queue
3. Check sync_records for duplicate (content_hash + target)
4. If new/changed → call SyncTarget.sync_item()
5. Record result in sync_records
6. Mark queue item complete
7. If failed → retry with backoff
```

### Real-Time Flow

```
reMarkable → Agent uploads .rm → Cloud stores → OCR job → OCR complete
                                                              ↓
                                                        queue_sync()
                                                              ↓
                                                        sync_worker
                                                              ↓
                                                      Notion API call
                                                              ↓
                                                     update sync_records
```

### Catch-Up Sync

**Scenario**: Integration disabled for 2 weeks, re-enabled
**Solution**: Query all pages without successful sync record, queue them

```sql
-- Find unsynced pages
SELECT p.id, p.notebook_uuid, np.page_number
FROM pages p
JOIN notebook_pages np ON p.id = np.page_id
WHERE p.ocr_status = 'completed'
  AND NOT EXISTS (
    SELECT 1 FROM sync_records sr
    WHERE sr.item_id = p.id::text
      AND sr.item_type = 'page_text'
      AND sr.target_name = 'notion'
      AND sr.status = 'success'
      AND sr.user_id = ?
  )
```

---

## Frontend Requirements

### 1. Integration Setup UI

**Location**: `/dashboard/settings/integrations`

**Notion Setup Flow**:
1. Click "Connect Notion"
2. Instructions: "Get your Notion integration token..."
3. Input fields:
   - Notion API Token (password field)
   - Notion Database ID
4. Test connection button
5. Save encrypted config
6. Enable/disable toggle

**UI Components needed**:
- Integration card component
- OAuth flow handler (future)
- Test connection status indicator

### 2. Notebook Todo View

**Location**: `/dashboard/notebooks/{id}` (expandable section at top)

```
┌─ Todos in this Notebook ──────────────────────┐
│ ☐ Review chapter 3              ✅ Synced     │
│ ☐ Add diagrams                  ⏱ Syncing...  │
│ ☐ Fix typos on page 12          ❌ Failed     │
└────────────────────────────────────────────────┘
```

**Features**:
- Collapsible todo list
- Sync status icon per todo
- Click to jump to source page
- Manual retry button for failed todos

### 3. Per-Page Sync Status

**Location**: Page cards in notebook view

```
Page 5                          Last synced to Notion: 2 hours ago
┌─────────────────────────┐
│ OCR text here...        │     ✅ Notion
│                         │     ❌ Readwise (Retry)
└─────────────────────────┘
```

**Display**:
- "Last synced to {target}: {time ago}" OR
- "{target}: Syncing..." OR
- "{target}: Failed - {error}" with retry button

---

## Implementation Steps

### Step 1: Database Migration
- [ ] Create new `sync_records` schema (consolidated)
- [ ] Add `fuzzy_signature` to todos table
- [ ] Add `config_encrypted` to integration_configs
- [ ] Migrate existing data

### Step 2: Credential Encryption
- [ ] Implement Fernet encryption service
- [ ] Add `INTEGRATION_MASTER_KEY` to env
- [ ] Update IntegrationConfig model with encrypt/decrypt

### Step 3: Real-Time Sync Triggers
- [ ] Add OCR completion hook
- [ ] Implement `queue_sync()` function
- [ ] Create `sync_queue` table
- [ ] Build background sync worker

### Step 4: Complete Notion Integration
- [ ] Page-level sync (incremental)
- [ ] Todo sync to checkboxes
- [ ] Highlight sync to callouts
- [ ] Batch API calls (50 blocks/request limit)

### Step 5: Frontend Integration UI
- [ ] Settings page: integration cards
- [ ] Notion setup form with test connection
- [ ] OAuth flow (if needed)

### Step 6: Frontend Todo View
- [ ] Notebook page: expandable todos section
- [ ] Sync status icons
- [ ] Manual retry buttons

### Step 7: Per-Page Sync Status
- [ ] Add sync status to page cards
- [ ] Join sync_records on page.id
- [ ] Show last_synced_at or error

---

## Open Questions - Answers

1. **Scheduled sync?** → NO, real-time only + catch-up on reconnect
2. **Quota management?** → Show usage in UI, pause sync when quota hit
3. **Conflict resolution?** → N/A, rmirror is master (unidirectional)
4. **Large notebooks?** → Split into batches of 50 blocks (Notion limit)
5. **Partial failures?** → Track per-page, show in UI
6. **Real-time sync?** → YES, OCR completion triggers sync
7. **Dry-run mode?** → YES, useful for testing
8. **Export format?** → Markdown

---

## Next Steps

Please review and confirm:
1. Database schema consolidation (one sync_records table)
2. Encryption implementation approach
3. Frontend UI mockups
4. Implementation step order

Ready to proceed with implementation?
