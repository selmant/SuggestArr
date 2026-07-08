const { test, expect } = require('@playwright/test');
const { getRequestsPageSelectors, detectRequestsPageSelectorMode } = require('./helpers/requestsPageSelectors');
const {
  analyzePostLoaderPosterStability,
  analyzeRequestsPageStability,
  attachStabilityTimeline,
  readRequestsPageSnapshot,
} = require('./helpers/pageStability');

const HOMELAB_BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://192.168.40.14:5000';

test.describe.configure({ mode: 'serial' });

test.use({ baseURL: HOMELAB_BASE_URL });

async function waitForInitialRequestsLoad(page, selectors) {
  await expect(page.getByRole('heading', { name: 'Request History' })).toBeVisible({ timeout: 30000 });

  await expect.poll(async () => {
    const snapshot = await readRequestsPageSnapshot(page, { selectors });
    return snapshot.posterCount;
  }, {
    message: 'Waiting for at least one request poster on homelab',
    timeout: 60000,
  }).toBeGreaterThan(0);

  await expect.poll(async () => {
    const snapshot = await readRequestsPageSnapshot(page, { selectors });
    return snapshot.loaderVisible;
  }, {
    message: 'Waiting for initial page loader to hide',
    timeout: 90000,
  }).toBe(false);
}

async function selectSeerStatusFilter(page, label) {
  await page.getByRole('button', { name: /All Seer Statuses/i }).click();
  await page.locator('.dropdown-item').filter({ hasText: label }).click();
}

test.describe('Homelab real-data Seer pending filter', () => {
  test('open requests and apply Seer pending without poster count churn', async ({ page }, testInfo) => {
    test.setTimeout(240_000);

    await page.goto('/requests');
    const selectorMode = await detectRequestsPageSelectorMode(page);
    const selectors = getRequestsPageSelectors(selectorMode);

    await waitForInitialRequestsLoad(page, selectors);

    const initialSnapshot = await readRequestsPageSnapshot(page, { selectors });
    await testInfo.attach('homelab-initial-snapshot.txt', {
      body: JSON.stringify({
        baseURL: HOMELAB_BASE_URL,
        selectorMode,
        ...initialSnapshot,
      }, null, 2),
      contentType: 'text/plain',
    });

    const samples = [];
    let filterApplied = false;
    const startedAt = Date.now();
    const collectSamples = (async () => {
      while (Date.now() - startedAt < 8000) {
        samples.push(await readRequestsPageSnapshot(page, { selectors }));
        if (!filterApplied && samples.length === 3) {
          filterApplied = true;
          await selectSeerStatusFilter(page, 'Pending');
        }
        await page.waitForTimeout(75);
      }
    })();

    await expect.poll(async () => {
      const snapshot = await readRequestsPageSnapshot(page, { selectors });
      return snapshot.loaderVisible;
    }, {
      message: 'Seer filter loader should finish',
      timeout: 150_000,
    }).toBe(false);

    await collectSamples;

    const transitionAnalysis = analyzeRequestsPageStability(samples);
    const postLoaderAnalysis = analyzePostLoaderPosterStability(samples);

    await attachStabilityTimeline(testInfo, 'homelab-seer-pending-transition.txt', transitionAnalysis.timeline);
    await attachStabilityTimeline(testInfo, 'homelab-seer-pending-post-loader.txt', postLoaderAnalysis.timeline);

    const posterCounts = samples.map((sample) => sample.posterCount);
    const uniquePosterCounts = [...new Set(posterCounts)];
    await testInfo.attach('homelab-seer-pending-poster-counts.txt', {
      body: [
        `initialPosters=${initialSnapshot.posterCount}`,
        `settledPosters=${postLoaderAnalysis.settledPosterCount}`,
        `uniqueCountsDuringWindow=${uniquePosterCounts.join(', ')}`,
        '',
        transitionAnalysis.timeline,
      ].join('\n'),
      contentType: 'text/plain',
    });

    const preFilterFlash = samples.slice(0, 4).some((sample, index) => (
      index > 0
      && !sample.loaderVisible
      && sample.posterCount !== initialSnapshot.posterCount
      && sample.posterCount !== 0
    ));
    expect(preFilterFlash, transitionAnalysis.timeline).toBe(false);

    expect(
      transitionAnalysis.loaderGridOverlaps,
      transitionAnalysis.timeline,
    ).toBe(0);

    expect(
      postLoaderAnalysis.postLoaderPosterChanges,
      `Poster count must not change after Seer filter loader hides.\n${postLoaderAnalysis.timeline}`,
    ).toBe(0);

    expect(
      postLoaderAnalysis.settledPosterCount,
      `Expected pending posters to remain visible after filter refresh.\n${transitionAnalysis.timeline}`,
    ).toBeGreaterThan(0);
  });
});
