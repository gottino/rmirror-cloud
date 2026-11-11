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
   - Run: `cd backend && poetry run python -c "from app.database import SessionLocal; from app.services import quota_service; db = SessionLocal(); print(quota_service.get_quota_status(db, 1)); db.close()"`
   - Report: used/limit, percentage, is_exhausted

3. **Test quota consumption**
   - Create test script to consume 1 page
   - Verify quota increments

4. **Test quota exhaustion**
   - If quota not exhausted, consume remaining quota
   - Upload a page with exhausted quota and call `GET /v1/quota/status`
   - Verify: `is_exhausted` is true; notebook export (`GET /v1/notebooks/{id}/export`) returns HTTP 402 with quota details

5. **Test graceful degradation**
   - Upload page with exhausted quota
   - Verify: Upload accepted (no 402) and page created with PENDING_QUOTA status
   - Verify: PDF generated, OCR skipped (after 100 pending pages uploads get HTTP 429)

6. **Check integration blocking**
   - Verify integration syncs blocked when quota exhausted (including `/processing/metadata/update`)

7. **Check retroactive OCR**
   - Reset the quota (`quota_service.reset_quota`) and watch the backend log: the sync worker OCRs `PENDING_QUOTA` pages, newest first, a few per poll

## Report

Provide summary:
- Current quota: X/Y pages
- Tests passed/failed
- Any issues found
