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
