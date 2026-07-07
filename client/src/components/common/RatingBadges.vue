<template>
  <div
    v-if="badges.length"
    class="rating-badges"
    :class="{
      'rating-badges--compact': compact,
      'rating-badges--vertical': layout === 'vertical',
      'rating-badges--horizontal': layout === 'horizontal',
    }"
    data-testid="rating-badges">
    <span
      v-for="badge in badges"
      :key="badge.key"
      class="rating-badge"
      :class="[badge.className, badge.qualityClassName]"
      :title="badge.title || badge.label">
      <i class="rating-badge__icon" :class="badge.icon"></i>
      <span class="rating-badge__value">{{ badge.value }}</span>
    </span>
  </div>
</template>

<script>
import { buildRatingBadges, DEFAULT_RATING_BADGE_SETTINGS } from '@/utils/ratingBadgeConfig.js';

export default {
  name: 'RatingBadges',
  props: {
    item: {
      type: Object,
      required: true,
    },
    badgeSettings: {
      type: Object,
      default: () => ({ ...DEFAULT_RATING_BADGE_SETTINGS }),
    },
    traktUserRating: {
      type: [Number, String],
      default: null,
    },
    compact: {
      type: Boolean,
      default: false,
    },
    layout: {
      type: String,
      default: 'vertical',
      validator: (value) => ['vertical', 'horizontal'].includes(value),
    },
  },
  computed: {
    badges() {
      const traktRating = this.traktUserRating != null && this.traktUserRating !== ''
        ? Number(this.traktUserRating)
        : null;
      return buildRatingBadges(this.item, this.badgeSettings, traktRating);
    },
  },
};
</script>

<style scoped>
.rating-badges {
  display: flex;
  gap: var(--spacing-2xs);
  max-width: 100%;
}

.rating-badges--vertical {
  flex-direction: column;
  align-items: flex-end;
  flex-wrap: nowrap;
}

.rating-badges--horizontal {
  flex-direction: row;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.rating-badges--compact {
  gap: 0.15rem;
}

.rating-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.28rem;
  min-width: 0;
  border: 1px solid var(--surface-glass-strong);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
  background-color: rgba(10, 12, 18, 0.82);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-sm);
  font-size: 0.78rem;
  font-weight: 800;
  line-height: 1;
  white-space: nowrap;
  padding: 0.24rem 0.4rem;
}

.rating-badges--compact .rating-badge {
  font-size: 0.7rem;
  gap: 0.22rem;
  padding: 0.18rem 0.34rem;
}

.rating-badge__icon {
  flex: 0 0 auto;
  font-size: 0.72rem;
  opacity: 0.95;
}

.rating-badges--compact .rating-badge__icon {
  font-size: 0.66rem;
}

.rating-badge__value {
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
}

/* Source identity lives in the icon color. */
.rating-badge--tmdb .rating-badge__icon {
  color: #21d07a;
}

.rating-badge--imdb .rating-badge__icon {
  color: #f5c518;
}

.rating-badge--rt .rating-badge__icon {
  color: #fa320a;
}

.rating-badge--rt-user .rating-badge__icon {
  color: #ffb84d;
}

.rating-badge--metacritic .rating-badge__icon {
  color: #ffcc00;
}

.rating-badge--trakt .rating-badge__icon,
.rating-badge--trakt-user .rating-badge__icon {
  color: #ed1c24;
}

/*
 * Quality drives the readable "is this good or bad?" signal: the value text,
 * pill tint, and left accent bar all shift green -> amber -> red with the
 * score. Falls back to a neutral pill when a source has no numeric score.
 */
.rating-badge--good {
  background-color: rgba(16, 185, 129, 0.22);
  border-color: rgba(16, 185, 129, 0.4);
  border-left-color: var(--color-success-light);
}

.rating-badge--good .rating-badge__value {
  color: var(--color-success-light);
}

.rating-badge--mixed {
  background-color: rgba(245, 158, 11, 0.22);
  border-color: rgba(245, 158, 11, 0.4);
  border-left-color: var(--color-warning-light);
}

.rating-badge--mixed .rating-badge__value {
  color: var(--color-warning-light);
}

.rating-badge--bad {
  background-color: rgba(239, 68, 68, 0.22);
  border-color: rgba(239, 68, 68, 0.4);
  border-left-color: var(--color-error-light);
}

.rating-badge--bad .rating-badge__value {
  color: var(--color-error-light);
}
</style>
