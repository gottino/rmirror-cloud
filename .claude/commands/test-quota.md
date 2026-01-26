# /test-quota

Test the quota system end-to-end.

## Usage

```
/test-quota
```

## Instructions

1. **Check backend is running**
   - Verify uvicorn is running on port 8000
   - If not: `cd backend && poetry run uvicorn app.main:app --reload`

2. **Query current quota status**
   - Run: `cd backend && poetry run python -c "from app.services.quota_service import QuotaService; from app.db.session import SessionLocal; db = SessionLocal(); qs = QuotaService(db); print(qs.get_quota_status(1, 'ocr_pages')); db.close()"`
   - Report: used/limit, percentage, is_exhausted

3. **Test quota consumption**
   - Create test script to consume 1 page
   - Verify quota increments

4. **Test quota exhaustion**
   - If quota not exhausted, consume remaining quota
   - Attempt OCR with exhausted quota
   - Verify: Returns HTTP 402, detailed error message

5. **Test graceful degradation**
   - Upload page with exhausted quota
   - Verify: Page created with PENDING_QUOTA status
   - Verify: PDF generated, OCR skipped

6. **Check integration blocking**
   - Verify integration syncs blocked when quota exhausted

## Report

Provide summary:
- Current quota: X/Y pages
- Tests passed/failed
- Any issues found
