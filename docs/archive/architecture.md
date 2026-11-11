# rMirror Cloud Architecture

## Overview

rMirror Cloud is a multi-tenant cloud service that syncs reMarkable tablet content, processes it with AI-powered OCR, and distributes it to connected services like Notion. The architecture is designed to scale from 100 to 10,000+ users with graceful degradation and intelligent quota management.

## System Components

```
┌──────────────────────────────────────────────────────────────┐
│                      User's Device                            │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Python Mac Agent (v1.4+)                   │ │
│  │  • File system watcher (watchdog library)               │ │
│  │  • Change detection & deduplication                     │ │
│  │  • Upload queue with batching & retry logic             │ │
│  │  • 30-day JWT authentication via Clerk                  │ │
│  │  • Web UI for configuration (localhost:9090)            │ │
│  │  • Quota display with color-coded status                │ │
│  │  • rumps macOS menu bar integration                     │ │
│  └─────────────────────────────────────────────────────────┘ │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS (TLS 1.3)
                         │ Gzipped payloads
                         ↓
┌──────────────────────────────────────────────────────────────┐
│                    Cloud Infrastructure                       │
│                      (Hetzner VPS)                            │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │               API Gateway Layer                         │  │
│  │  ┌──────────────┐  ┌──────────────┐                   │  │
│  │  │  Cloudflare  │→ │    nginx     │                   │  │
│  │  │  CDN + DDoS  │  │ (rate limit) │                   │  │
│  │  └──────────────┘  └──────┬───────┘                   │  │
│  └────────────────────────────┼──────────────────────────┘  │
│                                ↓                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │            FastAPI Application Servers                 │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │  uvicorn --workers 2 (multiple workers)        │   │  │
│  │  │  (4GB RAM, systemd managed)                     │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  │  • Clerk OAuth verification (dashboard)                │  │
│  │  • Agent token exchange (/auth/agent-token)            │  │
│  │  • Rate limiting: 300/min auth, 30/min anon            │  │
│  │  • File upload handling                                │  │
│  │  • Background sync worker (asyncio)                    │  │
│  │  • Quota enforcement before OCR                        │  │
│  │  • API endpoints for dashboard                         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                ↓                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              Data Layer                                 │  │
│  │  ┌─────────────────┐                                   │  │
│  │  │  PostgreSQL 15  │                                   │  │
│  │  │  (Production)   │  Development: SQLite              │  │
│  │  │                 │                                   │  │
│  │  │ • User accounts │                                   │  │
│  │  │ • Subscriptions │  (tier, billing period)           │  │
│  │  │ • Quota usage   │  (ocr_pages, limit, used)         │  │
│  │  │ • Notebooks     │  (uuid, parent_uuid hierarchy)    │  │
│  │  │ • Pages         │  (page_uuid, ocr_status, hash)    │  │
│  │  │ • Sync queue    │  (item_type, status, priority)    │  │
│  │  │ • Sync records  │  (page_uuid deduplication)        │  │
│  │  │ • Integrations  │  (credentials, settings)          │  │
│  │  └─────────────────┘                                   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                ↓                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │    Background Sync Worker (asyncio-based)              │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │  • Polls sync_queue every 5 seconds              │  │  │
│  │  │  • Database-level coordination via status flags  │  │  │
│  │  │  • Row-level locking (FOR UPDATE SKIP LOCKED)   │  │  │
│  │  │  • Handles NOTEBOOK and NOTEBOOK_METADATA types │  │  │
│  │  │  • Multiple workers with uvicorn --workers 2    │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                ↓                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │         File Storage (S3-compatible)                    │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │  Backblaze B2                                   │   │  │
│  │  │  • .rm files                                    │   │  │
│  │  │  • Generated PDFs                               │   │  │
│  │  │  • EPUB/PDF source files                        │   │  │
│  │  │  • Lifecycle: auto-delete after 90 days         │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────┬──────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────┐
│                  External Services                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Claude API   │  │   Notion     │  │   Readwise   │    │
│  │ (OCR)        │  │   (Sync)     │  │  (Planned)   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└────────────────────────────────────────────────────────────┘
                        ↑
                        │ Browser (Clerk OAuth)
                        │
┌────────────────────────────────────────────────────────────┐
│                  Web Dashboard (Next.js)                    │
│  • Hosted on Vercel (auto-scaling)                         │
│  • Clerk authentication with session tokens                │
│  • Server-side rendering for performance                   │
│  • API calls to FastAPI backend                            │
│  • Quota UI with upgrade CTAs                              │
│  • 402 error handling for quota exhaustion                 │
└────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. File Upload Flow (with Quota Management)

```
Agent detects .rm file change
  ↓
