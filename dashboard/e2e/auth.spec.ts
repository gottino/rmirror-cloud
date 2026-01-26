import { test, expect } from '@playwright/test';

/**
 * Authentication E2E tests.
 *
 * These tests verify the authentication flow works correctly.
 * Note: Full OAuth flows require test credentials or mocking.
 */

test.describe('Authentication', () => {
  test('redirects unauthenticated users to sign-in', async ({ page }) => {
    // Try to access protected dashboard route
    await page.goto('/dashboard');

    // Should redirect to sign-in
    await expect(page).toHaveURL(/sign-in/);
  });

  test('sign-in page loads correctly', async ({ page }) => {
    await page.goto('/sign-in');

    // Should show Clerk sign-in component
    await expect(page.locator('body')).toBeVisible();

    // Page should have sign-in elements (Clerk renders these)
    await expect(page).toHaveTitle(/rMirror|Sign In/i);
  });

  test('sign-up page loads correctly', async ({ page }) => {
    await page.goto('/sign-up');

    // Should show Clerk sign-up component
    await expect(page.locator('body')).toBeVisible();

    // Page should have sign-up elements
    await expect(page).toHaveTitle(/rMirror|Sign Up/i);
  });

  test('root redirects appropriately', async ({ page }) => {
    await page.goto('/');

    // Root should either show landing or redirect to sign-in/dashboard
    await expect(page.locator('body')).toBeVisible();
  });
});

test.describe('Protected Routes', () => {
  test('billing page requires authentication', async ({ page }) => {
    await page.goto('/billing');

    // Should redirect to sign-in
    await expect(page).toHaveURL(/sign-in/);
  });

  test('integrations page requires authentication', async ({ page }) => {
    await page.goto('/integrations');

    // Should redirect to sign-in
    await expect(page).toHaveURL(/sign-in/);
  });

  test('notebooks page requires authentication', async ({ page }) => {
    await page.goto('/notebooks/123');

    // Should redirect to sign-in
    await expect(page).toHaveURL(/sign-in/);
  });
});
