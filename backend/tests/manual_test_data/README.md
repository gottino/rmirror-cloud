# Manual Testing Scripts for Quota System

This directory contains scripts and SQL files for manual testing of the quota system according to the test plan in `dev-context/testing/quota-system-test-plan.md`.

## Overview

These scripts help you:
- Set up test users in different quota states
- Create pending pages for retroactive processing tests
- Test quota reset and processing workflows
- Verify UI/UX behavior across different scenarios

## Prerequisites

1. **Development environment running:**
   ```bash
   # Backend
   cd backend
   poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

   # Dashboard (separate terminal)
   cd dashboard
   npm run dev

   # Agent (separate terminal, if testing agent)
   cd agent
   poetry run python -m app.main --foreground --debug
   ```

2. **Test user created:**
   - Sign up a test user at http://localhost:3000
   - Note the email address (e.g., `test@example.com`)

3. **Database access:**
   ```bash
   # PostgreSQL
   psql $DATABASE_URL

   # Or use GUI tool (pgAdmin, TablePlus, etc.)
   ```

## Scripts

### 1. SQL Scripts (`01_set_quota_states.sql`)

**Purpose:** Set user quota to specific states for UI testing.

**Usage:**
```bash
psql $DATABASE_URL -f tests/manual_test_data/01_set_quota_states.sql
```

**Manual execution:**
```sql
-- Connect to database
psql $DATABASE_URL

-- Copy and paste relevant scenario from 01_set_quota_states.sql
-- Example: Set to 90% (warning threshold)
UPDATE quota_usage
SET used = 27, limit = 30
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- Verify
SELECT u.email, q.used, q.limit
FROM users u
JOIN quota_usage q ON u.id = q.user_id
WHERE u.email = 'test@example.com';
```

**Available scenarios:**
- Fresh user (0/30) - new signup state
- Low usage (5/30, 17%) - green status
- Medium usage (20/30, 67%) - still green
- Warning zone (25/30, 83%) - yellow warning
- High warning (27/30, 90%) - email trigger
- Near limit (28/30, 93%) - red status
- Exhausted (30/30, 100%) - quota exceeded
- Pro tier (150/500) - higher limits
- Enterprise (unlimited) - no limits

### 2. Create Pending Pages (`create_pending_pages.py`)

**Purpose:** Create PENDING_QUOTA pages for testing retroactive processing and hard cap.

**Usage:**
```bash
# Create 20 pending pages
poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 20

# Create 100 pending pages (hard cap test)
poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 100

# Create 50 pending pages (retroactive processing test)
poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 50
```

**What it does:**
- Creates a test notebook for the user
- Creates N pages with `ocr_status = PENDING_QUOTA`
- Staggers timestamps (oldest to newest)
- Sets required `pdf_s3_key` for processing

**Example output:**
```
📧 Found user: test@example.com (ID: 42)
📓 Created test notebook: Pending Pages Test (20 pages) (ID: 123)

📄 Creating 20 pending pages...
  ✅ Created page 1/20 (created_at: 2025-12-17)
  ✅ Created page 2/20 (created_at: 2025-12-18)
  ...
  💾 Committed batch (10/20)
  ...

✅ Success!
   Total pending pages: 20
   New pages created: 20
   Notebook ID: 123
```

### 3. Reset Quota and Process (`reset_quota_and_process.py`)

**Purpose:** Reset quota and trigger retroactive OCR processing.

**Usage:**
```bash
poetry run python tests/manual_test_data/reset_quota_and_process.py test@example.com
```

**What it does:**
1. Shows current quota status
2. Counts pending pages
3. Resets quota to 0/30 (new billing period)
4. Triggers retroactive processing job
5. Processes newest pages first (up to quota limit)
6. Reports results

