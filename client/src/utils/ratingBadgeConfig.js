export const DEFAULT_RATING_BADGE_SETTINGS = {
  showTmdb: true,
  showImdb: true,
  showRt: true,
  showRtUser: true,
  showMetacritic: true,
  showTraktUser: true,
  showTraktCommunity: true,
};

export function getRatingBadgeSettings(config = {}) {
  return {
    showTmdb: config.SHOW_RATING_TMDB !== false,
    showImdb: config.SHOW_RATING_IMDB !== false,
    showRt: config.SHOW_RATING_RT !== false,
    showRtUser: config.SHOW_RATING_RT_USER !== false,
    showMetacritic: config.SHOW_RATING_METACRITIC !== false,
    showTraktUser: config.SHOW_RATING_TRAKT_USER !== false,
    showTraktCommunity: config.SHOW_RATING_TRAKT_COMMUNITY !== false,
  };
}

// Quality thresholds on a normalized 0-100 scale, aligned with the
// well-known traffic-light conventions used by Metacritic (green >= 61,
// yellow 40-60, red < 40) and Rotten Tomatoes' 60% "fresh" cutoff.
export const SCORE_QUALITY_THRESHOLDS = {
  good: 60,
  mixed: 40,
};

const QUALITY_LABELS = {
  good: 'High',
  mixed: 'Mixed',
  bad: 'Low',
};

/**
 * Classify a normalized 0-100 score into a quality bucket so posters can
 * signal "is this good or bad?" at a glance via color, not just numbers.
 *
 * @param {number|null} percent Score normalized to a 0-100 scale.
 * @returns {'good'|'mixed'|'bad'|null} Quality bucket, or null when unknown.
 */
export function getScoreQuality(percent) {
  if (percent == null || !Number.isFinite(Number(percent))) {
    return null;
  }
  const value = Number(percent);
  if (value >= SCORE_QUALITY_THRESHOLDS.good) {
    return 'good';
  }
  if (value >= SCORE_QUALITY_THRESHOLDS.mixed) {
    return 'mixed';
  }
  return 'bad';
}

function decorateQuality(badge, percent) {
  const quality = getScoreQuality(percent);
  if (!quality) {
    return badge;
  }
  return {
    ...badge,
    scorePercent: Math.round(Number(percent)),
    quality,
    qualityClassName: `rating-badge--${quality}`,
    title: `${badge.label} · ${QUALITY_LABELS[quality]} (${badge.value})`,
  };
}

export function buildRatingBadges(item = {}, settings = DEFAULT_RATING_BADGE_SETTINGS, traktUserRating = null) {
  const badges = [];

  if (settings.showTmdb && item.rating != null) {
    badges.push(decorateQuality({
      key: 'tmdb',
      label: 'TMDB',
      value: Number(item.rating).toFixed(1),
      icon: 'fas fa-star',
      className: 'rating-badge--tmdb',
    }, Number(item.rating) * 10));
  }

  if (settings.showImdb && item.imdb_rating != null) {
    badges.push(decorateQuality({
      key: 'imdb',
      label: 'IMDb',
      value: Number(item.imdb_rating).toFixed(1),
      icon: 'fab fa-imdb',
      className: 'rating-badge--imdb',
    }, Number(item.imdb_rating) * 10));
  }

  if (settings.showRt && item.rt_rating != null) {
    badges.push(decorateQuality({
      key: 'rt',
      label: 'RT',
      value: `${item.rt_rating}%`,
      icon: 'fas fa-tomato',
      className: 'rating-badge--rt',
    }, Number(item.rt_rating)));
  }

  if (settings.showRtUser && item.rt_user_rating != null) {
    badges.push(decorateQuality({
      key: 'rt-user',
      label: 'RT Aud',
      value: `${item.rt_user_rating}%`,
      icon: 'fas fa-users',
      className: 'rating-badge--rt-user',
    }, Number(item.rt_user_rating)));
  }

  if (settings.showMetacritic && item.metacritic_rating != null) {
    badges.push(decorateQuality({
      key: 'metacritic',
      label: 'MC',
      value: `${item.metacritic_rating}/100`,
      icon: 'fas fa-m',
      className: 'rating-badge--metacritic',
    }, Number(item.metacritic_rating)));
  }

  if (settings.showTraktCommunity && item.trakt_rating != null) {
    badges.push(decorateQuality({
      key: 'trakt-community',
      label: 'Trakt',
      value: Number(item.trakt_rating).toFixed(1),
      icon: 'icon-trakt',
      className: 'rating-badge--trakt',
    }, Number(item.trakt_rating) * 10));
  }

  if (settings.showTraktUser && traktUserRating != null) {
    const stars = Number(traktUserRating) / 2;
    badges.push(decorateQuality({
      key: 'trakt-user',
      label: 'You',
      value: Number.isInteger(stars) ? String(stars) : stars.toFixed(1),
      icon: 'icon-trakt',
      className: 'rating-badge--trakt-user',
    }, Number(traktUserRating) * 10));
  }

  return badges;
}
