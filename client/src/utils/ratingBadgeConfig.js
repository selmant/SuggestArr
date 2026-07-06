export const DEFAULT_RATING_BADGE_SETTINGS = {
  showTmdb: true,
  showImdb: true,
  showRt: true,
  showMetacritic: true,
  showTraktUser: true,
  showTraktCommunity: true,
};

export function getRatingBadgeSettings(config = {}) {
  return {
    showTmdb: config.SHOW_RATING_TMDB !== false,
    showImdb: config.SHOW_RATING_IMDB !== false,
    showRt: config.SHOW_RATING_RT !== false,
    showMetacritic: config.SHOW_RATING_METACRITIC !== false,
    showTraktUser: config.SHOW_RATING_TRAKT_USER !== false,
    showTraktCommunity: config.SHOW_RATING_TRAKT_COMMUNITY !== false,
  };
}

export function buildRatingBadges(item = {}, settings = DEFAULT_RATING_BADGE_SETTINGS, traktUserRating = null) {
  const badges = [];

  if (settings.showTmdb && item.rating != null) {
    badges.push({
      key: 'tmdb',
      label: 'TMDB',
      value: Number(item.rating).toFixed(1),
      icon: 'fas fa-star',
      className: 'rating-badge--tmdb',
    });
  }

  if (settings.showImdb && item.imdb_rating != null) {
    badges.push({
      key: 'imdb',
      label: 'IMDb',
      value: Number(item.imdb_rating).toFixed(1),
      icon: 'fab fa-imdb',
      className: 'rating-badge--imdb',
    });
  }

  if (settings.showRt && item.rt_rating != null) {
    badges.push({
      key: 'rt',
      label: 'RT',
      value: `${item.rt_rating}%`,
      icon: 'fas fa-tomato',
      className: 'rating-badge--rt',
    });
  }

  if (settings.showMetacritic && item.metacritic_rating != null) {
    badges.push({
      key: 'metacritic',
      label: 'MC',
      value: String(item.metacritic_rating),
      icon: 'fas fa-m',
      className: 'rating-badge--metacritic',
    });
  }

  if (settings.showTraktCommunity && item.trakt_rating != null) {
    badges.push({
      key: 'trakt-community',
      label: 'Trakt',
      value: Number(item.trakt_rating).toFixed(1),
      icon: 'icon-trakt',
      className: 'rating-badge--trakt',
    });
  }

  if (settings.showTraktUser && traktUserRating != null) {
    const stars = Number(traktUserRating) / 2;
    badges.push({
      key: 'trakt-user',
      label: 'You',
      value: Number.isInteger(stars) ? String(stars) : stars.toFixed(1),
      icon: 'icon-trakt',
      className: 'rating-badge--trakt-user',
    });
  }

  return badges;
}
