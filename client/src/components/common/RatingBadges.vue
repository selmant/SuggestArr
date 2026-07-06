<template>
  <div
    v-if="badges.length"
    class="rating-badges"
    :class="{ 'rating-badges--compact': compact }"
    data-testid="rating-badges">
    <span
      v-for="badge in badges"
      :key="badge.key"
      class="rating-badge"
      :class="badge.className"
      :title="badge.label">
      <i :class="badge.icon"></i>
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
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--spacing-2xs);
  max-width: 100%;
}

.rating-badges--compact {
  gap: 0.15rem;
}

.rating-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  min-width: 0;
  border: 1px solid var(--surface-glass-strong);
  border-radius: var(--radius-full);
  background-color: var(--color-bg-overlay-heavy);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-sm);
  font-size: 0.62rem;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  padding: var(--spacing-2xs) var(--spacing-xs);
}

.rating-badges--compact .rating-badge {
  font-size: 0.58rem;
  padding: 0.1rem 0.3rem;
}

.rating-badge i {
  flex: 0 0 auto;
  font-size: 0.62rem;
}

.rating-badge--tmdb {
  background-color: var(--color-success-alpha-20);
  border-color: var(--color-success-alpha-20);
  color: var(--color-success-light);
}

.rating-badge--imdb {
  background-color: rgba(245, 197, 24, 0.18);
  border-color: rgba(245, 197, 24, 0.35);
  color: #f5c518;
}

.rating-badge--rt {
  background-color: rgba(250, 50, 10, 0.18);
  border-color: rgba(250, 50, 10, 0.35);
  color: #ff6b4a;
}

.rating-badge--rt-user {
  background-color: rgba(250, 180, 50, 0.18);
  border-color: rgba(250, 180, 50, 0.35);
  color: #ffb84d;
}

.rating-badge--metacritic {
  background-color: rgba(255, 204, 0, 0.16);
  border-color: rgba(255, 204, 0, 0.35);
  color: #ffcc00;
}

.rating-badge--trakt,
.rating-badge--trakt-user {
  background-color: rgba(237, 28, 36, 0.16);
  border-color: rgba(237, 28, 36, 0.35);
  color: #ed1c24;
}
</style>
