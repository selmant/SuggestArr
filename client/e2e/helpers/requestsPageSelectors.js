/** DOM selectors for requests page stability tests (testid + CSS fallback). */

export const requestsPageSelectors = {
  testId: {
    loader: '[data-testid="requests-page-loader"]',
    loaderMessage: '[data-testid="requests-page-loader-message"]',
    grid: '[data-testid="requests-poster-grid"]',
    poster: '[data-testid="request-poster-card"]',
  },
  css: {
    loader: '.loading-initial',
    loaderMessage: '.loading-initial p',
    grid: '.requests-grid',
    poster: '.requests-grid .request-card',
  },
};

/**
 * @param {'testId'|'css'} mode
 * @returns {{ loader: string, loaderMessage: string, grid: string, poster: string }}
 */
export function getRequestsPageSelectors(mode = 'testId') {
  return requestsPageSelectors[mode];
}

/**
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<'testId'|'css'>}
 */
export async function detectRequestsPageSelectorMode(page) {
  const hasTestIds = await page.locator('[data-testid="requests-poster-grid"]').count();
  return hasTestIds > 0 ? 'testId' : 'css';
}
