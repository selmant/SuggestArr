/** Human-readable labels for Seer request statuses. */

const STATUS_LABELS = {
  pending: 'Pending',
  approved: 'Approved',
  declined: 'Declined',
  processing: 'Processing',
  partially_available: 'Partial',
  available: 'Available',
  not_found: 'Not in Seer',
};

export const SEER_STATUS_FILTER_OPTIONS = [
  { value: 'all', label: 'All Seer Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'processing', label: 'Processing' },
  { value: 'partially_available', label: 'Partially Available' },
  { value: 'available', label: 'Available' },
  { value: 'declined', label: 'Declined' },
  { value: 'not_found', label: 'Not in Seer' },
];

/**
 * @param {string} status
 * @returns {string}
 */
export function formatSeerStatusLabel(status) {
  return STATUS_LABELS[status] || 'Seer';
}

/**
 * @param {string|null|undefined} seerStatus
 * @param {string} filter
 * @returns {boolean}
 */
export function matchesSeerStatusFilter(seerStatus, filter) {
  if (!filter || filter === 'all') {
    return true;
  }
  return seerStatus === filter;
}
