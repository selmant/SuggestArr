<template>
  <div class="trakt-list-filters">
    <div class="form-group">
      <label>List Source</label>
      <div class="source-selector">
        <button
          type="button"
          class="source-btn"
          :class="{ active: listSource === 'public_url' }"
          @click="setListSource('public_url')"
        >
          <i class="fas fa-link"></i>
          Public URL
        </button>
        <button
          type="button"
          class="source-btn"
          :class="{ active: listSource === 'linked_user', disabled: !linkedModeAvailable }"
          :disabled="!linkedModeAvailable"
          :title="linkedModeUnavailableReason"
          @click="setListSource('linked_user')"
        >
          <i class="fas fa-user-lock"></i>
          Linked User
        </button>
      </div>
      <small v-if="!linkedModeAvailable" class="form-help">{{ linkedModeUnavailableReason }}</small>
    </div>

    <div v-if="listSource === 'public_url'" class="form-group">
      <label for="traktListUrl">Trakt List URL</label>
      <div class="list-url-row">
        <input
          id="traktListUrl"
          v-model="localListUrl"
          type="text"
          class="form-control"
          placeholder="https://trakt.tv/users/username/lists/my-list"
          @input="clearResolvedList"
        />
        <button
          type="button"
          class="btn btn-outline btn-sm"
          :disabled="!localListUrl.trim() || isResolving"
          @click="validatePublicList"
        >
          <i :class="isResolving ? 'fas fa-spinner fa-spin' : 'fas fa-check'"></i>
          Validate
        </button>
      </div>
      <small class="form-help">
        Paste any public Trakt list URL, slug, or numeric list id.
      </small>
      <div v-if="resolvedList" class="resolved-list">
        <i class="fas fa-list"></i>
        <span>{{ resolvedList.name }} ({{ resolvedList.preview_count }} items previewed)</span>
      </div>
      <div v-if="resolveError" class="resolve-error">{{ resolveError }}</div>
    </div>

    <template v-else>
      <div class="form-group">
        <label id="trakt-list-user-label">Trakt Account</label>
        <div v-if="isLoading" class="empty-state-inline">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading Trakt users...</span>
        </div>
        <div v-else-if="connectedUsers.length === 0" class="empty-state-inline">
          <i class="fas fa-user-slash"></i>
          <span>No linked Trakt users available.</span>
        </div>
        <div v-else class="users-list" role="radiogroup" aria-labelledby="trakt-list-user-label">
          <button
            v-for="user in connectedUsers"
            :key="user.external_user_id"
            type="button"
            class="user-item"
            :class="{ selected: selectedUserId === user.external_user_id }"
            role="radio"
            :aria-checked="selectedUserId === user.external_user_id"
            @click="selectUser(user)"
          >
            <div class="user-avatar"><i class="fas fa-user"></i></div>
            <div class="user-meta">
              <span class="user-name">{{ user.external_username || user.external_user_id }}</span>
              <span class="user-sub">Trakt connected</span>
            </div>
            <i v-if="selectedUserId === user.external_user_id" class="fas fa-check check-icon"></i>
          </button>
        </div>
      </div>

      <div v-if="selectedUserId" class="form-group">
        <label for="traktListSelect">List</label>
        <div v-if="listsLoading" class="empty-state-inline">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading lists...</span>
        </div>
        <select
          v-else
          id="traktListSelect"
          v-model="selectedListKey"
          class="form-control"
          @change="onListSelected"
        >
          <option value="">Select a list...</option>
          <option
            v-for="list in availableLists"
            :key="listKey(list)"
            :value="listKey(list)"
          >
            {{ list.name }}{{ list.item_count != null ? ` (${list.item_count})` : '' }}
          </option>
        </select>
      </div>
    </template>

    <div class="form-group">
      <label>Dedup Mode</label>
      <div class="source-selector">
        <button
          type="button"
          class="source-btn"
          :class="{ active: dedupMode === 'global' }"
          @click="setDedupMode('global')"
        >
          Global
        </button>
        <button
          type="button"
          class="source-btn"
          :class="{ active: dedupMode === 'per_list' }"
          @click="setDedupMode('per_list')"
        >
          Per List
        </button>
      </div>
      <small class="form-help">
        <template v-if="dedupMode === 'global'">
          Skip anything already requested, downloaded, or pending in Seer.
        </template>
        <template v-else>
          Only skip items already seen on this list. New list entries can be requested even if removed elsewhere.
        </template>
      </small>
    </div>

    <div v-if="dedupMode === 'global'" class="form-group">
      <label>Request Behavior</label>
      <div class="toggle-options">
        <div class="toggle-item">
          <BaseCheckbox v-model="localFilters.exclude_downloaded">
            <span class="toggle-label-modal">
              <i class="fas fa-download"></i>
              Exclude downloaded content
            </span>
          </BaseCheckbox>
        </div>
        <div class="toggle-item">
          <BaseCheckbox v-model="localFilters.exclude_requested">
            <span class="toggle-label-modal">
              <i class="fas fa-clock"></i>
              Exclude requested content
            </span>
          </BaseCheckbox>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import BaseCheckbox from '@/components/common/BaseCheckbox.vue';
