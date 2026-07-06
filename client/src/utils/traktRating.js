/**
 * Normalize Trakt status payloads to a 0.5–5 star string for UI controls.
 *
 * @param {object|null|undefined} status
 * @returns {string}
 */
export function starsFromTraktStatus(status) {
  if (!status) {
    return '';
  }
  if (status.rating_stars != null && status.rating_stars !== '') {
    return String(status.rating_stars);
  }
  if (status.rating != null && status.rating !== '') {
    return String(Number(status.rating) / 2);
  }
  return '';
}

/**
 * Format star value for compact labels.
 *
 * @param {string|number|null|undefined} stars
 * @returns {string}
 */
export function formatTraktStars(stars) {
  if (stars === null || stars === undefined || stars === '') {
    return '';
  }
  const value = Number(stars);
  if (!Number.isFinite(value) || value <= 0) {
    return '';
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
