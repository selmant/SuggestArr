/**
 * Sample loader/grid visibility to detect UI flicker during requests page loads.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{ durationMs?: number, intervalMs?: number, selectors?: { loader: string, loaderMessage: string, grid: string, poster: string } }} [options]
 * @returns {Promise<Array<{ loaderVisible: boolean, gridVisible: boolean, posterCount: number, loaderMessage: string, ts: number }>>}
 */
export async function sampleRequestsPageStability(page, {
  durationMs = 4000,
  intervalMs = 100,
  selectors = {
    loader: '[data-testid="requests-page-loader"]',
    loaderMessage: '[data-testid="requests-page-loader-message"]',
    grid: '[data-testid="requests-poster-grid"]',
    poster: '[data-testid="request-poster-card"]',
  },
} = {}) {
  const samples = [];
  const startedAt = Date.now();

  while (Date.now() - startedAt < durationMs) {
    samples.push(await page.evaluate((selectorConfig) => {
      const loader = document.querySelector(selectorConfig.loader);
      const grid = document.querySelector(selectorConfig.grid);
      const loaderStyle = loader ? window.getComputedStyle(loader) : null;
      const gridStyle = grid ? window.getComputedStyle(grid) : null;

      return {
        loaderVisible: Boolean(
          loader &&
          loaderStyle &&
          loaderStyle.display !== 'none' &&
          loaderStyle.visibility !== 'hidden' &&
          loader.offsetParent !== null,
        ),
        gridVisible: Boolean(
          grid &&
          gridStyle &&
          gridStyle.display !== 'none' &&
          gridStyle.visibility !== 'hidden' &&
          grid.offsetParent !== null,
        ),
        posterCount: document.querySelectorAll(selectorConfig.poster).length,
        loaderMessage: document.querySelector(selectorConfig.loaderMessage)?.textContent?.trim() || '',
        ts: Date.now(),
      };
    }, selectors));
    await page.waitForTimeout(intervalMs);
  }

  return samples;
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ selectors?: { loader: string, loaderMessage: string, grid: string, poster: string } }} [options]
 * @returns {Promise<{ loaderVisible: boolean, gridVisible: boolean, posterCount: number, loaderMessage: string }>}
 */
export async function readRequestsPageSnapshot(page, { selectors } = {}) {
  const selectorConfig = selectors || {
    loader: '[data-testid="requests-page-loader"]',
    loaderMessage: '[data-testid="requests-page-loader-message"]',
    grid: '[data-testid="requests-poster-grid"]',
    poster: '[data-testid="request-poster-card"]',
  };

  return page.evaluate((config) => {
    const loader = document.querySelector(config.loader);
    const grid = document.querySelector(config.grid);
    const loaderStyle = loader ? window.getComputedStyle(loader) : null;
    const gridStyle = grid ? window.getComputedStyle(grid) : null;

    return {
      loaderVisible: Boolean(
        loader &&
        loaderStyle &&
        loaderStyle.display !== 'none' &&
        loaderStyle.visibility !== 'hidden' &&
        loader.offsetParent !== null,
      ),
      gridVisible: Boolean(
        grid &&
        gridStyle &&
        gridStyle.display !== 'none' &&
        gridStyle.visibility !== 'hidden' &&
        grid.offsetParent !== null,
      ),
      posterCount: document.querySelectorAll(config.poster).length,
      loaderMessage: document.querySelector(config.loaderMessage)?.textContent?.trim() || '',
    };
  }, selectorConfig);
}

/**
 * @param {Array<{ loaderVisible: boolean, gridVisible: boolean, posterCount: number, loaderMessage: string, ts: number }>} samples
 * @returns {{ loaderTransitions: number, gridTransitions: number, posterCountChanges: number, loaderGridOverlaps: number, timeline: string }}
 */
export function analyzeRequestsPageStability(samples) {
  let loaderTransitions = 0;
  let gridTransitions = 0;
  let posterCountChanges = 0;
  let loaderGridOverlaps = 0;

  for (let index = 1; index < samples.length; index += 1) {
    const previous = samples[index - 1];
    const current = samples[index];

    if (previous.loaderVisible !== current.loaderVisible) {
      loaderTransitions += 1;
    }
    if (previous.gridVisible !== current.gridVisible) {
      gridTransitions += 1;
    }
    if (previous.posterCount !== current.posterCount) {
      posterCountChanges += 1;
    }
    if (current.loaderVisible && current.gridVisible) {
      loaderGridOverlaps += 1;
    }
  }

  const timeline = samples.map((sample, index) => {
    const parts = [
      `#${index}`,
      sample.loaderVisible ? 'loader' : 'no-loader',
      sample.gridVisible ? 'grid' : 'no-grid',
      `posters=${sample.posterCount}`,
    ];
    if (sample.loaderMessage) {
      parts.push(`msg="${sample.loaderMessage}"`);
    }
    return parts.join(' ');
  }).join('\n');

  return {
    loaderTransitions,
    gridTransitions,
    posterCountChanges,
    loaderGridOverlaps,
    timeline,
  };
}

/**
 * After the loader last becomes hidden, poster count must not change again.
 *
 * @param {Array<{ loaderVisible: boolean, gridVisible: boolean, posterCount: number }>} samples
 * @returns {{ postLoaderPosterChanges: number, settledPosterCount: number|null, timeline: string }}
 */
export function analyzePostLoaderPosterStability(samples) {
  let lastLoaderHiddenIndex = -1;

  for (let index = samples.length - 1; index >= 0; index -= 1) {
    if (!samples[index].loaderVisible) {
      lastLoaderHiddenIndex = index;
      break;
    }
  }

  let postLoaderPosterChanges = 0;
  let settledPosterCount = null;

  if (lastLoaderHiddenIndex >= 0) {
    settledPosterCount = samples[lastLoaderHiddenIndex].posterCount;
    for (let index = lastLoaderHiddenIndex + 1; index < samples.length; index += 1) {
      if (samples[index].posterCount !== samples[index - 1].posterCount) {
        postLoaderPosterChanges += 1;
      }
    }
  }

  const timeline = samples.map((sample, index) => {
    const marker = index === lastLoaderHiddenIndex ? ' [loader-settled]' : '';
    return `#${index} ${sample.loaderVisible ? 'loader' : 'no-loader'} posters=${sample.posterCount}${marker}`;
  }).join('\n');

  return {
    postLoaderPosterChanges,
    settledPosterCount,
    timeline,
  };
}

/**
 * @param {import('@playwright/test').TestInfo} testInfo
 * @param {string} label
 * @param {string} timeline
 */
export async function attachStabilityTimeline(testInfo, label, timeline) {
  await testInfo.attach(label, {
    body: timeline,
    contentType: 'text/plain',
  });
}
