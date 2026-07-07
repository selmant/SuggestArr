<template>
  <Teleport to="body">
    <transition name="request-details-fade">
      <div
        v-if="show && selectedSource"
        class="request-details-modal"
        @click.self="$emit('close')">
        <div v-if="!isModalReady" class="request-details-modal__loading" @click.stop>
          <i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i>
          <span>Loading details...</span>
        </div>

        <div v-else class="request-details-modal__content">
          <div v-if="displayBackdrop" class="request-details-modal__hero">
            <img
              :src="displayBackdrop"
              alt=""
              class="request-details-modal__hero-image" />
            <div class="request-details-modal__hero-gradient" />
          </div>

          <button @click="$emit('close')" class="request-details-modal__close" type="button">
            <i class="fas fa-times"></i>
          </button>

          <div class="request-details-modal__body">
            <header class="request-details-modal__header">
              <div class="request-details-modal__poster">
                <img
                  v-if="selectedSource.poster_path"
                  :src="selectedSource.poster_path"
                  :alt="selectedSource.title"
                  class="request-details-modal__poster-image" />
                <div v-else class="request-details-modal__poster-placeholder">
                  <i class="fas fa-image"></i>
                </div>
              </div>

              <div class="request-details-modal__title-block">
                <div v-if="selectedSource.media_type" class="request-details-modal__type-badge">
                  {{ selectedSource.media_type === 'movie' ? 'Movie' : 'TV Series' }}
                </div>

                <h1 class="request-details-modal__title">
                  {{ selectedSource.title }}
                  <span v-if="displayYear" class="request-details-modal__year">({{ displayYear }})</span>
                </h1>

                <p v-if="displayOriginalTitle" class="request-details-modal__original-title">
                  {{ displayOriginalTitle }}
                </p>

                <div v-if="mediaAttributeParts.length" class="request-details-modal__attributes">
                  <template v-for="(part, index) in mediaAttributeParts" :key="`${part.type}-${index}`">
                    <span v-if="index > 0" class="request-details-modal__attribute-sep">|</span>
                    <span
                      v-if="part.type === 'cert'"
                      class="request-details-modal__cert-badge">
                      {{ part.value }}
                    </span>
                    <span v-else class="request-details-modal__attribute-text">{{ part.value }}</span>
                  </template>
                </div>

                <RatingBadges
                  v-if="selectedSource.rating || hasExtraRatings"
                  class="request-details-modal__header-ratings"
                  layout="horizontal"
                  :item="selectedSource"
                  :badge-settings="badgeSettings"
                  :trakt-user-rating="modalTraktUserRating" />

                <p v-if="displayTagline" class="request-details-modal__tagline">{{ displayTagline }}</p>

                <div v-if="seerModalTarget" class="seer-action-strip request-details-modal__action-strip" data-testid="seer-action-strip">
                  <div class="seer-action-main">
                    <span class="seer-action-label">
                      <i class="fas fa-inbox"></i>
                      Seer
                    </span>
                    <span v-if="seerStatusLoading" class="seer-action-state">Checking...</span>
                    <span v-else-if="seerStatusError" class="seer-action-state seer-action-state--warn">
                      {{ seerStatusError }}
                    </span>
                    <span
                      v-else
                      class="seer-status-badge"
                      :class="seerStatus?.seer_status ? `seer-status-badge--${seerStatus.seer_status}` : ''">
                      {{ getSeerInlineLabel(seerModalTarget) }}
                    </span>
                  </div>
                  <div v-if="canActionSeer(seerModalTarget)" class="seer-action-controls">
                    <button
                      type="button"
                      class="seer-action-btn seer-action-btn--approve"
                      data-testid="seer-approve"
                      :disabled="seerActionLoading || seerStatusLoading"
                      @click="$emit('approve-seer')">
                      <i class="fas fa-check"></i>
                      Approve
                    </button>
                    <button
                      type="button"
                      class="seer-action-btn seer-action-btn--decline"
                      data-testid="seer-decline"
                      :disabled="seerActionLoading || seerStatusLoading"
                      @click="$emit('decline-seer')">
                      <i class="fas fa-times"></i>
                      Decline
                    </button>
                  </div>
                </div>

                <div v-if="traktModalTarget" class="trakt-action-strip trakt-action-strip--modal request-details-modal__action-strip" data-testid="trakt-action-strip">
                  <div class="trakt-action-main">
                    <div class="trakt-action-summary">
                      <span class="trakt-action-label">
                        <i class="icon-trakt"></i>
                        Trakt
                      </span>
                      <span v-if="traktStatusLoading" class="trakt-action-state">Checking...</span>
                      <span v-else-if="traktStatusError" class="trakt-action-state trakt-action-state--warn">
                        {{ traktStatusError }}
                      </span>
                      <span v-else class="trakt-action-state">{{ traktStatusLabel }}</span>
                    </div>
                  </div>
                  <div class="trakt-action-controls">
                    <button
                      type="button"
                      class="trakt-toggle-btn"
                      data-testid="trakt-mark-watched"
                      :class="{ active: traktStatus?.watched }"
                      :disabled="traktActionLoading || traktStatusLoading"
                      @click="$emit('set-trakt-watched', !traktStatus?.watched)">
                      <i :class="traktStatus?.watched ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
                      {{ traktStatus?.watched ? 'Mark unwatched' : 'Mark watched' }}
                    </button>
                    <div class="trakt-action-rating" data-testid="trakt-star-rating-wrap">
                      <TraktStarRating
                        :model-value="traktRatingStars"
                        :disabled="traktActionLoading || traktStatusLoading"
                        show-value
                        @rate="onSelectedRatingUpdate" />
                    </div>
                  </div>
                </div>
              </div>
            </header>

            <div class="request-details-modal__main">
              <div class="request-details-modal__primary">
                <section v-if="selectedSource.rationale" class="request-details-modal__section">
                  <h2 class="request-details-modal__section-title" :class="{ 'request-details-modal__section-title--ai': selectedSource._isAiRequest }">
                    {{ selectedSource._isAiRequest ? 'Search Query' : 'AI Reasoning' }}
                  </h2>
                  <p class="request-details-modal__rationale" :class="{ 'request-details-modal__rationale--ai': selectedSource._isAiRequest }">
                    {{ selectedSource.rationale }}
                  </p>
                </section>

                <section class="request-details-modal__section">
                  <h2 class="request-details-modal__section-title">Overview</h2>
                  <p class="request-details-modal__overview">{{ displayOverview }}</p>
                  <p v-if="detailsError" class="request-details-modal__details-error">{{ detailsError }}</p>
                </section>

                <section v-if="displayKeywords.length" class="request-details-modal__section">
                  <div class="request-details-modal__keyword-list">
                    <span
                      v-for="keyword in displayKeywords"
                      :key="keyword"
                      class="request-details-modal__keyword-tag">
                      {{ keyword }}
                    </span>
                  </div>
                </section>

                <section v-if="displayCast.length" class="request-details-modal__section">
                  <h2 class="request-details-modal__section-title">Cast</h2>
                  <div class="request-details-modal__cast-list">
                    <div
                      v-for="member in displayCast"
                      :key="`${member.name}-${member.character}`"
                      class="request-details-modal__cast-card">
                      <div class="request-details-modal__cast-avatar">
                        <img
                          v-if="member.profile_path"
                          :src="member.profile_path"
                          :alt="member.name"
                          class="request-details-modal__cast-photo" />
                        <div v-else class="request-details-modal__cast-photo-placeholder">
                          <i class="fas fa-user"></i>
                        </div>
                      </div>
                      <div class="request-details-modal__cast-meta">
                        <span class="request-details-modal__cast-name">{{ member.name }}</span>
                        <span v-if="member.character" class="request-details-modal__cast-character">{{ member.character }}</span>
                      </div>
                    </div>
                  </div>
                </section>

                <section v-if="displayTrailer || displayHomepage" class="request-details-modal__section request-details-modal__links">
                  <a
                    v-if="displayTrailer"
                    :href="displayTrailer"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="request-details-modal__link-btn request-details-modal__link-btn--trailer">
                    <i class="fab fa-youtube"></i>
                    Watch Trailer
                  </a>
                  <a
                    v-if="displayHomepage"
                    :href="displayHomepage"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="request-details-modal__link-btn">
                    <i class="fas fa-globe"></i>
                    Official Site
                  </a>
                </section>
              </div>

              <aside v-if="metaPanelItems.length || requestPanelItems.length" class="request-details-modal__sidebar">
                <section v-if="metaPanelItems.length" class="request-details-modal__panel">
                  <h3 class="request-details-modal__panel-title">Details</h3>
                  <dl class="request-details-modal__meta-list">
                    <div
                      v-for="item in metaPanelItems"
                      :key="item.label"
                      class="request-details-modal__meta-row">
                      <dt>{{ item.label }}</dt>
                      <dd>{{ item.value }}</dd>
                    </div>
                  </dl>
                </section>

                <section v-if="displayWatchProviders.length" class="request-details-modal__panel">
                  <h3 class="request-details-modal__panel-title">Currently Streaming On</h3>
                  <div class="request-details-modal__provider-list">
                    <span
                      v-for="provider in displayWatchProviders"
                      :key="provider"
                      class="request-details-modal__provider-pill">
                      {{ provider }}
                    </span>
                  </div>
                </section>

                <section v-if="requestPanelItems.length" class="request-details-modal__panel request-details-modal__panel--request">
                  <h3 class="request-details-modal__panel-title">Request</h3>
                  <dl class="request-details-modal__meta-list">
                    <div
                      v-for="item in requestPanelItems"
                      :key="item.label"
                      class="request-details-modal__meta-row">
                      <dt>{{ item.label }}</dt>
                      <dd>{{ item.value }}</dd>
                    </div>
                  </dl>
                </section>
              </aside>
            </div>

            <section v-if="selectedSource.requests && selectedSource.requests.length > 0" class="request-details-modal__section request-details-modal__related">
              <h2 class="request-details-modal__section-title">
                Requested Media ({{ selectedSource.requests.length }})
              </h2>
              <div class="request-details-modal__requests-list">
                <div
                  v-for="request in selectedSource.requests"
                  :key="request.request_id"
                  class="request-details-modal__request-item"
                  @click="$emit('select-related', request)">
                  <div class="request-details-modal__request-info">
                    <h4 class="request-details-modal__request-title">{{ request.title }}</h4>
                    <p class="request-details-modal__request-date">
                      <i class="fas fa-clock"></i>
                      Requested on {{ formatDate(request.requested_at) }}
                    </p>
                    <p v-if="request.user_name" class="request-details-modal__request-date">
                      <i class="fas fa-user"></i>
                      {{ request.user_name }}
                    </p>
                    <div v-if="canShowRelatedSeer(request)" class="seer-inline-actions" data-testid="seer-inline-actions" @click.stop>
                      <span
                        class="seer-status-badge"
                        :class="getSeerStatus(request)?.seer_status ? `seer-status-badge--${getSeerStatus(request).seer_status}` : ''">
                        <i class="fas fa-inbox"></i>
                        {{ getSeerInlineLabel(request) }}
                      </span>
                      <button
                        v-if="canActionSeer(request)"
                        type="button"
                        class="seer-action-btn seer-action-btn--approve"
                        data-testid="seer-inline-approve"
                        :disabled="isSeerBusy(request)"
                        @click.stop="$emit('approve-related-seer', request)">
                        <i class="fas fa-check"></i>
                        Approve
                      </button>
                      <button
                        v-if="canActionSeer(request)"
                        type="button"
                        class="seer-action-btn seer-action-btn--decline"
                        data-testid="seer-inline-decline"
                        :disabled="isSeerBusy(request)"
                        @click.stop="$emit('decline-related-seer', request)">
                        <i class="fas fa-times"></i>
                        Decline
                      </button>
                    </div>
                    <div v-if="canShowRelatedTrakt(request)" class="trakt-inline-actions" data-testid="trakt-inline-actions" @click.stop>
                      <span
                        class="trakt-inline-state"
                        :class="{ watched: getTraktStatus(request)?.watched }">
                        <i class="icon-trakt"></i>
                        {{ getTraktInlineLabel(request) }}
                      </span>
                      <button
                        type="button"
                        class="trakt-inline-btn"
                        data-testid="trakt-inline-mark-watched"
                        :class="{ active: getTraktStatus(request)?.watched }"
                        :disabled="isTraktBusy(request)"
                        @click.stop="$emit('set-related-trakt-watched', request, !getTraktStatus(request)?.watched)">
                        <i :class="getTraktStatus(request)?.watched ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
                        {{ getTraktStatus(request)?.watched ? 'Unwatch' : 'Watched' }}
                      </button>
                      <div class="trakt-inline-rating" data-testid="trakt-inline-rating">
                        <TraktStarRating
                          :model-value="getTraktRatingStars(request)"
                          :disabled="isTraktBusy(request)"
                          compact
                          @rate="$emit('rate-related-on-trakt', request, $event)" />
                      </div>
                    </div>
                  </div>
                  <button type="button" class="request-details-modal__request-btn">
                    <i class="fas fa-external-link-alt"></i>
                    Details
                  </button>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script>
