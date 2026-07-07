<template>
    <div class="request-container" :class="{ 'static-bg-active': config.ENABLE_STATIC_BACKGROUND }">
      <div class="background-container">
        <template v-if="!config.ENABLE_STATIC_BACKGROUND">
          <div
            class="background-layer"
            :class="activeBg === 'bg1' ? 'bg-visible' : 'bg-hidden'"
            :style="{ backgroundImage: 'url(' + bg1Url + ')' }"
          ></div>
          <div
            class="background-layer"
            :class="activeBg === 'bg2' ? 'bg-visible' : 'bg-hidden'"
            :style="{ backgroundImage: 'url(' + bg2Url + ')' }"
          ></div>
        </template>
        <div
          v-if="config.ENABLE_STATIC_BACKGROUND"
          class="background-layer static-bg"
          :style="{ backgroundColor: config.STATIC_BACKGROUND_COLOR }"
        ></div>
      </div>
      <div class="background-overlay"></div>
      <div class="request-content">
        <!-- Header -->
        <div class="request-header">
          <!-- Back Button -->
          <div class="header-top">
            <button @click="goHome" class="back-button">
              <i class="fas fa-arrow-left"></i>
              <span>Back to Home</span>
            </button>
            <div class="header-spacer"></div>
          </div>

          <div class="header-content">
            <h1 class="page-title">Request History</h1>
            <p class="page-subtitle">Track your content requests and viewing patterns</p>
          </div>
        </div>

        <!-- View Toggle -->
        <div class="view-toggle-section">
          <div class="view-toggle">
            <button 
              @click="viewMode = 'by-content'" 
              :class="{ active: viewMode === 'by-content' }"
              class="view-toggle-btn">
              <i class="fas fa-film"></i>
              <span>By Watched Content</span>
              <span class="view-count">{{ totalSources }}</span>
            </button>
            <button
              @click="viewMode = 'all-requests'"
              :class="{ active: viewMode === 'all-requests' }"
              class="view-toggle-btn">
              <i class="fas fa-list"></i>
              <span>All Requests</span>
              <span class="view-count">{{ totalRequests }}</span>
            </button>
            <button
              @click="switchToAiRequests"
              :class="{ active: viewMode === 'ai-requests' }"
              class="view-toggle-btn">
              <i class="fas fa-magic"></i>
              <span>AI Requests</span>
              <span class="view-count">{{ aiRequestsTotal }}</span>
            </button>
            <button
              @click="switchToArchived"
              :class="{ active: viewMode === 'archived' }"
              class="view-toggle-btn">
              <i class="fas fa-archive"></i>
              <span>Archived</span>
              <span class="view-count">{{ archivedTotal }}</span>
            </button>
          </div>
        </div>

        <!-- Filters & Search Bar -->
        <div class="filters-section">
          <!-- Container per affiancare filtri e search -->
          <div class="filters-search-container">
            <!-- Search Bar (affiancata ai filtri) -->
            <div class="search-wrapper">
              <i class="fas fa-search search-icon"></i>
              <input 
                v-model="searchQuery" 
                type="text" 
                :placeholder="viewMode === 'by-content' ? 'Search content...' : 'Search requests...'" 
                class="search-input" />
              <span v-if="searchQuery" @click="searchQuery = ''" class="clear-search">
                <i class="fas fa-times"></i>
              </span>
            </div>
            <!-- Filter Buttons -->
            <div class="filter-bar">
              <!-- Sort By -->
              <BaseDropdown
                v-model="sortBy"
                :options="sortOptions"
                placeholder="Select sort order"
                :disabled="loading"
                id="sortBy"
              />
            
              <!-- Media Type Filter -->
              <BaseDropdown
                v-model="mediaTypeFilter"
                :options="mediaTypeOptions"
                placeholder="Select media type"
                :disabled="loading"
                id="mediaType"
              />

              <!-- Seer Status Filter -->
              <BaseDropdown
                v-if="viewMode !== 'archived'"
                v-model="seerStatusFilter"
                :options="seerStatusFilterOptions"
                placeholder="Select Seer status"
                :disabled="loading"
                id="seerStatus"
              />
            
              <!-- Clear Filters -->
              <button 
                v-if="hasActiveFilters" 
                @click="clearFilters" 
                class="clear-filters-btn">
                <i class="fas fa-undo"></i>
                <span>Reset</span>
              </button>
            </div>
          </div>
        
          <!-- Search Results Count -->
          <div class="search-results-count" v-if="hasActiveFilters">
            Found {{ activeFilteredCount }} result(s)
          </div>
        </div>

        <!-- View: By Content Watched -->
        <div v-if="showPageLoader" class="loading-initial">
          <div class="spinner"></div>
          <p>{{ pageLoaderMessage }}</p>
        </div>

        <template v-else>
          <div v-if="viewMode === 'by-content'" key="by-content">
            <transition-group 
              name="fade-slide" 
              tag="div"
              class="content-grid">
              <div 
                v-for="source in filteredAndSortedSources" 
                :key="source.id" 
                class="content-card">
                
                <!-- Card Header with Backdrop -->
                <div class="card-header" @click="openModal(source)">
                  <div class="backdrop-container">
                    <img
                      v-if="source.backdrop_path && !source.visual"
                      :src="source.backdrop_path"
                      :alt="source.title"
                      class="backdrop-image" />
                    <div
                      v-else-if="source.visual"
                      class="source-visual-backdrop"
                      :class="source.visual.key"
                      :style="{ background: source.visual.gradient }">
                      <i :class="source.visual.icon" class="source-visual-icon"></i>
                    </div>

                    <!-- Logo overlay -->
                    <div class="backdrop-overlay">
                      <img
                        v-if="source.logo_path && !source.visual"
                        :src="source.logo_path"
                        alt="Logo"
                        class="content-logo" />
                      <h3 v-else class="content-title-overlay">{{ source.title }}</h3>
                    </div>
                  </div>
                </div>

                <!-- Card Body -->
                <div class="card-body">
                  <!-- Badges -->
                  <div class="badge-container">
                    <span v-if="shouldShowSourceMediaBadge(source)" class="badge badge-media">
                      <i :class="source.media_type === 'movie' ? 'fas fa-film' : 'fas fa-tv'"></i>
                      {{ source.media_type.toUpperCase() }}
                    </span>
                    <RatingBadges
                      v-if="!source.visual"
                      layout="horizontal"
                      :item="source"
                      :badge-settings="ratingBadgeSettings"
                      :compact="true" />
                    <span v-if="!source.visual && source.release_date" class="badge badge-date">
                      <i class="fas fa-calendar"></i>
                      {{ source.release_date }}
                    </span>
                  </div>

                  <!-- Toggle Requests -->
                  <button 
                    @click="toggleSourceRequests(source)"
                    class="toggle-requests-btn">
                    <i :class="source.showRequests ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
                    <span>{{ source.showRequests ? 'Hide' : 'View' }} Requested Media ({{ source.total_request_count || source.requests.length }})</span>
                    <span v-if="source.has_more_requests && source.showRequests" class="requests-partial-note">
                      Showing {{ source.requests.length }} of {{ source.total_request_count }}
                    </span>
                  </button>

                  <!-- Requests List -->
                  <transition name="expand">
                    <div v-show="source.showRequests" class="requests-list">
                      <div 
                        v-for="request in source.requests" 
                        :key="request.request_id"
                        class="request-item"
                        @click="openModal(request)">
                        <img 
                          v-if="request.poster_path" 
                          :src="request.poster_path" 
                          :alt="request.title"
                          class="request-poster" />
                        <div class="request-info">
                          <h4 class="request-title">{{ request.title }}</h4>
                          <p class="request-date">
                            <i class="fas fa-clock"></i>
                            Requested {{ formatDate(request.requested_at) }}
                          </p>
                        </div>
                        <i class="fas fa-chevron-right request-arrow"></i>
                      </div>
                    </div>
                  </transition>
                </div>
              </div>
            </transition-group>
          </div>

          <!-- View: AI Requests -->
          <div v-else-if="viewMode === 'ai-requests'" key="ai-requests">
            <transition-group
              name="fade-slide"
              tag="div"
              class="requests-grid">
              <RequestPosterCard
                v-for="item in filteredAiRequests"
                :key="item.request_id"
                :item="item"
                :badge-settings="ratingBadgeSettings"
                source-mode="ai"
                placeholder-icon="fas fa-magic"
                :show-missing-rating="false"
                @select="openModal($event, true)" />
            </transition-group>
            <div
              v-if="aiRequestsHasMore"
              ref="loadMoreTriggerAi"
              class="load-more-trigger"
              :class="{ 'load-more-trigger--idle': !loading }">
              <template v-if="loading">
                <div class="spinner-small"></div>
                <p>Loading more...</p>
              </template>
            </div>
          </div>

          <!-- View: All Requests -->
          <div v-else-if="viewMode === 'all-requests'" key="all-requests">
            <div class="requests-grid">
              <RequestPosterCard
                v-for="request in filteredAndSortedRequests" 
                :key="request.request_id"
                :item="request"
                :badge-settings="ratingBadgeSettings"
                :trakt-user-rating="getTraktStatus(request)?.rating"
                v-bind="{ ...posterTraktProps(request), ...posterSeerProps(request) }"
                @set-trakt-watched="setTraktWatchedFor(request, $event)"
                @rate-trakt="rateRequestOnTraktFor(request, $event)"
                @approve-seer="approveFor(request)"
                @decline-seer="declineFor(request)"
                @select="openModal" />
            </div>


          </div>

          <!-- View: Archived -->
          <div v-else key="archived" class="archived-view">
            <table class="archived-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Title</th>
                  <th>Type</th>
                  <th>Requested</th>
                  <th>Archived</th>
                  <th>Seer status</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="request in filteredArchivedRequests" :key="`${request.media_type}-${request.request_id}`">
                  <td class="archived-poster-cell">
                    <img
                      v-if="request.poster_path"
                      :src="request.poster_path"
                      :alt="request.title"
                      class="archived-poster" />
                    <div v-else class="archived-poster archived-poster-placeholder">
                      <i :class="request.media_type === 'tv' ? 'fas fa-tv' : 'fas fa-film'"></i>
                    </div>
                  </td>
                  <td>
                    <div class="archived-title">{{ request.title || ('TMDB ' + request.request_id) }}</div>
                    <div v-if="request.source_origin" class="archived-subtitle">{{ request.source_origin }}</div>
                  </td>
                  <td>{{ request.media_type === 'tv' ? 'TV' : 'Movie' }}</td>
                  <td>{{ formatDate(request.requested_at) }}</td>
                  <td>{{ formatDate(request.archived_at) }}</td>
                  <td>
                    <span class="archived-status-badge">{{ formatSeerStatusLabel(request.seer_status) }}</span>
                  </td>
                  <td>{{ request.archive_reason || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

        <div
          v-if="hasMoreData && viewMode !== 'ai-requests' && viewMode !== 'archived'"
          :ref="viewMode === 'by-content' ? 'loadMoreTrigger' : 'loadMoreTriggerRequests'"
          class="load-more-trigger"
          :class="{ 'load-more-trigger--idle': !loading }">
          <template v-if="loading">
            <div class="spinner-small"></div>
            <p>Loading more requests...</p>
          </template>
        </div>
        <!-- No Results -->
        <div v-if="viewMode === 'archived' && filteredArchivedRequests.length === 0 && !loading" class="no-results">
          <i class="fas fa-archive text-6xl mb-4"></i>
          <h3>No archived requests</h3>
          <p>Requests archived by cleanup automation will appear here.</p>
        </div>
        <div v-else-if="viewMode !== 'ai-requests' && viewMode !== 'archived' && (viewMode === 'by-content' ? filteredAndSortedSources : filteredAndSortedRequests).length === 0 && !loading" class="no-results">
          <i class="fas fa-inbox text-6xl mb-4"></i>
          <h3>No {{ viewMode === 'by-content' ? 'content' : 'requests' }} found</h3>
          <p v-if="hasActiveFilters">Try adjusting your filters</p>
          <p v-else>Start watching content to see suggestions here</p>
        </div>
        <div
          v-if="hasMoreData && viewMode === 'archived'"
          ref="loadMoreTriggerArchived"
          class="load-more-trigger"
          :class="{ 'load-more-trigger--idle': !loading }">
          <template v-if="loading">
            <div class="spinner-small"></div>
            <p>Loading more archived requests...</p>
          </template>
        </div>
        <div v-if="viewMode === 'ai-requests' && filteredAiRequests.length === 0 && !loading" class="no-results">
          <i class="fas fa-magic text-6xl mb-4"></i>
          <h3>No AI Search requests yet</h3>
          <p>Use the <strong>AI Search</strong> tab to discover and request content.</p>
        </div>

        </template>

        <Footer />
      </div>

      <RequestDetailsModal
        :show="showModal"
        :selected-source="selectedSource"
        :trakt-modal-target="getTraktModalTarget(selectedSource)"
        :can-show-related-trakt="canShowRelatedTrakt"
        :trakt-status="traktStatus"
        :trakt-status-loading="traktStatusLoading"
        :trakt-action-loading="traktActionLoading"
        :trakt-status-error="traktStatusError"
        :trakt-rating-stars="traktRatingStars"
        :get-trakt-status="getTraktStatus"
        :get-trakt-rating-stars="getTraktRatingStars"
        :get-trakt-inline-label="getTraktInlineLabel"
        :is-trakt-busy="isTraktBusy"
        :seer-modal-target="getSeerModalTarget(selectedSource)"
        :can-show-related-seer="canShowRelatedSeer"
        :can-action-seer="canActionSeer"
        :seer-status="seerStatus"
        :seer-status-loading="seerStatusLoading"
        :seer-action-loading="seerActionLoading"
        :seer-status-error="seerStatusError"
        :get-seer-status="getSeerStatus"
        :get-seer-inline-label="getSeerInlineLabel"
        :is-seer-busy="isSeerBusy"
        :badge-settings="ratingBadgeSettings"
        @close="closeModal"
        @select-related="openModal"
        @set-trakt-watched="setTraktWatchedForSource(selectedSource, $event)"
        @update:trakt-rating-stars="traktRatingStars = $event"
        @rate-selected-on-trakt="rateSelectedOnTraktForSource(selectedSource)"
        @set-related-trakt-watched="(item, watched) => setTraktWatchedFor(item, watched)"
        @rate-related-on-trakt="(item, stars) => rateRequestOnTraktFor(item, stars)"
        @approve-seer="approveForSource(selectedSource)"
        @decline-seer="declineForSource(selectedSource)"
        @approve-related-seer="approveFor"
        @decline-related-seer="declineFor" />
    </div>
</template>

<script>
import '@/assets/styles/requestsPage.css';
import axios from "axios";
import { useBackgroundImage } from '@/composables/useBackgroundImage';
import { useRequestTraktActions } from '@/composables/useRequestTraktActions';
import { useRequestSeerActions } from '@/composables/useRequestSeerActions';
import Footer from './AppFooter.vue';
import BaseDropdown from '@/components/common/BaseDropdown.vue';
import RequestPosterCard from '@/components/common/RequestPosterCard.vue';
import RequestDetailsModal from '@/components/common/RequestDetailsModal.vue';
import RatingBadges from '@/components/common/RatingBadges.vue';
import { formatDate } from '@/utils/dateUtils.js';
import { SEER_STATUS_FILTER_OPTIONS, matchesSeerStatusFilter, formatSeerStatusLabel } from '@/utils/seerStatus.js';
import { getRequestSourceVisual } from '@/utils/jobTypeVisuals.js';
import { getRatingBadgeSettings } from '@/utils/ratingBadgeConfig.js';
import {
  getAiSearchRequests,
  getAutomationRequestsFlat,
  getAutomationRequestsBySource,
  getArchivedRequests,
} from '@/api/api.js';

export default {
  name: "RequestsPage",
  components: {
    Footer,
    BaseDropdown,
    RequestPosterCard,
    RequestDetailsModal,
    RatingBadges,
  },
  setup() {
    const background = useBackgroundImage();
    const trakt = useRequestTraktActions();
    const seer = useRequestSeerActions();
    return {
      ...background,
      ...trakt,
      ...seer,
      setTraktModalTargetResolver: trakt.setModalTargetResolver,
      setSeerModalTargetResolver: seer.setModalTargetResolver,
      setSeerStatusChangeHandler: seer.setSeerStatusChangeHandler,
    };
  },
  data() {
    return {
      defaultImages: ["/images/default1.jpg", "/images/default2.jpg", "/images/default3.jpg"],
      currentDefaultImageIndex: 0,
      config: {},
      sources: [],
      flatRequests: [],
      flatCurrentPage: 0,
      flatTotalPages: 1,
      flatPerPage: 24,
      viewMode: 'all-requests',
      searchQuery: "",
      sortBy: 'date-desc',
      mediaTypeFilter: 'all',
      seerStatusFilter: 'all',
      showModal: false,
      selectedSource: null,
      loading: false,
      hasCompletedInitialLoad: false,
      filterIntegrationLoading: false,
      filterIntegrationToken: 0,
      currentPage: 1,
      totalPages: 1,
      observer: null,
      retryTimeout: null,
      totalSourcesCount: 0,
      totalRequestsCount: 0,
      // AI Requests state
      aiRequests: [],
      aiRequestsTotal: 0,
      aiRequestsPage: 1,
      aiRequestsTotalPages: 1,
      aiObserver: null,
      archivedRequests: [],
      archivedTotal: 0,
      archivedPage: 1,
      archivedTotalPages: 1,
      archivedPerPage: 24,
      sortOptions: [
        { value: 'date-desc', label: 'Date (Newest)' },
        { value: 'date-asc', label: 'Date (Oldest)' },
        { value: 'title-asc', label: 'Title (A-Z)' },
        { value: 'title-desc', label: 'Title (Z-A)' },
        { value: 'rating-desc', label: 'Rating (High-Low)' },
        { value: 'rating-asc', label: 'Rating (Low-High)' }
      ],
      mediaTypeOptions: [
        { value: 'all', label: 'All Types' },
        { value: 'movie', label: 'Movies' },
        { value: 'tv', label: 'TV Shows' }
      ],
      seerStatusFilterOptions: SEER_STATUS_FILTER_OPTIONS,
    };
  },
  computed: {
    hasActiveFilters() {
      return this.sortBy !== 'date-desc'
        || this.mediaTypeFilter !== 'all'
        || this.seerStatusFilter !== 'all'
        || Boolean(this.searchQuery);
    },

    activeFilteredCount() {
      if (this.viewMode === 'by-content') {
        return this.filteredAndSortedSources.length;
      }
      if (this.viewMode === 'ai-requests') {
        return this.filteredAiRequests.length;
      }
      if (this.viewMode === 'archived') {
        return this.filteredArchivedRequests.length;
      }
      return this.filteredAndSortedRequests.length;
    },

    totalRequests() {
      return this.totalRequestsCount || this.sources.reduce((sum, source) => sum + source.requests.length, 0);
    },

    totalSources() {
      return this.totalSourcesCount || this.sources.length;
    },

    ratingBadgeSettings() {
      return getRatingBadgeSettings(this.config);
    },

    allRequestsFlat() {
      return this.sources.flatMap(source => 
        source.requests.map(req => ({
          ...req,
          source_title: source.title,
          source_id: source.id,
          source_poster: source.poster_path,
          source_backdrop: source.backdrop_path,
          source_logo: source.logo_path,
        }))
      );
    },

    filteredSources() {
      const query = this.searchQuery.toLowerCase();
      let filtered = this.sources.map((source) => {
        const requests = this.filterRequestList(source.requests);
        if (requests.length === 0) {
          return null;
        }
        return { ...source, requests };
      }).filter(Boolean);

      if (query) {
        filtered = filtered.filter((source) => {
          const sourceMatch = source.title && source.title.toLowerCase().includes(query);
          const requestMatch = source.requests.some((request) =>
            request.title && request.title.toLowerCase().includes(query)
          );
          return sourceMatch || requestMatch;
        });
      }

      return filtered;
    },

    filteredAllRequests() {
      const query = this.searchQuery.toLowerCase();
      const baseList = this.viewMode === 'all-requests'
        ? this.flatRequests
        : this.allRequestsFlat;
      let filtered = this.filterRequestList(baseList);

      if (query) {
        filtered = filtered.filter(request =>
          (request.title && request.title.toLowerCase().includes(query)) ||
          (request.source_title && request.source_title.toLowerCase().includes(query))
        );
      }

      return filtered;
    },

    filteredAiRequests() {
      const query = this.searchQuery.toLowerCase();
      let filtered = this.filterRequestList(this.aiRequests);

      if (query) {
        filtered = filtered.filter((request) =>
          request.title && request.title.toLowerCase().includes(query)
        );
      }

      return filtered;
    },

    filteredArchivedRequests() {
      const query = this.searchQuery.toLowerCase();
      let filtered = [...(this.archivedRequests || [])];

      if (this.mediaTypeFilter !== 'all') {
        filtered = filtered.filter((request) => request.media_type === this.mediaTypeFilter);
      }

      if (query) {
        filtered = filtered.filter((request) =>
          (request.title && request.title.toLowerCase().includes(query))
          || (request.source_origin && request.source_origin.toLowerCase().includes(query))
        );
      }

      return filtered;
    },

    filteredAndSortedSources() {
      return this.filteredSources;
    },

    filteredAndSortedRequests() {
      return this.filteredAllRequests;
    },

    hasMoreData() {
      if (this.viewMode === 'ai-requests') {
        return this.aiRequestsPage < this.aiRequestsTotalPages;
      }
      if (this.viewMode === 'archived') {
        return this.archivedPage < this.archivedTotalPages;
      }
      if (this.viewMode === 'all-requests') {
        return this.flatCurrentPage < this.flatTotalPages;
      }
      return this.currentPage < this.totalPages;
    },

    showInitialLoader() {
      return !this.hasCompletedInitialLoad;
    },

    showPageLoader() {
      return this.showInitialLoader || this.filterIntegrationLoading;
    },

    pageLoaderMessage() {
      if (this.filterIntegrationLoading) {
        return 'Applying Seer filter...';
      }
      return 'Loading your requests...';
    },

    isInitialLoad() {
      if (this.viewMode === 'ai-requests') {
        return this.aiRequests.length === 0;
      }
      if (this.viewMode === 'archived') {
        return this.archivedRequests.length === 0;
      }
      if (this.viewMode === 'all-requests') {
        return this.flatRequests.length === 0;
      }
      return this.sources.length === 0;
    },

    aiRequestsHasMore() {
      return this.aiRequestsPage < this.aiRequestsTotalPages;
    },
  },
  watch: {
    viewMode(newMode, oldMode) {
      if (newMode === 'ai-requests') {
        if (this.aiRequests.length === 0) {
          this.fetchAiRequests(1);
        }
        return;
      }
      if (newMode === 'archived') {
        if (this.archivedRequests.length === 0) {
          this.fetchArchivedRequests(1);
        }
        return;
      }
      if (newMode !== oldMode) {
        if (newMode === 'all-requests' && this.flatRequests.length === 0) {
          this.fetchFlatRequests(1);
        } else if (newMode === 'by-content' && this.sources.length === 0) {
          this.fetchRequests(1);
        }
      }
      this.$nextTick(() => {
        setTimeout(() => {
          this.initObserver();
        }, 400);
      });
    },

    sortBy() {
      if (this.viewMode === 'ai-requests') {
        this.aiRequests = [];
        this.aiRequestsPage = 1;
        this.fetchAiRequests(1);
        return;
      }
      if (this.viewMode === 'archived') {
        this.archivedRequests = [];
        this.archivedPage = 1;
        this.fetchArchivedRequests(1);
        return;
      }
      this.resetAndReload();
    },
    
    mediaTypeFilter() {
      this.reinitObserverAfterFilter();
    },

    seerStatusFilter() {
      void this.refreshSeerFilterStatuses();
    },
    
    searchQuery() {
      this.$nextTick(() => {
        this.initObserver();
      });
    },

    defaultTraktUserId(newUserId, oldUserId) {
      if (!newUserId || newUserId === oldUserId) {
        return;
      }
      const requests = this.viewMode === 'all-requests'
        ? this.flatRequests
        : this.allRequestsFlat;
      if (requests.length > 0) {
        void this.prefetchRequestIntegrationStatusesAsync(requests);
      }
    },
  },
  methods: {
    mapRequestRatings(request) {
      return {
        request_id: request.request_id,
        title: request.title,
        media_type: request.media_type,
        requested_at: request.requested_at,
        overview: request.overview,
        poster_path: request.poster_path,
        release_date: request.release_date,
        rating: request.rating,
        imdb_id: request.imdb_id,
        imdb_rating: request.imdb_rating,
        imdb_votes: request.imdb_votes,
        rt_rating: request.rt_rating,
        rt_user_rating: request.rt_user_rating,
        metacritic_rating: request.metacritic_rating,
        trakt_rating: request.trakt_rating,
        trakt_votes: request.trakt_votes,
        logo_path: request.logo_path,
        backdrop_path: request.backdrop_path,
        rationale: request.rationale,
        user_id: request.user_id,
        user_name: request.user_name,
        source_origin: request.source_origin,
        seer_status: request.seer_status,
        seer_request_status: request.seer_request_status,
        seer_media_status: request.seer_media_status,
        source_id: request.source_id,
        source_title: request.source_title,
        source_poster_path: request.source_poster_path,
        source_backdrop_path: request.source_backdrop_path,
        source_logo_path: request.source_logo_path,
      };
    },

    mapSourceRatings(sourceData) {
      return {
        imdb_id: sourceData.imdb_id,
        imdb_rating: sourceData.imdb_rating,
        imdb_votes: sourceData.imdb_votes,
        rt_rating: sourceData.rt_rating,
        rt_user_rating: sourceData.rt_user_rating,
        metacritic_rating: sourceData.metacritic_rating,
        trakt_rating: sourceData.trakt_rating,
        trakt_votes: sourceData.trakt_votes,
        rating: sourceData.rating,
      };
    },

    refreshConfigFromStorage() {
      const savedConfig = localStorage.getItem('suggestarr_config');
      if (!savedConfig) {
        return;
      }
      try {
        this.config = JSON.parse(savedConfig) || {};
      } catch (e) {
        console.error('❌ Failed to parse saved config:', e);
      }
    },

    formatDate,
    formatSeerStatusLabel,

    filterRequestList(requests) {
      let filtered = [...(requests || [])];

      if (this.mediaTypeFilter !== 'all') {
        filtered = filtered.filter((request) => request.media_type === this.mediaTypeFilter);
      }

      if (this.seerStatusFilter !== 'all') {
        filtered = filtered.filter((request) => this.requestMatchesSeerStatusFilter(request));
      }

      return filtered;
    },

    requestMatchesSeerStatusFilter(request) {
      const status = this.getSeerStatus(request)?.seer_status || request?.seer_status;
      return matchesSeerStatusFilter(status, this.seerStatusFilter);
    },

    loadedRequestsForFilters() {
      if (this.viewMode === 'all-requests') {
        return this.flatRequests;
      }
      if (this.viewMode === 'by-content') {
        return this.allRequestsFlat;
      }
      return [];
    },

    async refreshSeerFilterStatuses() {
      if (
        this.seerStatusFilter === 'all'
        || this.viewMode === 'archived'
        || this.viewMode === 'ai-requests'
      ) {
        this.filterIntegrationLoading = false;
        this.reinitObserverAfterFilter();
        return;
      }

      const requests = this.loadedRequestsForFilters();
      if (!requests.length) {
        this.filterIntegrationLoading = false;
        this.reinitObserverAfterFilter();
        return;
      }

      const token = ++this.filterIntegrationToken;
      this.filterIntegrationLoading = true;
      try {
        await this.prefetchRequestIntegrationStatusesAsync(requests, {
          forceTrakt: false,
          forceSeer: true,
        });
      } catch (error) {
        console.warn('Could not refresh statuses for Seer filter:', error);
      } finally {
        if (token === this.filterIntegrationToken) {
          this.filterIntegrationLoading = false;
          this.reinitObserverAfterFilter();
        }
      }
    },

    getSourceVisual(source) {
      return source?.visual ?? getRequestSourceVisual(source);
    },

    shouldShowSourceMediaBadge(source) {
      if (!source?.media_type) {
        return false;
      }
      if (source.visual && this.sourceHasMixedMediaTypes(source)) {
        return false;
      }
      return true;
    },

    sourceHasMixedMediaTypes(source) {
      const types = new Set((source?.requests || []).map((request) => request.media_type));
      return types.size > 1;
    },

    resetAndReload() {
      this.cleanupObserver();
      this.retryCount = 0;

      if (this.viewMode === 'all-requests') {
        this.flatRequests = [];
        this.flatCurrentPage = 0;
        this.flatTotalPages = 1;
        this.fetchFlatRequests(1);
        return;
      }

      this.sources = [];
      this.currentPage = 0;
      this.totalPages = 1;
      this.fetchRequests(1);
    },

    async toggleSourceRequests(source) {
      if (source.showRequests) {
        source.showRequests = false;
        return;
      }
      source.showRequests = true;
      if (source.has_more_requests && !source.requestsFullyLoaded) {
        await this.loadAllSourceRequests(source);
      }
      void this.prefetchRequestIntegrationStatusesAsync(source.requests || []);
    },

    async loadAllSourceRequests(source) {
      if (source.loadingMoreRequests) {
        return;
      }
      source.loadingMoreRequests = true;
      try {
        let page = 2;
        const perPage = 50;
        const totalPages = Math.max(
          1,
          Math.ceil((source.total_request_count || source.requests.length) / perPage),
        );
        while (page <= totalPages) {
          const response = await getAutomationRequestsBySource(
            source.id,
            page,
            perPage,
            this.sortBy,
          );
          const extraRequests = response.data?.data?.requests || [];
          source.requests = [
            ...source.requests,
            ...extraRequests.map((request) => this.mapRequestRatings(request)),
          ];
          page += 1;
        }
        source.requestsFullyLoaded = true;
        source.has_more_requests = false;
        void this.prefetchRequestIntegrationStatusesAsync(source.requests || []);
      } catch (error) {
        console.error('Failed to load remaining source requests:', error);
        this.$toast.open({
          message: 'Could not load all requests for this source',
          type: 'error',
          duration: 5000,
          position: 'top-right',
        });
      } finally {
        source.loadingMoreRequests = false;
      }
    },

    switchToAiRequests() {
      this.viewMode = 'ai-requests';
      if (this.aiRequests.length === 0) {
        this.fetchAiRequests(1);
      }
    },

    switchToArchived() {
      this.viewMode = 'archived';
      if (this.archivedRequests.length === 0) {
        this.fetchArchivedRequests(1);
      }
    },

    async fetchArchivedRequests(page = 1) {
      if ((page > this.archivedTotalPages && page > 1) || this.loading) {
        return;
      }

      this.loading = true;
      try {
        const response = await getArchivedRequests(page, this.archivedPerPage, this.sortBy);
        const { data, total, total_pages: totalPages } = response.data;

        if (page === 1) {
          this.archivedRequests = data;
          this.archivedTotal = total;
        } else {
          this.archivedRequests = [...this.archivedRequests, ...data];
        }

        this.archivedPage = page;
        this.archivedTotalPages = totalPages;

        this.$nextTick(() => {
          setTimeout(() => this.initArchivedObserver(), 150);
        });
      } catch (error) {
        console.error('Failed to fetch archived requests:', error);
      } finally {
        this.loading = false;
      }
    },

    initArchivedObserver() {
      if (this.observer) {
        this.observer.disconnect();
        this.observer = null;
      }
      if (!this.hasMoreData || this.viewMode !== 'archived') {
        return;
      }
      this.$nextTick(() => {
        const trigger = this.$refs.loadMoreTriggerArchived;
        if (trigger) {
          this.observer = new IntersectionObserver(async (entries) => {
            if (entries[0].isIntersecting && !this.loading) {
              await this.fetchArchivedRequests(this.archivedPage + 1);
            }
          }, { rootMargin: '300px', threshold: 0 });
          this.observer.observe(trigger);
        }
      });
    },

    async fetchAiRequests(page = 1) {
      if (this.loading) return;
      this.loading = true;
      try {
        const response = await getAiSearchRequests(page, 12, this.sortBy);
        const { data, total, total_pages } = response.data;
        if (page === 1) {
          this.aiRequests = data;
          this.aiRequestsTotal = total;
        } else {
          this.aiRequests = [...this.aiRequests, ...data];
        }
        this.aiRequestsPage = page;
        this.aiRequestsTotalPages = total_pages;
        if (data?.length) {
          void this.prefetchRequestIntegrationStatusesAsync(data);
        }
        this.$nextTick(() => {
          setTimeout(() => this.initAiObserver(), 150);
        });
      } catch (error) {
        console.error('❌ Failed to fetch AI search requests:', error);
      } finally {
        this.loading = false;
      }
    },

    initAiObserver() {
      if (this.aiObserver) {
        this.aiObserver.disconnect();
        this.aiObserver = null;
      }
      if (!this.aiRequestsHasMore) return;
      this.$nextTick(() => {
        const trigger = this.$refs.loadMoreTriggerAi;
        if (trigger) {
          this.aiObserver = new IntersectionObserver(async (entries) => {
            if (entries[0].isIntersecting && !this.loading) {
              await this.fetchAiRequests(this.aiRequestsPage + 1);
            }
          }, { rootMargin: '300px', threshold: 0 });
          this.aiObserver.observe(trigger);
        }
      });
    },

    clearFilters() {
      this.sortBy = 'date-desc';
      this.mediaTypeFilter = 'all';
      this.seerStatusFilter = 'all';
      this.searchQuery = '';
    },



    async observeIntersection(entries) {
      if (entries[0].isIntersecting && !this.loading) {
        if (this.viewMode === 'archived') {
          await this.fetchArchivedRequests(this.archivedPage + 1);
          return;
        }
        if (this.viewMode === 'all-requests') {
          await this.fetchFlatRequests(this.flatCurrentPage + 1);
          return;
        }
        await this.fetchRequests(this.currentPage + 1);
      }
    },

    reinitObserverAfterFilter() {
      this.$nextTick(() => {
        setTimeout(() => {
          this.initObserver();
        }, 100);
      });
    },

    initObserver() {
      // Cleanup existing observer
      this.cleanupObserver();

      if (!this.hasMoreData) {
        console.log('❌ No more data to load');
        return;
      }

      this.$nextTick(() => {
        const triggerRef = this.viewMode === 'by-content'
          ? this.$refs.loadMoreTrigger
          : this.viewMode === 'archived'
            ? this.$refs.loadMoreTriggerArchived
            : this.$refs.loadMoreTriggerRequests;

        if (triggerRef) {
          this.observer = new IntersectionObserver(this.observeIntersection, {
            root: null,
            rootMargin: '300px', 
            threshold: 0,
          });
          this.observer.observe(triggerRef);
        } else {
          console.warn('⚠️ Trigger ref not found, retrying...');
          this.retryTimeout = setTimeout(() => {
            this.initObserver();
          }, 200);
        }
      });
    },

    cleanupObserver() {
      if (this.observer) {
        this.observer.disconnect();
        this.observer = null;
      }
      if (this.retryTimeout) {
        clearTimeout(this.retryTimeout);
        this.retryTimeout = null;
      }
    },

    async fetchFlatRequests(page = 1) {
      if ((page > this.flatTotalPages && page > 1) || this.loading) {
        return;
      }

      this.loading = true;
      try {
        const response = await getAutomationRequestsFlat(page, this.flatPerPage, this.sortBy);
        const { data, total, total_pages: totalPages } = response.data;
        const mapped = data.map((request) => this.mapRequestRatings(request));

        if (page === 1) {
          this.flatRequests = mapped;
          this.totalRequestsCount = total;
          await this.prefetchRequestIntegrationStatusesAsync(mapped);
        } else {
          this.flatRequests = [...this.flatRequests, ...mapped];
          void this.prefetchRequestIntegrationStatusesAsync(mapped);
        }

        this.flatCurrentPage = page;
        this.flatTotalPages = totalPages;

        this.$nextTick(() => {
          setTimeout(() => {
            this.initObserver();
          }, 150);
        });
      } catch (error) {
        console.error('Failed to fetch flat requests:', error);
        this.$toast.open({
          message: 'Failed to load requests',
          type: 'error',
          duration: 5000,
          position: 'top-right',
        });
      } finally {
        this.loading = false;
        if (page === 1) {
          this.hasCompletedInitialLoad = true;
        }
      }
    },

    async fetchRequests(page = 1) {
      if (page > this.totalPages || this.loading) {
        console.log('⛔ Fetch blocked - page:', page, 'loading:', this.loading);
        return;
      }
      
      this.loading = true;
      
      try {
        const params = {
          page: page,
          sort_by: this.sortBy,
        };

        const response = await axios.get('/api/automation/requests', { params });
        const { data, total_pages, total_sources, total_requests } = response.data;
        
        if (page === 1) {
          this.totalSourcesCount = total_sources;
          this.totalRequestsCount = total_requests;
        }
        
        const newSources = data.map((sourceData) => ({
          id: sourceData.source_id,
          title: sourceData.source_title,
          release_date: sourceData.source_release_date,
          overview: sourceData.source_overview,
          poster_path: sourceData.source_poster_path,
          rating: sourceData.rating,
          ...this.mapSourceRatings(sourceData),
          media_type: sourceData.media_type,
          showRequests: false,
          logo_path: sourceData.logo_path,
          backdrop_path: sourceData.backdrop_path,
          visual: getRequestSourceVisual({
            id: sourceData.source_id,
            title: sourceData.source_title,
          }),
          requests: sourceData.requests.map((request) => this.mapRequestRatings(request)),
          total_request_count: sourceData.total_request_count || sourceData.requests.length,
          has_more_requests: Boolean(sourceData.has_more_requests),
          requestsFullyLoaded: !sourceData.has_more_requests,
          loadingMoreRequests: false,
        }));

        this.sources = [...this.sources, ...newSources];
        this.totalPages = total_pages;
        this.currentPage = page;

        const nestedRequests = newSources.flatMap((source) => source.requests || []);
        if (nestedRequests.length) {
          if (page === 1) {
            await this.prefetchRequestIntegrationStatusesAsync(nestedRequests);
          } else {
            void this.prefetchRequestIntegrationStatusesAsync(nestedRequests);
          }
        }

        this.$nextTick(() => {
          setTimeout(() => {
            this.initObserver();
          }, 150);
        });

      } catch (error) {
        console.error("❌ Failed to fetch requests:", error);
        this.$toast.open({
          message: '❌ Failed to load requests',
          type: 'error',
          duration: 5000,
          position: 'top-right'
        });
      } finally {
        this.loading = false;
        if (page === 1) {
          this.hasCompletedInitialLoad = true;
        }
      }
    },

    goHome() {
      this.$router.push({ name: "Home" });
    },

    prefetchRequestIntegrationStatuses(requests, { forceTrakt = true } = {}) {
      this.prefetchPosterTraktStatuses(requests, { force: forceTrakt });
      this.prefetchPosterSeerStatuses(requests);
    },

    async prefetchRequestIntegrationStatusesAsync(requests, { forceTrakt = true, forceSeer = true } = {}) {
      if (!requests?.length) {
        return;
      }
      try {
        await this.loadTraktDefaults();
        await Promise.all([
          this.prefetchPosterTraktStatusesAsync(requests, { force: forceTrakt, silent: true }),
          this.prefetchPosterSeerStatusesAsync(requests, { force: forceSeer, silent: true }),
        ]);
      } catch (error) {
        console.warn('Could not prefetch request integration statuses:', error);
      }
    },

    syncListedRequestSeerStatus(item, status) {
      const requestId = String(item?.request_id || '');
      const seerStatus = status?.seer_status;
      if (!requestId || !seerStatus) {
        return;
      }

      const updateRequest = (request) => {
        if (String(request?.request_id || '') === requestId) {
          request.seer_status = seerStatus;
        }
      };

      this.flatRequests.forEach(updateRequest);
      this.sources.forEach((source) => {
        (source.requests || []).forEach(updateRequest);
      });
    },

    refreshModalIntegrationStatuses(source) {
      this.loadTraktStatusForSource(source, { force: true });
      this.loadSeerStatusForSource(source, { force: true });

      for (const request of (source?.requests || [])) {
        if (this.canShowRelatedTrakt(request)) {
          this.loadTraktStatusFor(request, { force: true });
        }
        if (this.canShowRelatedSeer(request)) {
          this.loadSeerStatusFor(request, { force: true });
        }
      }
    },

    openModal(source, isAiRequest = false) {
      this.selectedSource = { ...source, _isAiRequest: isAiRequest };
      this.applyTraktStatus(null);
      this.applySeerStatus(null);
      this.traktStatusError = '';
      this.seerStatusError = '';
      this.showModal = true;
      document.body.style.overflow = 'hidden';
      this.$nextTick(() => {
        this.refreshModalIntegrationStatuses(this.selectedSource);
      });
    },

    closeModal() {
      this.showModal = false;
      this.selectedSource = null;
      this.applyTraktStatus(null);
      this.applySeerStatus(null);
      this.traktStatusError = '';
      this.seerStatusError = '';
      document.body.style.overflow = 'auto';
    },
  },
  mounted() {
    this.refreshConfigFromStorage();
    window.addEventListener('storage', this.refreshConfigFromStorage);

    const tab = this.$route?.query?.tab;
    if (tab === 'archived') {
      this.viewMode = 'archived';
    }

    this.$nextTick(async () => {
      if (this.config.ENABLE_STATIC_BACKGROUND) {
        // do not start rotation
      } else {
        this.startBackgroundImageRotation();
      }

      await this.loadTraktDefaults();
      this.setTraktModalTargetResolver(() => this.getTraktModalTarget(this.selectedSource));
      this.setSeerModalTargetResolver(() => this.getSeerModalTarget(this.selectedSource));
      this.setSeerStatusChangeHandler((item, status) => {
        this.syncListedRequestSeerStatus(item, status);
      });
      if (this.viewMode === 'archived') {
        await this.fetchArchivedRequests(1);
      } else if (this.viewMode === 'all-requests') {
        await this.fetchFlatRequests(1);
      } else {
        await this.fetchRequests(1);
      }

      this.$nextTick(() => {
        this.initObserver();
      });
    });
  },

  beforeUnmount() {
    window.removeEventListener('storage', this.refreshConfigFromStorage);
    this.stopBackgroundImageRotation();
    this.cleanupObserver();
    document.body.style.overflow = 'auto';
  },
};
</script>