Calculate SHA-256 hash
  ↓
Check if already uploaded (local cache)
  ↓ (if new)
POST /api/upload/files (with 30-day JWT)
  ↓
Backend: Validate auth
  ↓
Check quota: quota_service.check_quota(user_id, 'ocr_pages', num_pages)
  ↓
If quota OK:                          If quota exhausted:
  Upload to B2 storage                  Upload to B2 storage
  Create page (status: pending)         Create page (status: PENDING_QUOTA)
  Enqueue in sync_queue                 Skip OCR, skip sync queue
  Return 200 OK                         Return 402 Payment Required
  ↓                                     ↓
Agent displays "syncing..."           Agent displays "quota exceeded"
  ↓
Background worker picks up
  ↓
Perform OCR (Claude API)
  ↓
Consume quota: quota_service.consume_quota(user_id, 'ocr_pages', num_pages)
  ↓
Update page (status: completed)
  ↓
Queue for Notion sync (if enabled)
```

**Key Design Decisions:**
- Quota checked BEFORE upload (fail fast)
- Quota consumed AFTER successful OCR (not before)
- Graceful degradation: uploads accepted when quota exhausted, OCR deferred
- Pages with PENDING_QUOTA status show "OCR Pending" in dashboard
- Retroactive processing when quota resets (newest pages first)

### 2. Initial Sync Flow (Two-Phase Process)

```
User connects Notion integration
  ↓
POST /api/integrations/notion/sync (with page_limit=50)
  ↓
PHASE 1: Create notebooks sequentially
  ↓
For each notebook (in order):
  Check if Notion page exists (query sync_records)
  ↓ (if not exists)
  Create Notion page with database
  Store in sync_records (notebook_uuid → notion_page_id)
  ↓
PHASE 2: Queue pages for background processing
  ↓
Batch insert into sync_queue:
  - item_type: NOTEBOOK
  - status: queued
  - priority: based on last_modified
  ↓
Mark all as 'processing' BEFORE loop starts
  ↓
Return 200 OK to user
  ↓
Background worker processes sync_queue:
  - Row-level locking: FOR UPDATE SKIP LOCKED
  - Prevents duplicate processing across workers
  - Processes notebooks one by one
```

**Why Sequential Notebook Creation?**
- Prevents duplicate Notion pages (race condition with parallel creates)
- Establishes parent-child hierarchy correctly
- Fast enough (~100-200ms per notebook)

**Why Batch Status Update?**
- Prevents "check-then-set" race condition
- Multiple workers can safely process different items
- Database-level coordination via status flags

### 3. Notion Sync Flow (Database-Driven Deduplication)

```
Background worker polls sync_queue (every 5 seconds)
  ↓
SELECT with FOR UPDATE SKIP LOCKED (row-level lock)
  ↓
