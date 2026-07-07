<template>
  <div class="cleanup-page" :class="{ embedded }">
    <div v-if="!embedded" class="section-header">
      <h2><i class="fas fa-broom"></i> Cleanup Automation</h2>
      <p>Automatically delete old SuggestArr-originated request records when the item has not been favorited in your media server within a grace period.</p>
    </div>

    <div v-else class="embedded-header">
      <h3>
        <i class="fas fa-broom"></i>
        Cleanup Automation
      </h3>
      <p>Remove old SuggestArr and Seer request records when media-server users never favorite them.</p>
    </div>

    <div class="warning-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <div class="warning-content">
        <strong>Destructive action</strong>
        <span>When enabled and not in dry-run, this asks Seer to delete matched request records only. Media files are left untouched. Always run in dry-run first to verify the candidate list.</span>
      </div>
    </div>

    <div v-if="loading" class="placeholder">Loading…</div>

    <div v-else class="cleanup-panel">
      <label class="toggle-option">
        <span class="toggle-label">
          <span class="toggle-title">
            <i class="fas fa-power-off"></i>
            Enable cleanup automation
          </span>
          <span class="toggle-hint">Runs daily at 04:15 server-time. When off, no scans happen.</span>
        </span>
        <div class="toggle-switch" :class="{ on: form.enabled }" @click="form.enabled = !form.enabled">
          <div class="toggle-knob"></div>
        </div>
      </label>

      <label class="toggle-option">
        <span class="toggle-label">
          <span class="toggle-title">
            <i class="fas fa-vial"></i>
            Dry-run mode
          </span>
          <span class="toggle-hint">Logs which request records would be sent to Seer for deletion without changing Seer. Strongly recommended before flipping to real deletion.</span>
        </span>
        <div class="toggle-switch" :class="{ on: form.dry_run }" @click="form.dry_run = !form.dry_run">
          <div class="toggle-knob"></div>
        </div>
      </label>

      <div class="number-option">
        <span class="toggle-label">
          <span class="toggle-title">
            <i class="fas fa-hourglass-half"></i>
            Grace period (days)
          </span>
          <span class="toggle-hint">If a requested item has not been favorited in Plex, Jellyfin, or Emby within this many days of being requested, its request record becomes a deletion candidate.</span>
        </span>
        <input v-model.number="form.grace_days" type="number" min="1" max="365" class="number-input" />
      </div>

      <div class="actions-row">
        <button class="btn btn-primary" :disabled="saving" @click="save">
          <i :class="saving ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
          {{ saving ? 'Saving…' : 'Save settings' }}
        </button>
        <button class="btn" :disabled="running" @click="runNow(true)">
          <i :class="running && lastTrigger === 'dry' ? 'fas fa-spinner fa-spin' : 'fas fa-vial'"></i>
          Run now (dry-run)
        </button>
        <button class="btn btn-danger" :disabled="running || !form.enabled" @click="runNow(false)" title="Deletes Seer request records only">
          <i :class="running && lastTrigger === 'real' ? 'fas fa-spinner fa-spin' : 'fas fa-trash-alt'"></i>
          Run now (real)
        </button>
      </div>

      <div v-if="lastResult" class="result-banner" :class="{ ok: lastResult.status === 'success', err: lastResult.status === 'error' }">
        <i :class="lastResult.status === 'success' ? 'fas fa-check-circle' : 'fas fa-exclamation-circle'"></i>
        <span>{{ lastResult.message }}</span>
      </div>

      <div v-if="settings && settings.last_run_at" class="last-run-info">
        <span><strong>Last run:</strong> {{ formatTs(settings.last_run_at) }} · {{ settings.last_run_status || '—' }}</span>
        <div v-if="settings.last_run_summary" class="last-run-summary">{{ settings.last_run_summary }}</div>
      </div>
    </div>

    <div v-if="!loading" class="cleanup-panel seer-import-panel">
      <div class="embedded-header seer-import-header">
        <h3>
          <i class="fas fa-download"></i>
          Seer Request Import
        </h3>
        <p>Import Seer requests into SuggestArr so you can approve/decline them from the Requests page. All Seer statuses are imported; existing SuggestArr rows are skipped.</p>
      </div>

      <div class="info-banner">
        <i class="fas fa-info-circle"></i>
        <div class="warning-content">
          <strong>Seer → SuggestArr sync</strong>
          <span>Creates SuggestArr request rows for media found in Seer. Approve/decline in SuggestArr updates Seer automatically. Runs daily at 04:45 when enabled.</span>
        </div>
      </div>

      <label class="toggle-option">
        <span class="toggle-label">
          <span class="toggle-title">
            <i class="fas fa-power-off"></i>
            Enable Seer request import
          </span>
        </span>
        <div class="toggle-switch" :class="{ on: importForm.enabled }" @click="importForm.enabled = !importForm.enabled">
          <div class="toggle-knob"></div>
        </div>
      </label>

      <label class="toggle-option">
        <span class="toggle-label">
          <span class="toggle-title">
            <i class="fas fa-vial"></i>
            Import dry-run mode
          </span>
          <span class="toggle-hint">Logs which items would be imported without writing to SuggestArr.</span>
        </span>
        <div class="toggle-switch" :class="{ on: importForm.dry_run }" @click="importForm.dry_run = !importForm.dry_run">
          <div class="toggle-knob"></div>
        </div>
      </label>

      <div class="actions-row">
        <button class="btn btn-primary" :disabled="importSaving" @click="saveImport">
          <i :class="importSaving ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
          {{ importSaving ? 'Saving…' : 'Save import settings' }}
        </button>
        <button class="btn" :disabled="importRunning" @click="runImportNow(true)">
          <i :class="importRunning && lastImportTrigger === 'dry' ? 'fas fa-spinner fa-spin' : 'fas fa-vial'"></i>
          Run import (dry-run)
        </button>
        <button class="btn btn-danger" :disabled="importRunning || !importForm.enabled" @click="runImportNow(false)">
          <i :class="importRunning && lastImportTrigger === 'real' ? 'fas fa-spinner fa-spin' : 'fas fa-cloud-download-alt'"></i>
          Run import (real)
        </button>
      </div>

      <div v-if="lastImportResult" class="result-banner" :class="{ ok: lastImportResult.status === 'success', err: lastImportResult.status === 'error' }">
        <i :class="lastImportResult.status === 'success' ? 'fas fa-check-circle' : 'fas fa-exclamation-circle'"></i>
        <span>{{ lastImportResult.message }}</span>
      </div>

      <div v-if="importSettings && importSettings.last_run_at" class="last-run-info">
        <span><strong>Last import run:</strong> {{ formatTs(importSettings.last_run_at) }} · {{ importSettings.last_run_status || '—' }}</span>
        <div v-if="importSettings.last_run_summary" class="last-run-summary">{{ importSettings.last_run_summary }}</div>
      </div>
    </div>

    <div v-if="!loading" class="cleanup-panel seer-prune-panel">
      <div class="embedded-header seer-prune-header">
        <h3>
          <i class="fas fa-clipboard-check"></i>
          Seer Request Prune
        </h3>
        <p>Remove old settled Seer request records (declined, failed, available/completed, deleted). Never prunes pending or in-flight requests.</p>
      </div>

      <div class="info-banner">
        <i class="fas fa-info-circle"></i>
        <div class="warning-content">
          <strong>Record cleanup only</strong>
          <span>This deletes Seer request rows, not media files. Runs daily at 04:30 when enabled.</span>
        </div>
      </div>

      <label class="toggle-option">
        <span class="toggle-label">
          <span class="toggle-title">
            <i class="fas fa-power-off"></i>
            Enable Seer request prune
          </span>
          <span class="toggle-hint">When off, scheduled and manual prune runs are skipped unless you force a manual run.</span>
        </span>
        <div class="toggle-switch" :class="{ on: pruneForm.enabled }" @click="pruneForm.enabled = !pruneForm.enabled">
          <div class="toggle-knob"></div>
        </div>
      </label>

      <label class="toggle-option">
        <span class="toggle-label">
          <span class="toggle-title">
            <i class="fas fa-vial"></i>
            Prune dry-run mode
          </span>
          <span class="toggle-hint">Logs which Seer request records would be deleted without calling Seer.</span>
        </span>
        <div class="toggle-switch" :class="{ on: pruneForm.dry_run }" @click="pruneForm.dry_run = !pruneForm.dry_run">
          <div class="toggle-knob"></div>
        </div>
      </label>

      <label class="toggle-option">
        <span class="toggle-label">
          <span class="toggle-title">
            <i class="fas fa-exchange-alt"></i>
            Also remove matching SuggestArr rows
          </span>
          <span class="toggle-hint">Two-way sync: when a Seer request record is pruned, delete the matching SuggestArr request row too.</span>
        </span>
        <div class="toggle-switch" :class="{ on: pruneForm.sync_suggestarr }" @click="pruneForm.sync_suggestarr = !pruneForm.sync_suggestarr">
          <div class="toggle-knob"></div>
        </div>
      </label>

      <div class="retention-grid">
        <div class="number-option">
          <span class="toggle-label">
            <span class="toggle-title">Declined (days)</span>
            <span class="toggle-hint">Default 14</span>
          </span>
          <input v-model.number="pruneForm.declined_days" type="number" min="1" max="365" class="number-input" />
        </div>
        <div class="number-option">
          <span class="toggle-label">
            <span class="toggle-title">Failed (days)</span>
            <span class="toggle-hint">Default 7</span>
          </span>
          <input v-model.number="pruneForm.failed_days" type="number" min="1" max="365" class="number-input" />
        </div>
        <div class="number-option">
          <span class="toggle-label">
            <span class="toggle-title">Available / completed (days)</span>
            <span class="toggle-hint">Default 7</span>
          </span>
          <input v-model.number="pruneForm.completed_days" type="number" min="1" max="365" class="number-input" />
        </div>
        <div class="number-option">
          <span class="toggle-label">
            <span class="toggle-title">Deleted media (days)</span>
            <span class="toggle-hint">Default 3</span>
          </span>
          <input v-model.number="pruneForm.deleted_days" type="number" min="1" max="365" class="number-input" />
        </div>
      </div>

      <div class="actions-row">
        <button class="btn btn-primary" :disabled="pruneSaving" @click="savePrune">
          <i :class="pruneSaving ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
          {{ pruneSaving ? 'Saving…' : 'Save prune settings' }}
        </button>
        <button class="btn" :disabled="pruneRunning" @click="runPruneNow(true)">
          <i :class="pruneRunning && lastPruneTrigger === 'dry' ? 'fas fa-spinner fa-spin' : 'fas fa-vial'"></i>
          Run prune (dry-run)
        </button>
        <button class="btn btn-danger" :disabled="pruneRunning || !pruneForm.enabled" @click="runPruneNow(false)" title="Deletes Seer request records">
          <i :class="pruneRunning && lastPruneTrigger === 'real' ? 'fas fa-spinner fa-spin' : 'fas fa-trash-alt'"></i>
          Run prune (real)
        </button>
      </div>

      <div v-if="lastPruneResult" class="result-banner" :class="{ ok: lastPruneResult.status === 'success', err: lastPruneResult.status === 'error' }">
        <i :class="lastPruneResult.status === 'success' ? 'fas fa-check-circle' : 'fas fa-exclamation-circle'"></i>
        <span>{{ lastPruneResult.message }}</span>
      </div>

      <div v-if="pruneSettings && pruneSettings.last_run_at" class="last-run-info">
        <span><strong>Last prune run:</strong> {{ formatTs(pruneSettings.last_run_at) }} · {{ pruneSettings.last_run_status || '—' }}</span>
        <div v-if="pruneSettings.last_run_summary" class="last-run-summary">{{ pruneSettings.last_run_summary }}</div>
      </div>
    </div>

    <div class="cleanup-panel cleanup-log-panel seer-import-log-panel">
      <div class="card-header-row">
        <button class="log-title-button" @click="importLogCollapsed = !importLogCollapsed">
          <i :class="importLogCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-down'"></i>
          <span><i class="fas fa-history"></i> Seer import log</span>
          <span v-if="importLog.length" class="log-count">{{ importLog.length }}</span>
        </button>
        <div class="log-header-actions">
          <button class="btn btn-link" @click="loadImportLog" :disabled="loadingImportLog">
            <i :class="loadingImportLog ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i> Refresh
          </button>
        </div>
      </div>
      <div v-if="!importLogCollapsed && !importLog.length" class="placeholder">No Seer import actions logged yet.</div>
      <table v-else-if="!importLogCollapsed" class="log-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Title</th>
            <th>Type</th>
            <th>Action</th>
            <th>Mode</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in paginatedImportLog" :key="row.id" :class="importActionClass(row.action)">
            <td>{{ formatTs(row.ran_at) }}</td>
            <td>{{ row.title || ('tmdb:' + row.tmdb_id) }}</td>
            <td>{{ row.media_type === 'tv' ? 'TV' : 'Movie' }}</td>
            <td>{{ row.action }}</td>
            <td>{{ row.was_dry_run ? 'dry' : 'real' }}</td>
            <td>{{ row.reason }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!importLogCollapsed && totalImportLogPages > 1" class="pagination-row">
        <button class="btn btn-sm" :disabled="importLogPage <= 1" @click="importLogPage -= 1">
          <i class="fas fa-chevron-left"></i>
          Previous
        </button>
        <span>Page {{ importLogPage }} of {{ totalImportLogPages }}</span>
        <button class="btn btn-sm" :disabled="importLogPage >= totalImportLogPages" @click="importLogPage += 1">
          Next
          <i class="fas fa-chevron-right"></i>
        </button>
      </div>
    </div>

    <div class="cleanup-panel cleanup-log-panel seer-prune-log-panel">
      <div class="card-header-row">
        <button class="log-title-button" @click="pruneLogCollapsed = !pruneLogCollapsed">
          <i :class="pruneLogCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-down'"></i>
          <span><i class="fas fa-history"></i> Seer prune log</span>
          <span v-if="pruneLog.length" class="log-count">{{ pruneLog.length }}</span>
        </button>
        <div class="log-header-actions">
          <button class="btn btn-link" @click="loadPruneLog" :disabled="loadingPruneLog">
            <i :class="loadingPruneLog ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i> Refresh
          </button>
        </div>
      </div>
      <div v-if="!pruneLogCollapsed && !pruneLog.length" class="placeholder">No Seer prune actions logged yet.</div>
      <table v-else-if="!pruneLogCollapsed" class="log-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Seer ID</th>
            <th>Title</th>
            <th>Type</th>
            <th>Action</th>
            <th>Mode</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in paginatedPruneLog" :key="row.id" :class="pruneActionClass(row.action)">
            <td>{{ formatTs(row.ran_at) }}</td>
            <td>{{ row.seer_request_id ?? '—' }}</td>
            <td>{{ row.title || ('tmdb:' + row.tmdb_id) }}</td>
            <td>{{ row.media_type === 'tv' ? 'TV' : 'Movie' }}</td>
            <td>{{ row.action }}</td>
            <td>{{ row.was_dry_run ? 'dry' : 'real' }}</td>
            <td>{{ row.reason }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!pruneLogCollapsed && totalPruneLogPages > 1" class="pagination-row">
        <button class="btn btn-sm" :disabled="pruneLogPage <= 1" @click="pruneLogPage -= 1">
          <i class="fas fa-chevron-left"></i>
          Previous
        </button>
        <span>Page {{ pruneLogPage }} of {{ totalPruneLogPages }}</span>
        <button class="btn btn-sm" :disabled="pruneLogPage >= totalPruneLogPages" @click="pruneLogPage += 1">
          Next
          <i class="fas fa-chevron-right"></i>
        </button>
      </div>
    </div>

    <div class="cleanup-panel cleanup-log-panel">
      <div class="card-header-row">
        <button class="log-title-button" @click="logCollapsed = !logCollapsed">
          <i :class="logCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-down'"></i>
          <span><i class="fas fa-history"></i> Audit log</span>
          <span v-if="log.length" class="log-count">{{ log.length }}</span>
        </button>
        <div class="log-header-actions">
          <button class="btn btn-link" @click="loadLog" :disabled="loadingLog">
            <i :class="loadingLog ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i> Refresh
          </button>
        </div>
      </div>
      <div v-if="!logCollapsed && !log.length" class="placeholder">No cleanup actions logged yet.</div>
      <table v-else-if="!logCollapsed" class="log-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Title</th>
            <th>Type</th>
            <th>Action</th>
            <th>Mode</th>
            <th>★</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in paginatedLog" :key="row.id" :class="actionClass(row.action)">
            <td>{{ formatTs(row.ran_at) }}</td>
            <td>{{ row.title || ('tmdb:' + row.tmdb_id) }}</td>
            <td>{{ row.media_type === 'tv' ? 'TV' : 'Movie' }}</td>
            <td>{{ row.action }}</td>
            <td>{{ row.was_dry_run ? 'dry' : 'real' }}</td>
            <td>{{ row.user_rating ?? '—' }}</td>
            <td>{{ row.reason }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!logCollapsed && totalLogPages > 1" class="pagination-row">
        <button class="btn btn-sm" :disabled="logPage <= 1" @click="logPage -= 1">
          <i class="fas fa-chevron-left"></i>
          Previous
        </button>
        <span>Page {{ logPage }} of {{ totalLogPages }}</span>
        <button class="btn btn-sm" :disabled="logPage >= totalLogPages" @click="logPage += 1">
          Next
          <i class="fas fa-chevron-right"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import {
  getCleanupSettings,
  setCleanupSettings,
  runCleanupNow,
  getCleanupLog,
  getSeerPruneSettings,
  setSeerPruneSettings,
  runSeerPruneNow,
  getSeerPruneLog,
  getSeerImportSettings,
  setSeerImportSettings,
  runSeerImportNow,
  getSeerImportLog,
} from '@/api/api.js';

export default {
  name: 'SettingsCleanup',

  props: {
    embedded: {
      type: Boolean,
      default: false,
    },
  },

  data() {
    return {
      loading: true,
      loadingLog: false,
      loadingPruneLog: false,
      saving: false,
      running: false,
      pruneSaving: false,
      pruneRunning: false,
      lastTrigger: null,
      lastPruneTrigger: null,
      settings: null,
      form: { enabled: false, dry_run: true, grace_days: 7 },
      loadingImportLog: false,
      importSaving: false,
      importRunning: false,
      lastImportTrigger: null,
      importSettings: null,
      importForm: { enabled: false, dry_run: true },
      importLog: [],
      importLogCollapsed: true,
      importLogPage: 1,
      lastImportResult: null,
      pruneSettings: null,
      pruneForm: {
        enabled: false,
        dry_run: true,
        sync_suggestarr: false,
        declined_days: 14,
        failed_days: 7,
        completed_days: 7,
        deleted_days: 3,
      },
      log: [],
      pruneLog: [],
      logCollapsed: true,
      pruneLogCollapsed: true,
      logPage: 1,
      pruneLogPage: 1,
      logPageSize: 25,
      lastResult: null,
      lastPruneResult: null,
    };
  },

  computed: {
    totalLogPages() {
      return Math.max(1, Math.ceil(this.log.length / this.logPageSize));
    },

    paginatedLog() {
      const start = (this.logPage - 1) * this.logPageSize;
      return this.log.slice(start, start + this.logPageSize);
    },

    totalPruneLogPages() {
      return Math.max(1, Math.ceil(this.pruneLog.length / this.logPageSize));
    },

    paginatedPruneLog() {
      const start = (this.pruneLogPage - 1) * this.logPageSize;
      return this.pruneLog.slice(start, start + this.logPageSize);
    },

    totalImportLogPages() {
      return Math.max(1, Math.ceil(this.importLog.length / this.logPageSize));
    },

    paginatedImportLog() {
      const start = (this.importLogPage - 1) * this.logPageSize;
      return this.importLog.slice(start, start + this.logPageSize);
    },
  },

  methods: {
    async loadSettings() {
      this.loading = true;
      try {
        const [cleanupRes, pruneRes, importRes] = await Promise.all([
          getCleanupSettings(),
          getSeerPruneSettings(),
          getSeerImportSettings(),
        ]);
        this.settings = cleanupRes.data.settings;
        this.form = {
          enabled: !!this.settings.enabled,
          dry_run: !!this.settings.dry_run,
          grace_days: Number(this.settings.grace_days) || 7,
        };
        this.pruneSettings = pruneRes.data.settings;
        this.pruneForm = {
          enabled: !!this.pruneSettings.enabled,
          dry_run: !!this.pruneSettings.dry_run,
          sync_suggestarr: !!this.pruneSettings.sync_suggestarr,
          declined_days: Number(this.pruneSettings.declined_days) || 14,
          failed_days: Number(this.pruneSettings.failed_days) || 7,
          completed_days: Number(this.pruneSettings.completed_days) || 7,
          deleted_days: Number(this.pruneSettings.deleted_days) || 3,
        };
        this.importSettings = importRes.data.settings;
        this.importForm = {
          enabled: !!this.importSettings.enabled,
          dry_run: !!this.importSettings.dry_run,
        };
      } catch (err) {
        this.lastResult = { status: 'error', message: err.response?.data?.message || 'Failed to load settings.' };
      } finally {
        this.loading = false;
      }
    },

    async save() {
      this.saving = true;
      this.lastResult = null;
      try {
        const res = await setCleanupSettings(this.form);
        this.settings = res.data.settings;
        this.lastResult = { status: 'success', message: 'Settings saved.' };
      } catch (err) {
        this.lastResult = { status: 'error', message: err.response?.data?.message || 'Failed to save.' };
      } finally {
        this.saving = false;
      }
    },

    async savePrune() {
      this.pruneSaving = true;
      this.lastPruneResult = null;
      try {
        const res = await setSeerPruneSettings(this.pruneForm);
        this.pruneSettings = res.data.settings;
        this.lastPruneResult = { status: 'success', message: 'Prune settings saved.' };
      } catch (err) {
        this.lastPruneResult = { status: 'error', message: err.response?.data?.message || 'Failed to save prune settings.' };
      } finally {
        this.pruneSaving = false;
      }
    },

    async saveImport() {
      this.importSaving = true;
      this.lastImportResult = null;
      try {
        const res = await setSeerImportSettings(this.importForm);
        this.importSettings = res.data.settings;
        this.lastImportResult = { status: 'success', message: 'Import settings saved.' };
      } catch (err) {
        this.lastImportResult = { status: 'error', message: err.response?.data?.message || 'Failed to save import settings.' };
      } finally {
        this.importSaving = false;
      }
    },

    async runNow(dryRun) {
      if (this.running) return;
      this.running = true;
      this.lastTrigger = dryRun ? 'dry' : 'real';
      this.lastResult = null;
      try {
        const res = await runCleanupNow(dryRun);
        const r = res.data.result || {};
        this.lastResult = { status: 'success', message: `Run complete (${dryRun ? 'dry-run' : 'real'}): ${r.summary || r.message || 'done'}` };
        await this.loadSettings();
        await this.loadLog();
      } catch (err) {
        this.lastResult = { status: 'error', message: err.response?.data?.message || 'Run failed.' };
      } finally {
        this.running = false;
        this.lastTrigger = null;
      }
    },

    async runPruneNow(dryRun) {
      if (this.pruneRunning) return;
      this.pruneRunning = true;
      this.lastPruneTrigger = dryRun ? 'dry' : 'real';
      this.lastPruneResult = null;
      try {
        const res = await runSeerPruneNow(dryRun);
        const r = res.data.result || {};
        this.lastPruneResult = {
          status: 'success',
          message: `Prune complete (${dryRun ? 'dry-run' : 'real'}): ${r.summary || r.message || 'done'}`,
        };
        await this.loadSettings();
        await this.loadPruneLog();
      } catch (err) {
        this.lastPruneResult = { status: 'error', message: err.response?.data?.message || 'Prune run failed.' };
      } finally {
        this.pruneRunning = false;
        this.lastPruneTrigger = null;
      }
    },

    async runImportNow(dryRun) {
      if (this.importRunning) return;
      this.importRunning = true;
      this.lastImportTrigger = dryRun ? 'dry' : 'real';
      this.lastImportResult = null;
      try {
        const res = await runSeerImportNow(dryRun);
        const r = res.data.result || {};
        this.lastImportResult = {
          status: 'success',
          message: `Import complete (${dryRun ? 'dry-run' : 'real'}): ${r.summary || r.message || 'done'}`,
        };
        await this.loadSettings();
        await this.loadImportLog();
      } catch (err) {
        this.lastImportResult = { status: 'error', message: err.response?.data?.message || 'Import run failed.' };
      } finally {
        this.importRunning = false;
        this.lastImportTrigger = null;
      }
    },

    async loadLog() {
      this.loadingLog = true;
      try {
        const res = await getCleanupLog(200);
        this.log = res.data.log || [];
        if (this.logPage > this.totalLogPages) {
          this.logPage = this.totalLogPages;
        }
      } catch (err) {
        // non-fatal
      } finally {
        this.loadingLog = false;
      }
    },

    async loadPruneLog() {
      this.loadingPruneLog = true;
      try {
        const res = await getSeerPruneLog(200);
        this.pruneLog = res.data.log || [];
        if (this.pruneLogPage > this.totalPruneLogPages) {
          this.pruneLogPage = this.totalPruneLogPages;
        }
      } catch (err) {
        // non-fatal
      } finally {
        this.loadingPruneLog = false;
      }
    },

    async loadImportLog() {
      this.loadingImportLog = true;
      try {
        const res = await getSeerImportLog(200);
        this.importLog = res.data.log || [];
        if (this.importLogPage > this.totalImportLogPages) {
          this.importLogPage = this.totalImportLogPages;
        }
      } catch (err) {
        // non-fatal
      } finally {
        this.loadingImportLog = false;
      }
    },

    formatTs(ts) {
      if (!ts) return '—';
      const raw = String(ts).trim();
      const hasTimezone = /(?:z|gmt|[+-]\d{2}:?\d{2})$/i.test(raw);
      const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
      const date = new Date(hasTimezone ? normalized : `${normalized}Z`);
      if (Number.isNaN(date.getTime())) {
        return raw;
      }
      return date.toLocaleString();
    },

    actionClass(action) {
      if (action === 'deleted' || action === 'would_delete') return 'row-delete';
      if (action === 'kept_favorited') return 'row-kept';
      if (action === 'error' || action === 'delete_failed') return 'row-error';
      return '';
    },

    pruneActionClass(action) {
      if (action === 'deleted' || action === 'would_delete' || action === 'synced_suggestarr_row') return 'row-delete';
      if (action === 'error' || action === 'delete_failed') return 'row-error';
      return '';
    },

    importActionClass(action) {
      if (action === 'imported' || action === 'would_import') return 'row-delete';
      if (action === 'error') return 'row-error';
      return '';
    },
  },

  mounted() {
    this.loadSettings();
    this.loadLog();
    this.loadImportLog();
    this.loadPruneLog();
  },
};
</script>

<style scoped>
.cleanup-page { padding: 0; }
.cleanup-page.embedded {
  grid-column: 1 / -1;
  background: rgba(220, 38, 38, 0.06);
  border: 1px solid rgba(220, 38, 38, 0.22);
  border-radius: var(--border-radius-md, 8px);
  padding: 1.5rem;
}
.section-header h2 { font-size: 1.6rem; margin-bottom: 0.25rem; }
.section-header p { color: var(--color-text-muted, #aaa); }
.embedded-header {
  margin-bottom: 1rem;
}
.embedded-header h3 {
  font-size: 1.2rem;
  margin: 0 0 0.35rem;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.embedded-header p {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.95rem;
}

.warning-banner {
  display: flex; gap: 12px; align-items: flex-start;
  background: rgba(231, 138, 0, 0.1); border: 1px solid rgba(231, 138, 0, 0.4);
  padding: 12px; border-radius: 8px; margin: 16px 0;
}
.warning-banner i { color: #e78a00; font-size: 1.1rem; margin-top: 2px; }
.info-banner {
  display: flex; gap: 12px; align-items: flex-start;
  background: rgba(52, 152, 219, 0.1); border: 1px solid rgba(52, 152, 219, 0.35);
  padding: 12px; border-radius: 8px; margin: 16px 0;
}
.info-banner i { color: #3498db; font-size: 1.1rem; margin-top: 2px; }
.seer-prune-panel { margin-top: 20px; }
.seer-import-panel { margin-top: 20px; }
.seer-prune-header { margin-bottom: 0; }
.seer-import-header { margin-bottom: 0; }
.retention-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px 16px;
  margin-top: 8px;
}
.retention-grid .number-option { border-bottom: none; padding: 8px 0; }
.warning-content strong { display: block; margin-bottom: 2px; }

.cleanup-panel {
  background: var(--color-card, #2a2a2a);
  border: 1px solid var(--color-border, #444);
  border-radius: 8px; padding: 16px; margin-bottom: 20px;
}
.embedded .cleanup-panel {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
}
.cleanup-log-panel {
  overflow-x: auto;
}

.toggle-option, .number-option {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 0; border-bottom: 1px solid var(--color-border-soft, #333);
}
.toggle-option:last-of-type, .number-option:last-of-type { border-bottom: none; }
.toggle-label { display: flex; flex-direction: column; gap: 4px; max-width: 70%; }
.toggle-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-primary, #fff);
}
.toggle-title i {
  width: 16px;
  color: var(--color-text-muted, #aaa);
  text-align: center;
}
.toggle-hint { color: var(--color-text-muted, #888); font-size: 0.85rem; }

.number-input {
  width: 90px; padding: 6px 8px;
  background: var(--color-bg, #1f1f1f); border: 1px solid var(--color-border, #444);
  border-radius: 6px; color: var(--color-text-primary, white);
}

.actions-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.btn {
  padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 0.9rem;
  border: 1px solid var(--color-border, #444); background: transparent; color: var(--color-text-primary, #ddd);
  display: inline-flex; align-items: center; gap: 6px;
}
.btn:hover:not(:disabled) { border-color: #888; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #3498db; border-color: #3498db; color: white; }
.btn-danger { background: #c0392b; border-color: #c0392b; color: white; }
.btn-link { background: transparent; border: none; color: #3498db; padding: 4px 8px; }
.btn-sm { padding: 6px 10px; font-size: 0.82rem; }

.result-banner {
  margin-top: 12px; padding: 10px; border-radius: 6px;
  display: flex; gap: 8px; align-items: center;
}
.result-banner.ok { background: rgba(46, 204, 113, 0.12); border: 1px solid #2ecc71; color: #2ecc71; }
.result-banner.err { background: rgba(231, 76, 60, 0.12); border: 1px solid #e74c3c; color: #e74c3c; }

.last-run-info { margin-top: 12px; font-size: 0.9rem; color: var(--color-text-muted, #aaa); }
.last-run-summary { margin-top: 4px; font-family: monospace; font-size: 0.82rem; }

.card-header-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }
.log-title-button {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: transparent;
  border: 0;
  color: var(--color-text-primary, #fff);
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
  padding: 4px 0;
}
.log-title-button span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.log-count {
  min-width: 24px;
  justify-content: center;
  border-radius: 999px;
  padding: 2px 8px;
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-muted, #aaa);
  font-size: 0.78rem;
  font-weight: 600;
}
.log-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.placeholder { color: var(--color-text-muted, #888); padding: 8px 0; font-style: italic; }

.log-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.log-table th, .log-table td {
  text-align: left; padding: 6px 8px;
  border-bottom: 1px solid var(--color-border-soft, #333);
}
.log-table th { color: var(--color-text-muted, #aaa); font-weight: 600; }
.log-table .row-delete { color: #e67e22; }
.log-table .row-kept { color: #2ecc71; }
.log-table .row-error { color: #e74c3c; }
.pagination-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 12px;
  color: var(--color-text-muted, #aaa);
  font-size: 0.85rem;
}
</style>
