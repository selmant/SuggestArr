const { test, expect } = require('@playwright/test');
const { mockRequestsPageBoot, mockLiveSeerStatus } = require('./helpers/mockApi');
const {
  analyzeRequestsPageStability,
  analyzePostLoaderPosterStability,
  attachStabilityTimeline,
  sampleRequestsPageStability,
} = require('./helpers/pageStability');

const LOADED_REQUEST_COUNT = 24;

async function waitForRequestsGrid(page) {
  await expect(page.getByRole('heading', { name: 'Request History' })).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId('requests-page-loader')).toBeHidden({ timeout: 30000 });
  await expect(page.getByTestId('requests-poster-grid')).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId('request-poster-card')).toHaveCount(LOADED_REQUEST_COUNT, { timeout: 10000 });
}

async function openSeerStatusFilter(page) {
  await page.getByRole('button', { name: /All Seer Statuses/i }).click();
}

async function selectSeerStatusFilter(page, label) {
  await openSeerStatusFilter(page);
  await page.locator('.dropdown-item').filter({ hasText: label }).click();
}

test.describe('Requests page loading stability', () => {
  test.beforeEach(async ({ page }) => {
    await mockRequestsPageBoot(page, {
      requestCount: LOADED_REQUEST_COUNT,
      batchDelayMs: 500,
    });
  });

  test('initial load keeps loader and poster grid stable after first paint', async ({ page }, testInfo) => {
    await page.goto('/requests?skipSetup=1');
    await waitForRequestsGrid(page);

    const samples = await sampleRequestsPageStability(page, {
      durationMs: 3000,
      intervalMs: 100,
    });
    const analysis = analyzeRequestsPageStability(samples);
    await attachStabilityTimeline(testInfo, 'initial-load-timeline.txt', analysis.timeline);

    expect(analysis.loaderTransitions, analysis.timeline).toBeLessThanOrEqual(1);
    expect(analysis.loaderGridOverlaps, analysis.timeline).toBe(0);
    expect(analysis.posterCountChanges, analysis.timeline).toBe(0);
  });

  test('seer status filter keeps loader and poster count stable after applying', async ({ page }, testInfo) => {
    await page.goto('/requests?skipSetup=1');
    await waitForRequestsGrid(page);

    await selectSeerStatusFilter(page, 'Pending');
    await expect(page.getByTestId('requests-page-loader')).toBeHidden({ timeout: 30000 });

    const samples = await sampleRequestsPageStability(page, {
      durationMs: 3500,
      intervalMs: 100,
    });
    const analysis = analyzeRequestsPageStability(samples);
    await attachStabilityTimeline(testInfo, 'seer-filter-timeline.txt', analysis.timeline);

    expect(analysis.loaderTransitions, analysis.timeline).toBeLessThanOrEqual(1);
    expect(analysis.loaderGridOverlaps, analysis.timeline).toBe(0);
    expect(analysis.posterCountChanges, analysis.timeline).toBe(0);

    const expectedPendingCount = buildFlatPendingCount(LOADED_REQUEST_COUNT);
    await expect(page.getByTestId('request-poster-card')).toHaveCount(expectedPendingCount, { timeout: 5000 });
  });

  test('seer filter transition records full timeline while applying', async ({ page }, testInfo) => {
    await page.goto('/requests?skipSetup=1');
    await waitForRequestsGrid(page);

    const samples = [];
    const startedAt = Date.now();
    const collectSamples = (async () => {
      while (Date.now() - startedAt < 5000) {
        samples.push(await page.evaluate(() => ({
          loaderVisible: Boolean(document.querySelector('[data-testid="requests-page-loader"]')?.offsetParent),
          gridVisible: Boolean(document.querySelector('[data-testid="requests-poster-grid"]')?.offsetParent),
          posterCount: document.querySelectorAll('[data-testid="request-poster-card"]').length,
        })));
        await page.waitForTimeout(75);
      }
    })();

    await selectSeerStatusFilter(page, 'Pending');
    await expect(page.getByTestId('requests-page-loader')).toBeHidden({ timeout: 30000 });
    await collectSamples;

    const transitionAnalysis = analyzeRequestsPageStability(samples);
    const postLoaderAnalysis = analyzePostLoaderPosterStability(samples);
    await attachStabilityTimeline(testInfo, 'seer-filter-full-transition.txt', transitionAnalysis.timeline);
    await attachStabilityTimeline(testInfo, 'seer-filter-post-loader.txt', postLoaderAnalysis.timeline);

    expect(transitionAnalysis.loaderGridOverlaps, transitionAnalysis.timeline).toBe(0);
    expect(postLoaderAnalysis.postLoaderPosterChanges, postLoaderAnalysis.timeline).toBe(0);

    const expectedPendingCount = buildFlatPendingCount(LOADED_REQUEST_COUNT);
    expect(postLoaderAnalysis.settledPosterCount).toBe(expectedPendingCount);
  });
});

test.describe('Requests page loading regression (stale DB vs live Seer)', () => {
  test('shows poster shrink when filter applies before live refresh finishes', async ({ page }, testInfo) => {
    await mockRequestsPageBoot(page, {
      requestCount: LOADED_REQUEST_COUNT,
      batchDelayMs: 1200,
    });

    await page.goto('/requests?skipSetup=1');
    await waitForRequestsGrid(page);

    const posterCounts = [];
    await selectSeerStatusFilter(page, 'Pending');

    for (let index = 0; index < 30; index += 1) {
      posterCounts.push({
        loaderVisible: await page.getByTestId('requests-page-loader').isVisible().catch(() => false),
        posterCount: await page.getByTestId('request-poster-card').count(),
      });
      await page.waitForTimeout(100);
    }

    const timeline = posterCounts.map((sample, index) => (
      `#${index} loader=${sample.loaderVisible} posters=${sample.posterCount}`
    )).join('\n');
    await attachStabilityTimeline(testInfo, 'slow-filter-refresh-timeline.txt', timeline);

    const expectedPendingCount = buildFlatPendingCount(LOADED_REQUEST_COUNT);
    const countsAfterLoaderHidden = [];
    let loaderWasVisible = false;

    for (const sample of posterCounts) {
      if (sample.loaderVisible) {
        loaderWasVisible = true;
      } else if (loaderWasVisible) {
        countsAfterLoaderHidden.push(sample.posterCount);
      }
    }

    expect(
      countsAfterLoaderHidden.length,
      `Expected loader to appear during filter refresh.\n${timeline}`,
    ).toBeGreaterThan(0);
    expect(
      [...new Set(countsAfterLoaderHidden)],
      `Poster count must not churn after filter loader hides.\n${timeline}`,
    ).toEqual([expectedPendingCount]);
  });
});

/**
 * @param {number} loadedCount
 * @returns {number}
 */
function buildFlatPendingCount(loadedCount) {
  let pending = 0;
  for (let index = 0; index < loadedCount; index += 1) {
    if (mockLiveSeerStatus(1000 + index) === 'pending') {
      pending += 1;
    }
  }
  return pending;
}