import { formatDate } from '@/utils/dateUtils.js';
import { getRequestDetails } from '@/api/api.js';
import {
  getRequestMethodMetadata,
  getRequestSourceContentMetadata,
} from '@/utils/requestSourceMetadata.js';
import TraktStarRating from '@/components/common/TraktStarRating.vue';
import RatingBadges from '@/components/common/RatingBadges.vue';
import { DEFAULT_RATING_BADGE_SETTINGS } from '@/utils/ratingBadgeConfig.js';

export default {
  name: 'RequestDetailsModal',
  components: {
    TraktStarRating,
    RatingBadges,
  },
  props: {
    show: {
      type: Boolean,
      default: false,
    },
    selectedSource: {
      type: Object,
      default: null,
    },
    traktModalTarget: {
      type: Object,
      default: null,
    },
    canShowRelatedTrakt: {
      type: Function,
      default: () => false,
    },
    traktStatus: {
      type: Object,
      default: null,
    },
    traktStatusLoading: {
      type: Boolean,
      default: false,
    },
    traktActionLoading: {
      type: Boolean,
      default: false,
    },
    traktStatusError: {
      type: String,
      default: '',
    },
    traktRatingStars: {
      type: String,
      default: '',
    },
    getTraktStatus: {
      type: Function,
      default: () => null,
    },
    getTraktRatingStars: {
      type: Function,
      default: () => '',
    },
    getTraktInlineLabel: {
      type: Function,
      default: () => 'Trakt',
    },
    isTraktBusy: {
      type: Function,
      default: () => false,
    },
    seerModalTarget: {
      type: Object,
      default: null,
    },
    canShowRelatedSeer: {
      type: Function,
      default: () => false,
    },
    canActionSeer: {
      type: Function,
      default: () => false,
    },
    seerStatus: {
      type: Object,
      default: null,
    },
    seerStatusLoading: {
      type: Boolean,
      default: false,
    },
    seerActionLoading: {
      type: Boolean,
      default: false,
    },
    seerStatusError: {
      type: String,
      default: '',
    },
    getSeerStatus: {
      type: Function,
      default: () => null,
    },
    getSeerInlineLabel: {
      type: Function,
      default: () => 'Seer',
    },
    isSeerBusy: {
      type: Function,
      default: () => false,
    },
    badgeSettings: {
      type: Object,
      default: () => ({ ...DEFAULT_RATING_BADGE_SETTINGS }),
    },
  },
  data() {
    return {
      details: null,
      detailsLoading: false,
      detailsReady: false,
      detailsError: '',
      detailsRequestToken: 0,
    };
  },
  emits: [
    'close',
    'select-related',
    'set-trakt-watched',
    'update:trakt-rating-stars',
    'rate-selected-on-trakt',
    'set-related-trakt-watched',
    'rate-related-on-trakt',
    'approve-seer',
    'decline-seer',
    'approve-related-seer',
    'decline-related-seer',
  ],
  watch: {
    show(value) {
      if (!value) {
        this.resetDetails();
        return;
      }
      this.fetchDetailsForSelection();
    },
    selectedSource: {
      deep: true,
      handler() {
        if (this.show) {
          this.fetchDetailsForSelection();
        }
      },
    },
  },
  computed: {
    detailsTmdbId() {
      if (!this.selectedSource) {
        return '';
      }
      return String(this.selectedSource.request_id || this.selectedSource.source_id || '');
    },
    shouldFetchDetails() {
      return Boolean(this.detailsTmdbId && this.selectedSource?.media_type);
    },
    isModalReady() {
      if (!this.shouldFetchDetails) {
        return true;
      }
      return this.detailsReady;
    },
    displayTagline() {
      return this.details?.tagline || '';
    },
    displayOriginalTitle() {
      const original = this.details?.original_title || '';
      const title = this.selectedSource?.title || '';
      if (!original || original === title) {
        return '';
      }
      return original;
    },
    displayGenres() {
      return Array.isArray(this.details?.genres) ? this.details.genres : [];
    },
    displayKeywords() {
      return Array.isArray(this.details?.keywords) ? this.details.keywords : [];
    },
    displayCast() {
      return Array.isArray(this.details?.cast) ? this.details.cast : [];
    },
    displayTrailer() {
      return this.details?.trailer || '';
    },
    displayHomepage() {
      return this.details?.homepage || '';
    },
    displayBackdrop() {
      return this.details?.backdrop_path || this.selectedSource?.backdrop_path || '';
    },
    displayOverview() {
      if (this.details?.overview) {
        return this.details.overview;
      }
      return this.selectedSource?.overview || 'Overview unavailable.';
    },
    displayReleaseDate() {
      return this.details?.release_date || this.selectedSource?.release_date || '';
    },
    displayYear() {
      const date = this.displayReleaseDate;
      return date ? String(date).slice(0, 4) : '';
    },
    displayStatus() {
      return this.details?.status || '';
    },
    displayContentRating() {
      return this.details?.content_rating || '';
    },
    tvSeasonsLabel() {
      if (this.selectedSource?.media_type !== 'tv') {
        return '';
      }
      const seasons = this.details?.seasons_count;
      const episodes = this.details?.episodes_count;
      if (seasons == null && episodes == null) {
        return '';
      }
      const parts = [];
      if (seasons != null) {
        parts.push(`${seasons} Season${seasons === 1 ? '' : 's'}`);
      }
      if (episodes != null) {
        parts.push(`${episodes} Episode${episodes === 1 ? '' : 's'}`);
      }
      return parts.join(' · ');
    },
    displayNetworks() {
      const networks = this.details?.networks;
      return Array.isArray(networks) && networks.length ? networks.join(', ') : '';
    },
    displayCollection() {
      return this.details?.collection || '';
    },
    displayProductionCompanies() {
      const companies = this.details?.production_companies;
      return Array.isArray(companies) && companies.length ? companies.join(', ') : '';
    },
    displayWatchProviders() {
      const providers = this.details?.watch_providers;
      return Array.isArray(providers) ? providers : [];
    },
    runtimeLabel() {
      const runtime = this.details?.runtime;
      if (!runtime) {
        return '';
      }
      if (this.selectedSource?.media_type === 'tv') {
        return `${runtime} min`;
      }
      return `${runtime} min`;
    },
    directorHeading() {
      return this.selectedSource?.media_type === 'tv' ? 'Created By' : 'Director';
    },
    directorLabel() {
      const directors = this.details?.director;
      if (!Array.isArray(directors) || !directors.length) {
        return '';
      }
      return directors.join(', ');
    },
    mediaAttributeParts() {
      const parts = [];
      if (this.displayContentRating) {
        parts.push({ type: 'cert', value: this.displayContentRating });
      }
      if (this.runtimeLabel) {
        parts.push({ type: 'text', value: this.runtimeLabel });
      }
      if (this.displayGenres.length) {
        parts.push({ type: 'text', value: this.displayGenres.join(', ') });
      }
      if (this.tvSeasonsLabel) {
        parts.push({ type: 'text', value: this.tvSeasonsLabel });
      }
      return parts;
    },
    metaPanelItems() {
      const items = [];
      if (this.displayReleaseDate) {
        items.push({
          label: this.selectedSource?.media_type === 'tv' ? 'First Air Date' : 'Release Date',
          value: this.displayReleaseDate,
        });
      }
      if (this.displayStatus) {
        items.push({ label: 'Status', value: this.displayStatus });
      }
      if (this.directorLabel) {
        items.push({ label: this.directorHeading, value: this.directorLabel });
      }
      if (this.displayNetworks) {
        items.push({ label: 'Network', value: this.displayNetworks });
      }
      if (this.displayCollection) {
        items.push({ label: 'Collection', value: this.displayCollection });
      }
      if (this.displayProductionCompanies) {
        items.push({ label: 'Studio', value: this.displayProductionCompanies });
      }
      return items;
    },
    requestPanelItems() {
      const items = [];
      if (this.selectedSource?.requested_at) {
        items.push({
          label: 'Requested',
          value: this.formatDate(this.selectedSource.requested_at),
        });
      }
      if (this.requestMethodLabel) {
        items.push({ label: 'Method', value: this.requestMethodLabel });
      }
      if (this.selectedSource?.user_name) {
        items.push({ label: 'User', value: this.selectedSource.user_name });
      }
      const sourceMeta = this.sourceContentMetadata;
      if (sourceMeta?.label) {
        items.push({ label: sourceMeta.kind, value: sourceMeta.label });
      }
      if (this.selectedSource?.source_origin === 'trakt_history') {
        items.push({ label: 'Seed Origin', value: 'Trakt History' });
      }
      return items;
    },
    hasExtraRatings() {
      const source = this.selectedSource || {};
      return [
        source.imdb_rating,
        source.rt_rating,
        source.rt_user_rating,
        source.metacritic_rating,
        source.trakt_rating,
        this.modalTraktUserRating,
      ].some(value => value != null && value !== '');
    },
    modalTraktUserRating() {
      return this.traktStatus?.rating ?? null;
    },
    sourceContentMetadata() {
      return getRequestSourceContentMetadata(this.selectedSource);
    },
    requestMethodMetadata() {
      return getRequestMethodMetadata(this.selectedSource);
    },
    requestMethodLabel() {
      return this.requestMethodMetadata?.label || '';
    },
    traktStatusLabel() {
      if (this.traktStatusLoading) {
        return 'Checking...';
      }
      if (this.traktStatusError) {
        return this.traktStatusError;
      }
      const state = this.traktStatus?.watched ? 'Watched' : 'Unwatched';
      const stars = this.traktStatus?.rating_stars || (this.traktStatus?.rating ? `${this.traktStatus.rating / 2}` : '');
      return stars ? `${state} · ${stars} stars` : state;
    },
  },
  methods: {
    formatDate,
    resetDetails() {
      this.details = null;
      this.detailsLoading = false;
      this.detailsReady = false;
      this.detailsError = '';
      this.detailsRequestToken += 1;
    },
    async fetchDetailsForSelection() {
      if (!this.shouldFetchDetails) {
        this.details = null;
        this.detailsLoading = false;
        this.detailsError = '';
        this.detailsReady = true;
        return;
      }

      const requestToken = this.detailsRequestToken + 1;
      this.detailsRequestToken = requestToken;
      this.details = null;
      this.detailsLoading = true;
      this.detailsReady = false;
      this.detailsError = '';

      try {
        const response = await getRequestDetails(
          this.detailsTmdbId,
          this.selectedSource.media_type,
        );
        if (requestToken !== this.detailsRequestToken) {
          return;
        }
        const payload = response?.data || {};
        if (payload.available === false) {
          this.detailsError = 'Extra details are unavailable from Seer right now.';
          return;
        }
        this.details = payload;
      } catch (error) {
        if (requestToken !== this.detailsRequestToken) {
          return;
        }
        this.detailsError = error?.response?.data?.message || 'Could not load extra details.';
      } finally {
        if (requestToken === this.detailsRequestToken) {
          this.detailsLoading = false;
          this.detailsReady = true;
        }
      }
    },
    onSelectedRatingUpdate(value) {
      this.$emit('update:trakt-rating-stars', value);
      if (value) {
        this.$emit('rate-selected-on-trakt');
      }
    },
  },
};
</script>

