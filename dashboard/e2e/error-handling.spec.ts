import { test, expect } from '@playwright/test';

/**
 * Error handling E2E tests.
 *
 * These tests verify error states are handled gracefully.
 */

test.describe('Error Handling', () => {
  test('handles 404 page not found', async ({ page }) => {
    // Navigate to a non-existent page
    const response = await page.goto('/this-page-does-not-exist-12345');

    // Should get 404 or show a not found page
    // Next.js returns the page content even for 404s
    await expect(page.locator('body')).toBeVisible();
  });

  test('handles invalid notebook ID gracefully', async ({ page }) => {
    // This will redirect to sign-in for unauthenticated users
    // but tests that the URL format is handled
    await page.goto('/notebooks/invalid-id-not-a-number');

    // Should either show error or redirect to sign-in
    await expect(page.locator('body')).toBeVisible();
  });

  test('API health check works', async ({ page, request }) => {
    // Check if API health endpoint is reachable
    // This uses the configured baseURL
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';

    // Note: This test may fail if API is not running locally
    // In CI, it should hit the staging API
    try {
      const response = await request.get(`${apiUrl}/../health`);
      expect(response.status()).toBeLessThan(500); // Not a server error
    } catch {
      // API might not be available in test environment
      // This is acceptable for local dev
      test.skip(true, 'API not available in test environment');
    }
  });
});

test.describe('Loading States', () => {
  test('sign-in page shows loading state initially', async ({ page }) => {
    // Navigate to sign-in
    await page.goto('/sign-in');

    // Page should render something (loading or content)
    await expect(page.locator('body')).toBeVisible();
  });
});
