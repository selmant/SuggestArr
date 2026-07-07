/** Human-readable labels for Seer request statuses. */

const STATUS_LABELS = {
  pending: 'Pending',
  approved: 'Approved',
  declined: 'Declined',
  processing: 'Processing',
  partially_available: 'Partial',
  available: 'Available',
  unavailable: 'Unavailable',
  failed: 'Failed',
  deleted: 'Deleted',
  completed: 'Completed',
  not_found: 'Not in Seer',
};

export const SEER_STATUS_FILTER_OPTIONS = [
  { value: 'all', label: 'All Seer Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'processing', label: 'Processing' },
  { value: 'unavailable', label: 'Unavailable' },
  { value: 'partially_available', label: 'Partially Available' },
  { value: 'available', label: 'Available' },
  { value: 'completed', label: 'Completed' },
  { value: 'declined', label: 'Declined' },
  { value: 'failed', label: 'Failed' },
  { value: 'deleted', label: 'Deleted' },
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

  const status = seerStatus || 'not_found';

  if (filter === 'unavailable') {
    return ['pending', 'approved', 'processing', 'partially_available', 'unavailable'].includes(status);
  }

  if (filter === 'processing') {
    return ['processing', 'partially_available', 'approved', 'unavailable'].includes(status);
  }

  return status === filter;
}