<style src="@/assets/styles/traktRequestActions.css"></style>
<style src="@/assets/styles/seerRequestActions.css"></style>

<style scoped>
.request-details-modal {
  position: fixed;
  inset: 0;
  background-color: rgba(10, 14, 24, 0.82);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  z-index: 1000;
  padding: 1.5rem 1rem;
  overflow-y: auto;
}

.request-details-modal__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  min-height: 8rem;
  margin: auto;
  color: #d1d5db;
  font-size: 0.95rem;
}

.request-details-modal__loading i {
  font-size: 1.75rem;
  color: #a5b4fc;
}

.request-details-modal__content {
  position: relative;
  width: 100%;
  max-width: 1100px;
  max-height: 92vh;
  overflow: hidden auto;
  border-radius: 0.9rem;
  background: #111827;
  border: 1px solid rgba(75, 85, 99, 0.55);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
}

.request-details-modal__hero {
  position: relative;
  height: 240px;
  overflow: hidden;
}

.request-details-modal__hero-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center top;
}

.request-details-modal__hero-gradient {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.35) 0%, rgba(17, 24, 39, 1) 100%);
}

.request-details-modal__close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  z-index: 5;
  width: 2.25rem;
  height: 2.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 999px;
  background: rgba(17, 24, 39, 0.75);
  color: #d1d5db;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}