**Example output:**
```
📧 Found user: test@example.com (ID: 42)

📊 Current quota status:
   Used: 30/30 (100.0%)
   Period: 2026-01-01 to 2026-01-31
   Pending pages: 50

🔄 Resetting quota...
   ✅ Quota reset to 0/30
   New period: 2026-01-06 to 2026-02-05

🔄 Starting retroactive OCR processing...
   Processing up to 30 pages (newest first)

✅ Retroactive processing complete!
   Pages processed: 30
   Quota used: 30/30
   Still pending: 20
   Total completed: 30

📝 Note: 20 pages still pending
   (Quota exhausted after processing 30 pages)

🔍 Newest processed pages:
   1. Page pending-page-... (created: 2026-01-06, processed: 14:23:10)
   2. Page pending-page-... (created: 2026-01-05, processed: 14:23:11)
   ...
```

## Manual Test Workflows

### Workflow 1: End-to-End Quota Exhaustion Journey

**Objective:** Test complete user experience from warning to exhaustion (TC-MANUAL-01)

**Steps:**
1. **Setup:** Set quota to 28/30
   ```bash
   psql $DATABASE_URL
   ```
   ```sql
   UPDATE quota_usage SET used = 28, limit = 30
   WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');
   ```

2. **Verify dashboard:**
   - Open http://localhost:3000
   - Check quota badge shows "28 / 30 pages used" (YELLOW)
   - Verify warning banner visible

