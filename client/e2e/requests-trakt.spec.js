const { test, expect } = require('@playwright/test');
const { mockSuggestarrBoot } = require('./helpers/mockApi');

test.describe('Requests page Trakt controls', () => {
  test.beforeEach(async ({ page }) => {
    await mockSuggestarrBoot(page);
    await page.goto('/requests?skipSetup=1');
    await expect(page.getByRole('heading', { name: 'Request History' })).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId('request-poster-card').first()).toBeVisible({ timeout: 20000 });
  });

  test('all-requests modal shows Trakt strip with fallback user id', async ({ page }) => {
    await page.getByTestId('request-poster-card').first().click();
    const strip = page.getByTestId('trakt-action-strip');
    await expect(strip).toBeVisible();
    await expect(strip.getByTestId('trakt-mark-watched')).toBeVisible();
    await expect(strip.getByTestId('trakt-points-select')).toBeVisible();
    await expect(strip).toContainText('Unwatched');
  });

  test('grouped by-content modal shows inline Trakt actions for each request', async ({ page }) => {
    await page.getByRole('button', { name: /By Watched Content/i }).click();
    await page.locator('.card-header').first().click();
    await expect(page.getByTestId('trakt-inline-actions')).toHaveCount(2);
    await expect(page.getByTestId('trakt-inline-mark-watched').first()).toBeVisible();
  });

  test('mark watched button updates Trakt state label', async ({ page }) => {
    await page.getByTestId('request-poster-card').first().click();
    const strip = page.getByTestId('trakt-action-strip');
    await strip.getByTestId('trakt-mark-watched').click();
    await expect(strip).toContainText('Watched');
  });
});