.request-details-modal__close:hover {
  background: #ef4444;
  color: #fff;
}

.request-details-modal__body {
  position: relative;
  padding: 0 1.5rem 1.5rem;
  margin-top: -4.5rem;
}

.request-details-modal__header {
  display: flex;
  gap: 1.25rem;
  align-items: flex-end;
  margin-bottom: 1.75rem;
}

.request-details-modal__poster {
  flex: 0 0 148px;
  width: 148px;
  border-radius: 0.65rem;
  overflow: hidden;
  box-shadow: 0 16px 32px rgba(0, 0, 0, 0.45);
  background: #1f2937;
}

.request-details-modal__poster-image {
  display: block;
  width: 100%;
  height: auto;
}

.request-details-modal__poster-placeholder {
  aspect-ratio: 2 / 3;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  font-size: 2rem;
}

.request-details-modal__title-block {
  flex: 1;
  min-width: 0;
  padding-bottom: 0.25rem;
}

.request-details-modal__type-badge {
  display: inline-flex;
  margin-bottom: 0.45rem;
  padding: 0.15rem 0.55rem;
  border-radius: 0.35rem;
  background: rgba(99, 102, 241, 0.18);
  color: #c7d2fe;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.request-details-modal__title {
  margin: 0;
  color: #f9fafb;
  font-size: clamp(1.5rem, 2.4vw, 2.2rem);
  font-weight: 700;
  line-height: 1.15;
}