For each sync_queue item:
  Query sync_records by page_uuid (NOT content_hash)
  ↓
  If sync_records exists (page already synced):
    Check if content changed (compare content_hash)
    ↓
    If changed:                    If unchanged:
      Update Notion block            Skip (already up-to-date)
      Update sync_records hash       Mark queue item complete
  ↓
  If NOT in sync_records (new page):
    Create Notion block in database
    Insert into sync_records:
      - page_uuid (reMarkable's unique ID)
      - external_id (Notion block ID)
      - content_hash (for change detection)
      - target_name: 'notion'
  ↓
Mark queue item as complete
  ↓
Close SQLAlchemy session (in finally block)
```

**Database is Source of Truth:**
- `sync_records` table tracks all synced pages
- Uses `page_uuid` for deduplication (NOT `content_hash`)
- UNIQUE constraint on (page_uuid, target_name, user_id)
- Clean Notion titles without content hashes

**Handling Archived Blocks:**
- Catch "Can't edit block that is archived" error
- Treat as deleted, remove from sync_records
- Next sync will recreate if page still exists

## Database Schema

### Multi-Tenancy

All tables include `user_id` for data isolation. Application-level enforcement in FastAPI middleware.

**Production**: PostgreSQL 15 on Hetzner VPS
**Development**: SQLite (backend/rmirror.db)

### Key Tables

**users**
- Primary authentication (Clerk integration)
- Fields: `id`, `clerk_id` (unique), `email`, `created_at`

**subscriptions**
- Subscription tier and billing period
- Fields: `user_id`, `tier` (free/pro/enterprise), `status`, `current_period_start`, `current_period_end`, `stripe_customer_id` (nullable, Phase 2)
- Constraints: UNIQUE on `user_id` (one subscription per user)

**quota_usage**
- OCR page quota tracking
- Fields: `user_id`, `quota_type` ('ocr_pages'), `limit` (30 for free), `used`, `reset_at`, `period_start`
- Index: Composite on (`user_id`, `quota_type`) for fast lookups
- Free tier: 30 pages/month, resets on billing cycle anniversary

**notebooks**
- reMarkable notebooks/folders
- Fields: `id`, `user_id`, `notebook_uuid` (unique), `visible_name`, `parent_uuid` (folder hierarchy), `document_type`, `metadata`

**pages**
- Individual pages with OCR status
- Fields: `id`, `notebook_id`, `page_uuid` (unique), `page_number`, `content_hash`, `pdf_s3_key`, `ocr_text`, `ocr_status` (pending/completed/failed/pending_quota), `ocr_confidence`
- Key field: `page_uuid` is reMarkable's unique identifier (used for deduplication)

**sync_queue**
- Background processing queue
- Fields: `id`, `user_id`, `item_type` (NOTEBOOK/NOTEBOOK_METADATA), `item_id`, `content_hash`, `status` (queued/processing/completed/failed), `priority`, `created_at`
- Item types:
  - `NOTEBOOK`: Full content sync with OCR (~5s per page)
  - `NOTEBOOK_METADATA`: Property-only sync (~100ms, 50-100x faster)

**sync_records**
- Deduplication tracking (source of truth)
- Fields: `id`, `user_id`, `page_uuid` (reMarkable's unique ID), `external_id` (Notion block ID), `content_hash`, `target_name` ('notion'/'readwise'), `synced_at`
- Constraints: UNIQUE on (`page_uuid`, `target_name`, `user_id`) - prevents duplicates
- Tracks both page content blocks and notebook page IDs

**integration_configs**
- Connected service credentials
- Fields: `id`, `user_id`, `service_name` ('notion'), `credentials_encrypted` (AES-256), `settings` (JSON), `enabled`

### Indexing Strategy

```sql
-- Most common queries
CREATE INDEX idx_pages_notebook ON pages(notebook_id);
CREATE INDEX idx_pages_uuid ON pages(page_uuid);
CREATE INDEX idx_pages_status ON pages(ocr_status) WHERE ocr_status IN ('pending', 'pending_quota');

-- Sync queue processing
CREATE INDEX idx_sync_queue_status ON sync_queue(status, priority, created_at)
  WHERE status = 'queued';
CREATE INDEX idx_sync_queue_user ON sync_queue(user_id, status);

-- Deduplication lookups
CREATE UNIQUE INDEX idx_sync_records_dedup ON sync_records(page_uuid, target_name, user_id);
CREATE INDEX idx_sync_records_user ON sync_records(user_id, target_name);

-- Quota lookups
CREATE INDEX idx_quota_user_type ON quota_usage(user_id, quota_type);

-- Full-text search (future)
CREATE INDEX idx_pages_text_search ON pages USING gin(to_tsvector('english', ocr_text));
```

## Authentication & Security

### Agent Authentication (Long-Lived Tokens)

```
Dashboard → Clerk OAuth login
  ↓
User clicks "Download Agent" in dashboard
  ↓
POST /api/auth/agent-token
  Headers: Authorization: Bearer <clerk_session_token>
  ↓
Backend:
  1. Verify Clerk session token
  2. Extract user_id from Clerk claims
  3. Generate 30-day JWT with user_id
  4. Return long-lived JWT to dashboard
  ↓
Dashboard displays token to user
  ↓
User copies token into agent configuration
  ↓
Agent → API: POST /api/upload/files
  Headers: Authorization: Bearer <30_day_jwt>
  ↓
Backend:
  1. Verify JWT signature
  2. Extract user_id from JWT claims
  3. Set user_id in request context
  4. All queries filtered by user_id
```

**Why 30-day tokens?**
- Avoids frequent re-authentication for background agent
- Secure enough for single-user desktop app
- Stored in system keychain (macOS keyring)

### Dashboard Authentication

```
Dashboard → Clerk OAuth (Google/GitHub/Email)
  ↓
Clerk returns session token (short-lived)
  ↓
Dashboard → API: All requests include Clerk session
  Headers: Authorization: Bearer <clerk_session_token>
  ↓
Backend:
  1. Verify session with Clerk API
  2. Extract user_id from Clerk claims
  3. Set user_id in request context
```

### Rate Limiting (Multi-Layer)

**nginx (Infrastructure Protection)**:
- DDoS protection
- Connection limits per IP
- Prevents infrastructure overload

**FastAPI Middleware (User-Aware)**:
- Authenticated users: 300 requests/minute
- Anonymous users: 30 requests/minute
- Auth endpoints (/auth/*): 10 requests/minute
- Based on user_id (authenticated) or IP (anonymous)

**Quota System (Resource Consumption)**:
- OCR pages: 30/month (free tier)
- Enforced before OCR processing
- 402 Payment Required when exhausted

### Security Measures

- **TLS 1.3** for all connections (nginx → Cloudflare)
- **AES-256** encryption at rest for integration credentials
- **JWT signature verification** for all authenticated requests
- **SQL injection**: SQLAlchemy ORM prevents this
- **XSS**: React auto-escapes output (Next.js)
- **CSRF**: SameSite cookies + CORS configuration
- **Clerk OAuth**: Industry-standard authentication provider

## Scaling Strategy

### Phase 1: 1-100 Users (Current - January 2026)
- **Setup**: Single Hetzner VPS (4GB RAM), PostgreSQL on same host
- **Workers**: uvicorn --workers 2 (multiple background workers)
- **Storage**: Backblaze B2 (S3-compatible)
- **Cost**: ~$20/month (Hetzner) + ~$10/month (B2) = ~$30/month
- **Sufficient for**: Initial launch and beta testing

### Phase 2: 100-1000 Users
- **Setup**: Separate database server (Hetzner or managed PostgreSQL)
- **Add**: Redis for rate limiting and caching
- **Scale**: Increase to --workers 4, upgrade to 8GB RAM VPS
- **Cost**: ~$100-150/month
- **Optimization**:
  - Database connection pooling (pgbouncer)
  - Metadata-only syncs (50-100x faster)
  - Aggressive caching of Notion API responses

### Phase 3: 1000-5000 Users
- **Setup**: Add load balancer, scale to 2-3 VPS instances
- **Add**: Read replica for PostgreSQL
- **Add**: Dedicated worker instances (separate from API servers)
- **Optimization**:
  - Batch Claude API requests (multiple pages per call)
  - CDN for static assets and PDFs
  - Database query optimization and indexing
- **Cost**: ~$300-500/month

### Phase 4: 5000+ Users
- **Setup**: Kubernetes on Hetzner Cloud or migrate to AWS/GCP
- **Add**: Horizontal pod autoscaling, Elasticsearch for search
- **Add**: Multi-region deployment (EU + US)
- **Optimization**:
  - Read replicas per region
  - CDN edge caching (Cloudflare)
  - Dedicated Claude API rate limits
  - Database sharding (if needed)
- **Cost**: ~$1000-2000+/month

## Performance Targets

| Metric | Target | Current (Jan 2026) | Monitoring |
|--------|--------|-------------------|------------|
| API Response (p95) | < 200ms | ~150ms | Better Stack logs |
| OCR Processing | < 30s/page | ~10-15s/page | Custom metrics |
| Metadata Sync | < 200ms | ~100ms | Background worker logs |
| Full Notebook Sync | < 10s | ~5s/page | Background worker logs |
| File Upload | < 5s for 10MB | ~2-3s | Better Stack |
| Dashboard Load | < 2s | ~1.5s | Vercel Analytics |
| Initial Sync (50 pages) | < 5min | ~3-4min | Background worker |
| Uptime | > 99.9% | 99.5% | systemd + Better Stack |

## Monitoring & Observability

### Error Tracking (Current Setup)
- **Better Stack**: Log aggregation from systemd journal
- **Application logs**: Structured JSON logging to stdout
- **Database**: PostgreSQL logs for slow queries
- **Future**: Sentry for exception tracking and performance monitoring

### Metrics
- **systemd**: Service health and uptime
- **PostgreSQL**: Connection pool stats, query performance
- **Background worker**: Queue depth, processing time
- **Future**: Prometheus for custom metrics, Posthog for user analytics

### Alerts (via Better Stack)
- API error rate > 1%
- Sync queue depth > 100 items
- Database connections > 80%
- Disk usage > 85%
- Response time p95 > 500ms
- systemd service restart (backend crash)

## Disaster Recovery

### Backups (Current)
- **PostgreSQL**: Automated daily backups via pg_dump (30-day retention)
- **Backblaze B2**: Object versioning enabled, lifecycle rules (90-day retention)
- **Application**: GitHub repository + systemd service files
- **Secrets**: Stored in .env file (backed up manually to secure location)

### Recovery Procedures
1. Database restore from pg_dump: < 1 hour
2. Application redeploy from GitHub: < 5 minutes
3. Full system restore (new VPS): < 2 hours
4. B2 bucket recreation: < 30 minutes

### RPO/RTO Targets (Current)
- **RPO** (Recovery Point Objective): 24 hours (daily backups)
- **RTO** (Recovery Time Objective): 2 hours (manual restore from backups)
- **Future**: Implement WAL archiving for PostgreSQL (RPO < 1 hour)

## Cost Optimization

### Storage Lifecycle (Current)
- **B2 Lifecycle Rules**: Auto-delete files after 90 days
- **OCR Text**: Stored in PostgreSQL (minimal cost)
- **Future**: Optional .rm file deletion after OCR completion (user configurable)

### API Cost Reduction (Implemented)
- **Content-based deduplication**: page_uuid prevents re-processing same page
- **Metadata-only syncs**: 50-100x faster, no OCR needed for property updates
- **Quota enforcement**: Prevents runaway OCR costs (30 pages/month free)
- **Future**: Batch processing (multiple pages in one Claude API call)

### Infrastructure (Current)
- **Hetzner VPS**: ~60% cheaper than AWS/DigitalOcean
- **Backblaze B2**: ~25% of AWS S3 cost
- **Vercel**: Free tier for dashboard (Next.js)
- **Cloudflare**: Free tier for CDN and DDoS protection
- **Total**: ~$30/month (vs ~$100+ on AWS)

## Technology Decisions

### Why FastAPI?
- Async/await for concurrent processing
- Automatic validation & documentation
- **Reuses existing Python processing code**

### Why PostgreSQL (Production) / SQLite (Dev)?
- **PostgreSQL**: JSONB support, proven reliability, great performance
- **SQLite**: Zero-setup local development, perfect for testing
- **Application-level multi-tenancy**: No need for row-level security (RLS)
- **Schema compatibility**: SQLAlchemy ORM works with both

### Why Python for Mac Agent?
- **Same stack as backend**: Shared reMarkable parsing libraries
- **rumps library**: Native macOS menu bar integration
- **watchdog**: Robust file system monitoring
- **Flask**: Simple web UI (localhost:9090)
- **Fast iteration**: Python allows rapid development and testing
- **Future**: Consider Electron or Tauri for cross-platform support

### Why Database-Driven Background Worker (No Redis)?
- **Simplicity**: One less service to manage (no Redis setup)
- **Reliability**: PostgreSQL provides ACID guarantees
- **Cost**: No additional infrastructure needed
- **Sufficient for <1000 users**: Database polling every 5 seconds is fast enough
- **Row-level locking**: FOR UPDATE SKIP LOCKED prevents duplicate processing
- **When to migrate**: If queue depth consistently > 1000, consider Redis/Celery

### Why Clerk for Authentication?
- **Industry standard**: OAuth, magic links, 2FA out of the box
- **Developer-friendly**: Excellent Next.js integration
- **Secure**: JWT verification built-in
- **Cost-effective**: Free tier covers initial users
- **Agent tokens**: Custom 30-day JWT for background agent

### Why Backblaze B2 over AWS S3?
- **Cost**: ~75% cheaper than S3 ($5/TB vs $20+/TB)
- **S3-compatible API**: Easy migration to S3 if needed
- **Reliable**: 99.9% uptime SLA
- **No egress fees**: Free downloads (unlike S3)

## Key Architectural Achievements (January 2026)

### Quota System Phase 1 ✅
- Free tier: 30 OCR pages/month
- Graceful degradation: Accept uploads when quota exhausted, defer OCR
- Email notifications: 90% warning, 100% exceeded
- Retroactive processing: Process PENDING_QUOTA pages when quota resets (newest first)
- Dashboard quota UI with upgrade CTAs
- Agent quota display with color-coded status

### Two-Phase Initial Sync ✅
- Phase 1: Sequential notebook creation (prevents duplicates)
- Phase 2: Background page processing with row-level locking
- Batch status update before processing loop (prevents race conditions)
- Supports page_limit parameter (default 50 pages for initial sync)

### Metadata-Only Sync ✅
- NOTEBOOK_METADATA item type (separate from NOTEBOOK)
- Updates only Notion properties (not content blocks)
- 50-100x faster than full sync (~100ms vs ~5s)
- Triggered when .metadata file changes (without .rm changes)

### Database-Driven Deduplication ✅
- sync_records table is source of truth
- Uses page_uuid (reMarkable's unique ID) for deduplication
- Clean Notion titles without content hashes
- Handles archived blocks gracefully
- UNIQUE constraint prevents duplicates: (page_uuid, target_name, user_id)

### Production Deployment ✅
- Hetzner VPS with systemd service management
- GitHub Actions CI/CD pipeline
- PostgreSQL for production, SQLite for development
- Backblaze B2 for file storage
- Cloudflare CDN and DDoS protection
- Vercel hosting for Next.js dashboard

---

**Document Status**: Living document, updated as architecture evolves
**Last Updated**: 2026-01-21
**Version**: 1.0.0 (reflects production architecture as of January 2026)
