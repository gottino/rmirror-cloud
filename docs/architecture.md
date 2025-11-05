# rMirror Cloud Architecture

## Overview

rMirror Cloud is a multi-tenant cloud service that syncs reMarkable tablet content, processes it with AI-powered OCR, and distributes it to connected services. The architecture is designed to scale from 100 to 10,000+ users.

## System Components

```
┌──────────────────────────────────────────────────────────────┐
│                      User's Device                            │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Tauri Desktop Agent                         │ │
│  │  • File system watcher (platform-specific)              │ │
│  │  • Change detection & deduplication (SHA-256)           │ │
│  │  • Upload queue with retry logic                        │ │
│  │  • API key authentication                               │ │
│  └─────────────────────────────────────────────────────────┘ │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS (TLS 1.3)
                         │ Gzipped payloads
                         ↓
┌──────────────────────────────────────────────────────────────┐
│                    Cloud Infrastructure                       │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │               API Gateway Layer                         │  │
│  │  ┌──────────────┐  ┌──────────────┐                   │  │
│  │  │  Cloudflare  │→ │ DigitalOcean │                   │  │
│  │  │  CDN + DDoS  │  │ Load Balancer│                   │  │
│  │  └──────────────┘  └──────┬───────┘                   │  │
│  └────────────────────────────┼──────────────────────────┘  │
│                                ↓                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │            FastAPI Application Servers                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │  │
│  │  │  Instance 1 │  │  Instance 2 │  │  Instance N │   │  │
│  │  │  (4GB RAM)  │  │  (4GB RAM)  │  │  (4GB RAM)  │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │  │
│  │  • Authentication & authorization                      │  │
│  │  • Rate limiting (per-user quotas)                     │  │
│  │  • File upload handling                                │  │
│  │  • Job queue management                                │  │
│  │  • API endpoints for dashboard                         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                ↓                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              Data Layer                                 │  │
│  │  ┌─────────────────┐  ┌──────────────┐                │  │
│  │  │  PostgreSQL 15  │  │    Redis     │                │  │
│  │  │  (Managed)      │  │  (Managed)   │                │  │
│  │  │                 │  │              │                │  │
│  │  │ • User accounts │  │ • Job queue  │                │  │
│  │  │ • Notebooks     │  │ • Rate limits│                │  │
│  │  │ • Pages         │  │ • Sessions   │                │  │
│  │  │ • Highlights    │  │ • Cache      │                │  │
│  │  │ • Sync records  │  │              │                │  │
│  │  └─────────────────┘  └──────────────┘                │  │
│  └────────────────────────────────────────────────────────┘  │
│                                ↓                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │           Processing Workers (RQ)                       │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │  │
│  │  │  OCR     │  │  Sync    │  │  Export  │            │  │
│  │  │  Worker  │  │  Worker  │  │  Worker  │            │  │
│  │  └──────────┘  └──────────┘  └──────────┘            │  │
│  │  • Pull jobs from Redis queue                          │  │
│  │  • Process with retry logic                            │  │
│  │  • Update database with results                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                ↓                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │         File Storage (S3-compatible)                    │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │  DigitalOcean Spaces / S3                       │   │  │
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
│  │ (OCR)        │  │   (Sync)     │  │   (Sync)     │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└────────────────────────────────────────────────────────────┘
                        ↑
                        │ Browser
                        │
┌────────────────────────────────────────────────────────────┐
│                  Web Dashboard (Next.js)                    │
│  • Hosted on Vercel (auto-scaling)                         │
│  • Server-side rendering for performance                   │
│  • API calls to FastAPI backend                            │
│  • Real-time updates via polling/WebSocket                 │
└────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. File Upload Flow

```
Agent detects .rm file change
  ↓
Calculate SHA-256 hash
  ↓
Check if already uploaded (local cache)
  ↓ (if new)
POST /api/upload/files
  ↓
Backend: Validate auth & quota
  ↓
Upload to Spaces storage
  ↓
Create page record (status: pending)
  ↓
Enqueue OCR job in Redis
  ↓
Return job_id to agent
  ↓
Agent displays "syncing..." status
```

### 2. OCR Processing Flow

```
OCR Worker pulls job from Redis queue
  ↓
Download .rm file from Spaces
  ↓
Convert .rm → PNG (using rmscene library)
  ↓
Send PNG to Claude Vision API
  ↓
Receive OCR text + confidence
  ↓
Update page record (status: completed)
  ↓
Trigger connector sync jobs (if configured)
  ↓
Mark job as complete
```

### 3. Connector Sync Flow

```
Sync Worker pulls job from Redis queue
  ↓
Fetch page/highlight data from database
  ↓
Check if already synced (sync_records table)
  ↓ (if not synced)
Call external API (Notion/Readwise)
  ↓
Store external ID in sync_records
  ↓
Mark job as complete
```

## Database Schema

### Multi-Tenancy

All tables use **row-level security** with `user_id` isolation:

```sql
-- Enable RLS
ALTER TABLE notebooks ENABLE ROW LEVEL SECURITY;

-- Policy: users can only access their own data
CREATE POLICY user_isolation ON notebooks
  FOR ALL
  USING (user_id = current_setting('app.user_id')::uuid);