3. **Verify agent:**
   - Open agent UI (http://localhost:9090 or check agent status)
   - Check quota shows "2/30 pages remaining" (yellow)

4. **Consume 1 page:** Upload via agent or simulate
   ```sql
   UPDATE quota_usage SET used = 29 WHERE user_id = ...;
   ```
   - Refresh dashboard → shows "29 / 30 pages used"
   - Check email inbox → "90% quota warning" email

5. **Consume final page:**
   ```sql
   UPDATE quota_usage SET used = 30 WHERE user_id = ...;
   ```
   - Refresh dashboard → shows "30 / 30 pages used" (RED)
   - Modal appears: "Free Tier Limit Reached"
   - Check email → "Quota exhausted" email

6. **Test graceful degradation:**
   - Create pending pages:
     ```bash
     poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 5
     ```
   - Refresh dashboard → pages show "OCR Pending" badge
   - Click page → PDF viewable, no OCR text

### Workflow 2: Dashboard Quota Display Validation

**Objective:** Test quota display states (TC-MANUAL-02)

**Test matrix:**
```bash
# Low usage (17%)
psql $DATABASE_URL -c "UPDATE quota_usage SET used = 5 WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');"
# → Dashboard: Green, no warning

# High usage (83%)
psql $DATABASE_URL -c "UPDATE quota_usage SET used = 25 WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');"
# → Dashboard: Yellow, warning banner shown

# Exhausted (100%)
psql $DATABASE_URL -c "UPDATE quota_usage SET used = 30 WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');"
# → Dashboard: Red, warning banner (red), modal
```

### Workflow 3: Retroactive Processing Test

**Objective:** Test pending page processing when quota resets (TC-MANUAL-05)

**Steps:**
1. **Setup:** Create 50 pending pages
   ```bash
   poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 50
   ```

2. **Set quota exhausted:**
   ```sql
   UPDATE quota_usage SET used = 30, limit = 30 WHERE user_id = ...;
   ```

3. **Verify dashboard:**
   - Should show 50 pages with "OCR Pending" badge

4. **Reset and process:**
   ```bash
   poetry run python tests/manual_test_data/reset_quota_and_process.py test@example.com
   ```

5. **Verify results:**
   - 30 newest pages should have OCR completed
   - 20 oldest pages still pending
   - Quota shows 30/30 used

6. **Check database:**
   ```sql
   SELECT
     ocr_status,
     COUNT(*) as count,
     MIN(created_at) as oldest,
     MAX(created_at) as newest
   FROM pages p
   JOIN notebooks n ON p.notebook_id = n.id
   WHERE n.user_id = (SELECT id FROM users WHERE email = 'test@example.com')
   GROUP BY ocr_status;
   ```

### Workflow 4: Hard Cap Testing

**Objective:** Test 100 pending pages limit (TC-MANUAL-06)

**Steps:**
1. **Create exactly 100 pending pages:**
   ```bash
   poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 100
   ```

2. **Set quota exhausted:**
   ```sql
   UPDATE quota_usage SET used = 30 WHERE user_id = ...;
   ```

3. **Try to upload 101st page:**
   - Via agent or API
   - Should get HTTP 429 error
   - Error message: "You have 100 pages pending OCR..."

4. **Verify database:**
   ```sql
   SELECT COUNT(*) FROM pages p
   JOIN notebooks n ON p.notebook_id = n.id
   WHERE n.user_id = (SELECT id FROM users WHERE email = 'test@example.com')
   AND p.ocr_status = 'pending_quota';
   -- Should be exactly 100
   ```

## Verification Queries

### Check Quota Status
```sql
SELECT
    u.email,
    s.tier,
    q.used || '/' || q.limit as quota,
    ROUND((q.used::float / q.limit) * 100, 1) as pct,
    q.reset_at
FROM users u
JOIN subscriptions s ON u.id = s.user_id
JOIN quota_usage q ON u.id = q.user_id
WHERE u.email = 'test@example.com';
```

### Check Pending Pages
```sql
SELECT
    p.page_uuid,
    p.ocr_status,
    p.created_at,
    n.visible_name as notebook
FROM pages p
JOIN notebooks n ON p.notebook_id = n.id
WHERE n.user_id = (SELECT id FROM users WHERE email = 'test@example.com')
AND p.ocr_status = 'pending_quota'
ORDER BY p.created_at DESC;
```

### Check Page Status Distribution
```sql
SELECT
    p.ocr_status,
    COUNT(*) as count
FROM pages p
JOIN notebooks n ON p.notebook_id = n.id
WHERE n.user_id = (SELECT id FROM users WHERE email = 'test@example.com')
GROUP BY p.ocr_status;
```

## Cleanup

### Reset Test User
```sql
-- Reset quota
UPDATE quota_usage
SET used = 0, period_start = NOW(), reset_at = NOW() + INTERVAL '30 days'
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- Delete test pages
DELETE FROM pages
WHERE notebook_id IN (
    SELECT id FROM notebooks
    WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com')
);

-- Delete test notebooks
DELETE FROM notebooks
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');
```

### Quick Reset Script
```bash
# Create a quick reset alias
alias reset-test-user="psql \$DATABASE_URL -c \"UPDATE quota_usage SET used = 0, period_start = NOW(), reset_at = NOW() + INTERVAL '30 days' WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');\""

# Use it
reset-test-user
```

## Troubleshooting

### Script won't run
```bash
# Make sure you're in the backend directory
cd backend

# Check Python environment
poetry env info

# Install dependencies if needed
poetry install

# Run with full poetry command
poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 20
```

### Database connection error
```bash
# Check DATABASE_URL environment variable
echo $DATABASE_URL

# Or use .env file
export DATABASE_URL="postgresql://localhost/rmirror_dev"

# Test connection
psql $DATABASE_URL -c "SELECT current_database();"
```

### User not found
```bash
# List available users
psql $DATABASE_URL -c "SELECT id, email, full_name FROM users LIMIT 10;"

# Create test user if needed (via dashboard signup)
# Then run scripts with correct email
```

## Tips

1. **Test in sequence:** Follow the test plan order (TC-MANUAL-01 through TC-MANUAL-07)

2. **Reset between tests:** Use cleanup SQL to reset state

3. **Check both UI and database:** Verify UI matches database state

4. **Test emails:** Configure email service or check logs for email triggers

5. **Document issues:** Screenshot any UI bugs, note database inconsistencies

6. **Use multiple browsers:** Test quota display across Chrome, Firefox, Safari

## Related Files

- **Test Plan:** `dev-context/testing/quota-system-test-plan.md`
- **Quota Concept:** `dev-context/concepts/free-trial-quota-plan.md`
- **Automated Tests:** `backend/tests/test_quota_service.py`, `backend/tests/test_quota_integration.py`

## Support

If you encounter issues with these scripts:
1. Check the troubleshooting section above
2. Verify your development environment is running
3. Check database connection and credentials
4. Review test plan for expected behavior