.request-details-modal__year {
  color: #9ca3af;
  font-weight: 500;
}

.request-details-modal__original-title {
  margin: 0.35rem 0 0;
  color: #9ca3af;
  font-size: 0.92rem;
}

.request-details-modal__attributes {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
  margin-top: 0.7rem;
  color: #d1d5db;
  font-size: 0.92rem;
}

.request-details-modal__attribute-sep {
  color: #6b7280;
}

.request-details-modal__cert-badge {
  display: inline-flex;
  padding: 0.1rem 0.4rem;
  border: 1px solid #6b7280;
  border-radius: 0.35rem;
  color: #f3f4f6;
  font-size: 0.8rem;
  font-weight: 600;
}

.request-details-modal__header-ratings {
  margin-top: 0.75rem;
}

.request-details-modal__tagline {
  margin: 0.75rem 0 0;
  color: #9ca3af;
  font-size: 1rem;
  font-style: italic;
  line-height: 1.45;
}

.request-details-modal__action-strip {
  margin-top: 0.85rem;
}

.request-details-modal__main {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.5rem;
}

.request-details-modal__section {
  margin-bottom: 1.5rem;
}

.request-details-modal__section-title {
  margin: 0 0 0.75rem;
  color: #f3f4f6;
  font-size: 1.15rem;
  font-weight: 600;
}