import { getMediaUserTraktLists, resolveTraktList } from '@/api/api';

export default {
  name: 'TraktListFilters',
  components: { BaseCheckbox },
  props: {
    modelValue: {
      type: Object,
      default: () => ({})
    },
    showAdvanced: {
      type: Boolean,
      default: false
    },
    traktConfigured: {
      type: Boolean,
      default: false
    },
    connectedUsers: {
      type: Array,
      default: () => []
    },
    isLoading: {
      type: Boolean,
      default: false
    }
  },
  emits: ['update:modelValue'],
  data() {
    return {
      isUpdatingFromParent: false,
      localListUrl: '',
      localFilters: {
        list_source: 'public_url',
        list_url: '',
        list_ref: '',
        watchlist: false,
        dedup_mode: 'global',
        exclude_downloaded: true,
        exclude_requested: true
      },
      availableLists: [],
      listsLoading: false,
      selectedListKey: '',
      isResolving: false,
      resolvedList: null,
      resolveError: ''
    };
  },
  computed: {
    listSource() {
      return this.localFilters.list_source || 'public_url';
    },
    dedupMode() {
      return this.localFilters.dedup_mode || 'global';
    },
    selectedUserId() {
      const ids = this.modelValue.user_ids || [];
      return ids.length ? ids[0] : '';
    },
    linkedModeAvailable() {
      return this.traktConfigured && this.connectedUsers.length > 0;
    },
    linkedModeUnavailableReason() {
      if (!this.traktConfigured) {
        return 'Configure Trakt app credentials in Services to use linked-user lists.';
      }
      if (this.connectedUsers.length === 0) {
        return 'Link at least one media user to Trakt to use private lists or watchlist.';
      }
      return '';
    }
  },
  watch: {
    modelValue: {
      handler(newVal) {
        this.isUpdatingFromParent = true;
        this.localFilters = {
          list_source: newVal.filters?.list_source || 'public_url',
          list_url: newVal.filters?.list_url || '',
          list_ref: newVal.filters?.list_ref || newVal.filters?.list_slug || '',
          watchlist: newVal.filters?.watchlist === true,
          dedup_mode: newVal.filters?.dedup_mode || 'global',
          exclude_downloaded: newVal.filters?.exclude_downloaded ?? true,
          exclude_requested: newVal.filters?.exclude_requested ?? true
        };
        this.localListUrl = this.localFilters.list_url || '';
        this.syncSelectedListKey();
        this.$nextTick(() => {
          this.isUpdatingFromParent = false;
        });
      },
      deep: true,
      immediate: true
    },
    localFilters: {
      handler(newVal) {
        if (!this.isUpdatingFromParent) {
          this.emitFilters(newVal);
        }
      },
      deep: true
    },
    connectedUsers: {
      handler(users) {
        if (this.listSource === 'linked_user' && !this.selectedUserId && users.length === 1) {
          this.selectUser(users[0]);
        }
      },
      immediate: true
    }
  },
  mounted() {
    if (this.listSource === 'linked_user' && this.selectedUserId) {
      this.loadListsForSelectedUser();
    }
  },
  methods: {
    listKey(list) {
      if (list.is_watchlist || list.slug === 'watchlist') {
        return 'watchlist';
      }
      return list.slug || list.id;
    },
    syncSelectedListKey() {
      if (this.localFilters.watchlist) {
        this.selectedListKey = 'watchlist';
        return;
      }
      this.selectedListKey = this.localFilters.list_ref || '';
    },
    emitFilters(filters) {
      this.$emit('update:modelValue', {
        ...this.modelValue,
        filters: {
          ...this.modelValue.filters,
          ...filters
        }
      });
    },
    setListSource(source) {
      if (source === 'linked_user' && !this.linkedModeAvailable) {
        return;
      }
      this.localFilters = {
        ...this.localFilters,
        list_source: source,
        list_url: source === 'public_url' ? this.localListUrl : '',
        list_ref: source === 'linked_user' ? this.localFilters.list_ref : '',
        watchlist: source === 'linked_user' ? this.localFilters.watchlist : false
      };
      if (source === 'linked_user') {
        if (!this.selectedUserId && this.connectedUsers.length === 1) {
          this.selectUser(this.connectedUsers[0]);
        }
      } else {
        this.$emit('update:modelValue', {
          ...this.modelValue,
          user_ids: [],
          filters: {
            ...this.modelValue.filters,
            ...this.localFilters
          }
        });
      }
    },
    setDedupMode(mode) {
      this.localFilters = { ...this.localFilters, dedup_mode: mode };
    },
    clearResolvedList() {
      this.resolvedList = null;
      this.resolveError = '';
      this.localFilters = { ...this.localFilters, list_url: this.localListUrl };
    },
    async validatePublicList() {
      this.isResolving = true;
      this.resolveError = '';
      this.resolvedList = null;
      try {
        const response = await resolveTraktList(this.localListUrl.trim());
        this.resolvedList = response.data?.list || null;
        this.localFilters = {
          ...this.localFilters,
          list_url: this.localListUrl.trim()
        };
      } catch (error) {
        this.resolveError = error.response?.data?.message || 'Could not resolve Trakt list';
      } finally {
        this.isResolving = false;
      }
    },
    selectUser(user) {
      this.$emit('update:modelValue', {
        ...this.modelValue,
        user_ids: [user.external_user_id]
      });
      this.loadListsForSelectedUser(user);
    },
    async loadListsForSelectedUser(user = null) {
      const selected = user || this.connectedUsers.find(
        (entry) => entry.external_user_id === this.selectedUserId
      );
      if (!selected) {
        this.availableLists = [];
        return;
      }
      this.listsLoading = true;
      try {
        const response = await getMediaUserTraktLists(
          selected.provider,
          selected.external_user_id
        );
        this.availableLists = response.data?.lists || [];
        this.syncSelectedListKey();
      } catch (error) {
        this.availableLists = [];
        this.resolveError = error.response?.data?.message || 'Failed to load Trakt lists';
      } finally {
        this.listsLoading = false;
      }
    },
    onListSelected() {
      const selected = this.availableLists.find(
        (list) => this.listKey(list) === this.selectedListKey
      );
      const isWatchlist = this.selectedListKey === 'watchlist' || selected?.is_watchlist;
      this.localFilters = {
        ...this.localFilters,
        list_ref: isWatchlist ? '' : (selected?.slug || selected?.id || this.selectedListKey),
        watchlist: isWatchlist
      };
    }
  }
};
</script>

