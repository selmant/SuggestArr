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

/**
 * @param {string} status
 * @returns {string}
 */
export function formatSeerStatusLabel(status) {
  return STATUS_LABELS[status] || 'Seer';
}