.request-details-modal__section-title--ai {
  color: #93c5fd;
}

.request-details-modal__rationale {
  margin: 0;
  padding-left: 0.9rem;
  border-left: 3px solid #6366f1;
  color: #d1d5db;
  line-height: 1.6;
  white-space: pre-wrap;
}

.request-details-modal__rationale--ai {
  border-left-color: #60a5fa;
}

.request-details-modal__overview {
  margin: 0;
  color: #d1d5db;
  line-height: 1.7;
}

.request-details-modal__overview--muted {
  color: #9ca3af;
  font-style: italic;
}

.request-details-modal__details-error {
  margin-top: 0.65rem;
  color: #fbbf24;
  font-size: 0.9rem;
}

.request-details-modal__keyword-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.request-details-modal__keyword-tag {
  display: inline-flex;
  padding: 0.2rem 0.55rem;
  border-radius: 0.35rem;
  background: #1f2937;
  border: 1px solid #374151;
  color: #d1d5db;
  font-size: 0.78rem;
}

.request-details-modal__cast-list {
  display: flex;
  gap: 0.85rem;
  overflow-x: auto;
  padding-bottom: 0.35rem;
}

.request-details-modal__cast-card {
  flex: 0 0 92px;
  text-align: center;
}

.request-details-modal__cast-avatar {
  width: 92px;
  height: 92px;
  margin: 0 auto 0.45rem;
  border-radius: 999px;
  overflow: hidden;
  background: #1f2937;
  border: 2px solid #374151;
}