<style scoped>
.trakt-list-filters {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.source-selector {
  display: flex;
  gap: 0.5rem;
}

.source-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  padding: 0.65rem 0.75rem;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.source-btn.active {
  border-color: var(--color-primary);
  background: var(--color-primary-alpha-10);
  color: var(--color-text-primary);
}

.source-btn.disabled,
.source-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.list-url-row {
  display: flex;
  gap: 0.5rem;
}

.list-url-row .form-control {
  flex: 1;
}

.form-control,
.form-help,
.empty-state-inline,
.resolved-list,
.resolve-error,
.users-list,
.user-item,
.toggle-options {
  font-size: 0.8rem;
}

.form-control {
  width: 100%;
  padding: 0.65rem 0.875rem;
  background: var(--color-bg-interactive);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
}

.form-help {
  display: block;
  margin-top: 0.35rem;
  color: var(--color-text-muted);
}

.resolved-list {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  color: var(--color-success, #22c55e);
}

.resolve-error {
  margin-top: 0.5rem;
  color: var(--color-error-light);
}

.empty-state-inline {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px dashed var(--color-border-light);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
}

.users-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.user-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.user-item.selected {
  border-color: var(--color-primary);
  background: var(--color-primary-alpha-10);
}

.user-avatar {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-interactive);
}

.user-meta {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  flex: 1;
}

.user-name {
  color: var(--color-text-primary);
}

.user-sub,
.check-icon {
  color: var(--color-text-muted);
}

.check-icon {
  color: var(--color-primary);
}

.toggle-options {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.toggle-item {
  display: flex;
  align-items: center;
}

.toggle-label-modal {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}
</style>
