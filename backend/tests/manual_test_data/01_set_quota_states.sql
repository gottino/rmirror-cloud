-- =============================================================================
-- SQL Scripts for Manual Testing: Set User Quota States
-- =============================================================================
--
-- Purpose: Set specific quota states for testing different UI/UX scenarios
-- Usage: Replace 'test@example.com' with your test user email
--
-- IMPORTANT: These scripts modify the database directly. Use only in
-- development/testing environments!
-- =============================================================================

-- Check current quota status first
SELECT
    u.email,
    u.full_name,
    s.tier,
    q.used,
    q.limit,
    q.reset_at,
    ROUND((q.used::float / q.limit) * 100, 1) as percentage_used
FROM users u
JOIN subscriptions s ON u.id = s.user_id
JOIN quota_usage q ON u.id = q.user_id
WHERE u.email = 'test@example.com';

-- =============================================================================
-- SCENARIO 1: Fresh User (New Signup)
-- =============================================================================
-- Usage: 0/30 quota, free tier
-- Testing: Initial state, onboarding flow

UPDATE quota_usage
SET
    used = 0,
    limit = 30,
    period_start = NOW(),
    reset_at = NOW() + INTERVAL '30 days',
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- Verify
SELECT
    u.email,
    q.used || '/' || q.limit as quota,
    q.reset_at
FROM users u
JOIN quota_usage q ON u.id = q.user_id
WHERE u.email = 'test@example.com';

-- =============================================================================
-- SCENARIO 2: Low Usage (17%)
-- =============================================================================
-- Usage: 5/30 quota
-- Testing: Green status indicator, normal operation

UPDATE quota_usage
SET
    used = 5,
    limit = 30,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- =============================================================================
-- SCENARIO 3: Medium Usage (67%)
-- =============================================================================
-- Usage: 20/30 quota
-- Testing: Still green, approaching warning threshold

UPDATE quota_usage
SET
    used = 20,
    limit = 30,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- =============================================================================
-- SCENARIO 4: Warning Zone (83%)
-- =============================================================================
-- Usage: 25/30 quota
-- Testing: Yellow warning badge, warning banner displayed

UPDATE quota_usage
SET
    used = 25,
    limit = 30,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- =============================================================================
-- SCENARIO 5: High Warning (90%)
-- =============================================================================
-- Usage: 27/30 quota
-- Testing: Email trigger threshold, strong warning UI

UPDATE quota_usage
SET
    used = 27,
    limit = 30,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- =============================================================================
-- SCENARIO 6: Near Limit (93%)
-- =============================================================================
-- Usage: 28/30 quota
-- Testing: Red status, urgent messaging

UPDATE quota_usage
SET
    used = 28,
    limit = 30,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- =============================================================================
-- SCENARIO 7: Quota Exhausted (100%)
-- =============================================================================
-- Usage: 30/30 quota
-- Testing: Modal display, graceful degradation, upgrade CTAs

UPDATE quota_usage
SET
    used = 30,
    limit = 30,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- =============================================================================
-- SCENARIO 8: Quota Exhausted + Pending Pages
-- =============================================================================
-- Usage: 30/30 quota + pages awaiting processing
-- Testing: Retroactive processing, pending page display

-- First, set quota exhausted
UPDATE quota_usage
SET
    used = 30,
    limit = 30,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- Note: Use Python script (create_pending_pages.py) to create pending pages
-- SQL creation is complex due to foreign key dependencies

-- =============================================================================
-- SCENARIO 9: Pro Tier User
-- =============================================================================
-- Usage: 150/500 quota, Pro tier
-- Testing: Pro tier display, higher limits

-- Upgrade subscription tier
UPDATE subscriptions
SET
    tier = 'pro',
    status = 'active',
    current_period_start = NOW(),
    current_period_end = NOW() + INTERVAL '30 days',
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- Update quota limit
UPDATE quota_usage
SET
    used = 150,
    limit = 500,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- =============================================================================
-- SCENARIO 10: Enterprise Tier (Unlimited)
-- =============================================================================
-- Usage: Unlimited quota
-- Testing: Unlimited quota display, no warnings

-- Upgrade to enterprise
UPDATE subscriptions
SET
    tier = 'enterprise',
    status = 'active',
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- Set unlimited quota (limit = -1)
UPDATE quota_usage
SET
    used = 500,  -- Used is tracked but not enforced
    limit = -1,  -- -1 = unlimited
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- =============================================================================
-- RESET TO FREE TIER
-- =============================================================================
-- Return user to free tier for continued testing

UPDATE subscriptions
SET
    tier = 'free',
    status = 'active',
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

UPDATE quota_usage
SET
    used = 0,
    limit = 30,
    period_start = NOW(),
    reset_at = NOW() + INTERVAL '30 days',
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');

-- =============================================================================
-- BULK QUOTA CHECK
-- =============================================================================
-- Check quota status for all users (useful for multi-user testing)

SELECT
    u.email,
    u.full_name,
    s.tier,
    q.used || '/' || q.limit as quota,
    ROUND((q.used::float / NULLIF(q.limit, 0)) * 100, 1) as pct,
    CASE
        WHEN q.limit = -1 THEN 'unlimited'
        WHEN q.used >= q.limit THEN 'exhausted'
        WHEN (q.used::float / q.limit) >= 0.90 THEN 'high'
        WHEN (q.used::float / q.limit) >= 0.80 THEN 'warning'
        ELSE 'ok'
    END as status,
    q.reset_at
FROM users u
JOIN subscriptions s ON u.id = s.user_id
JOIN quota_usage q ON u.id = q.user_id
ORDER BY u.email;

-- =============================================================================
-- CLEANUP
-- =============================================================================
-- Delete test users and their data (use with caution!)

-- Delete pages for test users
DELETE FROM pages
WHERE notebook_id IN (
    SELECT id FROM notebooks
    WHERE user_id IN (
        SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com'
    )
);

-- Delete notebooks for test users
DELETE FROM notebooks
WHERE user_id IN (
    SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com'
);

-- Reset quota for test users
UPDATE quota_usage
SET
    used = 0,
    period_start = NOW(),
    reset_at = NOW() + INTERVAL '30 days',
    updated_at = NOW()
WHERE user_id IN (
    SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com'
);

-- Verify cleanup
SELECT
    u.email,
    (SELECT COUNT(*) FROM notebooks WHERE user_id = u.id) as notebooks,
    (SELECT COUNT(*) FROM pages p
     JOIN notebooks n ON p.notebook_id = n.id
     WHERE n.user_id = u.id) as pages,
    q.used as quota_used
FROM users u
JOIN quota_usage q ON u.id = q.user_id
WHERE u.email LIKE '%test%' OR u.email LIKE '%example.com';