.request-details-modal__cast-photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.request-details-modal__cast-photo-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
}

.request-details-modal__cast-name {
  display: block;
  color: #f3f4f6;
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.25;
}

.request-details-modal__cast-character {
  display: block;
  margin-top: 0.15rem;
  color: #9ca3af;
  font-size: 0.72rem;
  line-height: 1.25;
}

.request-details-modal__links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
}

.request-details-modal__link-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.55rem 0.9rem;
  border-radius: 0.45rem;
  background: #1f2937;
  border: 1px solid #374151;
  color: #f3f4f6;
  text-decoration: none;
  font-size: 0.88rem;
  font-weight: 600;
  transition: border-color 0.2s ease, color 0.2s ease;
}

.request-details-modal__link-btn:hover {
  border-color: #6366f1;
  color: #c7d2fe;
}

.request-details-modal__link-btn--trailer {
  border-color: #7f1d1d;
  background: rgba(127, 29, 29, 0.35);
}

.request-details-modal__sidebar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.request-details-modal__panel {
  padding: 1rem;
  border-radius: 0.65rem;
  background: rgba(31, 41, 55, 0.72);
  border: 1px solid #374151;
}

.request-details-modal__panel--request {
  border-color: rgba(99, 102, 241, 0.35);
}

.request-details-modal__panel-title {
  margin: 0 0 0.75rem;
  color: #e5e7eb;
  font-size: 0.95rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.request-details-modal__meta-list {
  margin: 0;
}

.request-details-modal__meta-row {
  display: grid;
  grid-template-columns: 7.5rem minmax(0, 1fr);
  gap: 0.65rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid rgba(55, 65, 81, 0.65);
}

.request-details-modal__meta-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.request-details-modal__meta-row dt {
  margin: 0;
  color: #9ca3af;
  font-size: 0.82rem;
}

.request-details-modal__meta-row dd {
  margin: 0;
  color: #f3f4f6;
  font-size: 0.88rem;
  line-height: 1.4;
}

.request-details-modal__provider-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.request-details-modal__provider-pill {
  display: inline-flex;
  padding: 0.25rem 0.55rem;
  border-radius: 0.35rem;
  background: #111827;
  border: 1px solid #4b5563;
  color: #e5e7eb;
  font-size: 0.78rem;
}

.request-details-modal__related {
  margin-top: 0.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid #374151;
}

.request-details-modal__requests-list {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.request-details-modal__request-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 1rem;
  border-radius: 0.55rem;
  background: #1f2937;
  border: 1px solid #374151;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.request-details-modal__request-item:hover {
  background: #243041;
  border-color: #6366f1;
}

.request-details-modal__request-title {
  margin: 0 0 0.2rem;
  color: #f3f4f6;
  font-size: 0.95rem;
  font-weight: 600;
}

.request-details-modal__request-date {
  margin: 0.15rem 0 0;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  color: #9ca3af;
  font-size: 0.8rem;
}

.request-details-modal__request-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.8rem;
  border: none;
  border-radius: 0.45rem;
  background: #4f46e5;
  color: #fff;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
}

.request-details-modal__request-btn:hover {
  background: #6366f1;
}

.request-details-fade-enter-active,
.request-details-fade-leave-active {
  transition: opacity 0.25s ease;
}

.request-details-fade-enter-from,
.request-details-fade-leave-to {
  opacity: 0;
}

@media (min-width: 900px) {
  .request-details-modal__hero {
    height: 280px;
  }

  .request-details-modal__body {
    padding: 0 2rem 2rem;
    margin-top: -5rem;
  }

  .request-details-modal__poster {
    flex-basis: 180px;
    width: 180px;
  }

  .request-details-modal__main {
    grid-template-columns: minmax(0, 1.7fr) minmax(260px, 0.9fr);
    gap: 1.75rem;
    align-items: start;
  }
}
</style>