```

### Key Tables

**users**
- Primary authentication and subscription tracking
- Fields: id, email, subscription_tier, api_key_hash, settings

**notebooks**
- Represents a reMarkable notebook/document
- Fields: id, user_id, notebook_uuid, visible_name, document_type, metadata

**pages**
- Individual pages with OCR status tracking
- Fields: id, notebook_id, page_number, file_hash, storage_path, ocr_status, ocr_text

**highlights**
- Extracted highlights from PDFs/EPUBs
- Fields: id, user_id, notebook_id, original_text, corrected_text, confidence

**sync_records**
- Tracks what's been synced to external services
- Fields: id, user_id, item_type, item_id, target_service, target_id, content_hash

**processing_jobs**
- Job queue state for async processing
- Fields: id, user_id, job_type, status, input_data, result_data, error_message

**connectors**
- User's connected service credentials
- Fields: id, user_id, service_name, credentials_encrypted, settings

### Indexing Strategy

```sql
-- Most common queries
CREATE INDEX idx_pages_notebook ON pages(notebook_id);
CREATE INDEX idx_pages_pending ON pages(ocr_status) WHERE ocr_status = 'pending';
CREATE INDEX idx_jobs_pending ON processing_jobs(status, created_at) WHERE status IN ('pending', 'processing');
CREATE INDEX idx_highlights_user_date ON highlights(user_id, created_at DESC);

-- Full-text search (future)
CREATE INDEX idx_pages_text_search ON pages USING gin(to_tsvector('english', ocr_text));
```

## Authentication & Security

### Agent Authentication

```
Agent → API: POST /api/auth/login
  Headers: Authorization: Bearer <api_key>

Backend:
  1. Hash provided API key
  2. Look up user by api_key_hash
  3. If found, set user_id in context
  4. All subsequent queries filtered by user_id
```

### Dashboard Authentication

```
Dashboard → Supabase Auth → API
  1. User logs in via Supabase (OAuth/email)
  2. Supabase returns JWT token
  3. Dashboard includes JWT in API requests
  4. Backend verifies JWT with Supabase
  5. Extract user_id from JWT claims
```

### Security Measures

- **TLS 1.3** for all connections
- **AES-256** encryption at rest for connector credentials
- **Rate limiting**: Per-user quotas enforced via Redis
- **SQL injection**: SQLAlchemy ORM prevents this
- **XSS**: React auto-escapes output
- **CSRF**: SameSite cookies + CORS configuration

## Scaling Strategy

### Phase 1: 1-100 Users
- **Setup**: Single FastAPI instance, managed DB/Redis
- **Cost**: ~$50/month
- **Sufficient for**: Beta testing and validation

### Phase 2: 100-1000 Users
- **Setup**: Add load balancer, scale to 2-3 app instances
- **Add**: Read replica for PostgreSQL
- **Cost**: ~$200-300/month
- **Optimization**: Aggressive caching in Redis

### Phase 3: 1000-5000 Users
- **Setup**: Move to Kubernetes (DOKS)
- **Add**: Horizontal pod autoscaling, CDN for files
- **Optimization**: Batch Claude API requests
- **Cost**: ~$500-1000/month

### Phase 4: 5000+ Users
- **Setup**: Multi-region deployment
- **Add**: Elasticsearch for search, dedicated Claude API limits
- **Optimization**: Read replicas per region, CDN edge caching
- **Cost**: ~$2000+/month

## Performance Targets

| Metric | Target | Monitoring |
|--------|--------|------------|
| API Response (p95) | < 200ms | Sentry Performance |
| OCR Processing | < 30s/page | Custom metrics |
| File Upload | < 5s for 10MB | CloudWatch/Better Stack |
| Dashboard Load | < 2s | Vercel Analytics |
| Uptime | > 99.9% | Better Stack + Status page |

## Monitoring & Observability

### Error Tracking
- **Sentry**: All exceptions, performance monitoring
- **Better Stack**: Log aggregation, alerting

### Metrics
- **Prometheus**: Custom metrics from FastAPI
- **Posthog**: User analytics, feature usage

### Alerts
- API error rate > 1%
- OCR worker queue depth > 100
- Database connections > 80%
- Disk usage > 85%
- Response time p95 > 500ms

## Disaster Recovery

### Backups
- **PostgreSQL**: Automated daily backups (30-day retention)
- **Spaces**: Versioning enabled, lifecycle rules
- **Application**: Immutable deployments via Docker

### Recovery Procedures
1. Database restore: < 1 hour
2. Application redeploy: < 5 minutes
3. Full system restore: < 2 hours

### RPO/RTO Targets
- **RPO** (Recovery Point Objective): 24 hours (daily backups)
- **RTO** (Recovery Time Objective): 2 hours (manual restore)

## Cost Optimization

### Storage Lifecycle
- Delete .rm files after OCR completion (optional)
- Archive old notebooks after 90 days
- Compress stored JSON/text data

### API Cost Reduction
- Content-based deduplication (never reprocess same file)
- Batch processing (multiple pages in one API call when possible)
- Fallback OCR for simple printed text (Tesseract = free)

### Infrastructure
- Reserved instances for predictable workloads
- Spot instances for worker nodes (80% discount)
- CDN caching reduces bandwidth costs

## Technology Decisions

### Why FastAPI?
- Async/await for concurrent processing
- Automatic validation & documentation
- **Reuses existing Python processing code**

### Why PostgreSQL?
- JSONB support for flexible schemas
- Row-level security for multi-tenancy
- Proven reliability at scale

### Why Tauri?
- 10MB installer (vs Electron's 100MB+)
- Native performance
- Cross-platform with shared codebase

### Why Redis + RQ?
- Simple Python integration
- Reliable job queue
- Sufficient for <10K users
- Migrate to Celery only if needed

---

**Document Status**: Living document, updated as architecture evolves
**Last Updated**: 2025-01-05
**Version**: 0.1.0
