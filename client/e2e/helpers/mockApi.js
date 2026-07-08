/** Shared Playwright route mocks for SuggestArr boot + requests Trakt UI. */

export const mockConfig = {
  AUTH_MODE: 'disabled',
  ENABLE_STATIC_BACKGROUND: true,
  STATIC_BACKGROUND_COLOR: '#101018',
  SUBPATH: '',
};

export const mockAuthStatus = {
  auth_setup_complete: true,
  app_setup_complete: true,
  authenticated: true,
  bypass: true,
};

export const mockSetupStatus = {
  setup_completed: true,
  is_complete: true,
};

export const mockTraktMediaUsers = {
  media_users: [
    {
      provider: 'jellyfin',
      external_user_id: 'jf-user-1',
      external_username: 'alice',
      trakt: { connected: true, trakt_username: 'alice_trakt' },
    },
  ],
};

export const mockRequestsPayload = {
  current_page: 1,
  per_page: 8,
  total_pages: 1,
  total_sources: 1,
  total_requests: 2,
  data: [
    {
      source_id: '42',
      source_title: 'Inception',
      source_overview: 'A mind-bending thriller.',
      source_release_date: '2010',
      source_poster_path: '/poster-source.jpg',
      rating: 8.8,
      media_type: 'movie',
      logo_path: null,
      backdrop_path: '/backdrop-source.jpg',
      is_anime: false,
      requests: [
        {
          request_id: '27205',
          title: 'Inception',
          media_type: 'movie',
          requested_at: '2026-01-01T12:00:00Z',
          overview: 'Dream within a dream.',
          poster_path: '/poster.jpg',
          release_date: '2010',
          rating: 8.8,
          logo_path: null,
          backdrop_path: '/backdrop.jpg',
          rationale: null,
          user_id: null,
          user_name: null,
          source_origin: null,
        },
        {
          request_id: '603',
          title: 'The Matrix',
          media_type: 'movie',
          requested_at: '2026-01-02T12:00:00Z',
          overview: 'Wake up Neo.',
          poster_path: '/poster2.jpg',
          release_date: '1999',
          rating: 8.7,
          logo_path: null,
          backdrop_path: '/backdrop2.jpg',
          rationale: null,
          user_id: 'jf-user-1',
          user_name: 'alice',
          source_origin: null,
        },
      ],
    },
  ],
};

/**
 * Register API mocks required to load /requests with Trakt controls.
 *
 * @param {import('@playwright/test').Page} page
 */
export async function mockSuggestarrBoot(page) {
  await page.route('**/api/config/status', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(mockSetupStatus),
  }));

  await page.route('**/api/auth/status', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(mockAuthStatus),
  }));

  await page.route('**/api/config/fetch', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(mockConfig),
  }));

  await page.route('**/api/trakt/media-users', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(mockTraktMediaUsers),
  }));

  await page.route('**/api/automation/requests**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(mockRequestsPayload),
  }));

  await page.route('**/api/automation/requests/*/movie/trakt/status**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      tmdb_id: '27205',
      media_type: 'movie',
      user_id: 'jf-user-1',
      watched: false,
      rating: null,
      rating_stars: null,
    }),
  }));

  await page.route('**/api/automation/requests/*/movie/trakt/mark-watched', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      tmdb_id: '27205',
      media_type: 'movie',
      user_id: 'jf-user-1',
      watched: true,
      rating: null,
      rating_stars: null,
    }),
  }));
}

/**
 * Build a flat requests payload with deterministic Seer statuses for flicker tests.
 *
 * @param {number} count
 * @returns {object}
 */
export function buildFlatRequestsPayload(count = 32, page = 1, perPage = 24) {
  const data = Array.from({ length: count }, (_, index) => {
    const requestId = String(1000 + index);
    return {
      request_id: requestId,
      title: `Request ${requestId}`,
      media_type: 'movie',
      requested_at: `2026-01-${String((index % 28) + 1).padStart(2, '0')}T12:00:00Z`,
      overview: `Overview for ${requestId}`,
      poster_path: `/poster-${requestId}.jpg`,
      release_date: '2020',
      rating: 7.5,
      backdrop_path: null,
      logo_path: null,
      is_anime: false,
      user_id: 'internal-user-5',
      user_name: 'alice',
      source_origin: null,
      seer_status: 'pending',
      seer_request_status: null,
      seer_media_status: null,
      source_id: '42',
      source_title: 'Inception',
      source_poster_path: null,
      source_backdrop_path: null,
      source_logo_path: null,
    };
  });

  return {
    current_page: page,
    per_page: perPage,
    total_pages: Math.max(1, Math.ceil(count / perPage)),
    total: count,
    data: data.slice((page - 1) * perPage, page * perPage),
  };
}

/**
 * Resolve live Seer status for batch mocks. Even ids become declined to expose filter flicker.
 *
 * @param {string|number} tmdbId
 * @returns {string}
 */
export function mockLiveSeerStatus(tmdbId) {
  return Number(tmdbId) % 2 === 0 ? 'declined' : 'pending';
}

/**
 * Register API mocks for /requests stability tests with delayed integration batches.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{ requestCount?: number, batchDelayMs?: number, flatPage?: number }} [options]
 */
export async function mockRequestsPageBoot(page, {
  requestCount = 32,
  batchDelayMs = 400,
  flatPage = 1,
} = {}) {
  const flatPayload = buildFlatRequestsPayload(requestCount, flatPage);

  await mockSuggestarrBoot(page);

  await page.route('**/api/automation/requests/flat**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(flatPayload),
    });
  });

  await page.route('**/api/automation/requests/seer/status-batch', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, batchDelayMs));
    const payload = route.request().postDataJSON();
    const items = Array.isArray(payload?.items) ? payload.items : [];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        statuses: items.map((item) => ({
          tmdb_id: String(item.tmdb_id),
          media_type: item.media_type,
          seer_status: mockLiveSeerStatus(item.tmdb_id),
          can_action: false,
        })),
      }),
    });
  });

  await page.route('**/api/automation/requests/trakt/status-batch', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, batchDelayMs));
    const payload = route.request().postDataJSON();
    const items = Array.isArray(payload?.items) ? payload.items : [];
    const userId = String(payload?.user_id || 'jf-user-1');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user_id: userId,
        statuses: items.map((item) => ({
          tmdb_id: String(item.tmdb_id),
          media_type: item.media_type,
          user_id: userId,
          watched: false,
          rating: null,
          rating_stars: null,
        })),
      }),
    });
  });
}
