<template>
  <div class="settings-page">
    <!-- Fixed header -->
    <div class="settings-header pa-6 pb-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h5 font-weight-bold">Settings</div>
          <div class="text-body-2 text-medium-emphasis">
            Manage connections, integrations, and AI configuration
          </div>
        </div>
        <v-btn
          color="primary"
          prepend-icon="mdi-content-save-outline"
          :loading="settingsStore.saving"
          @click="save"
        >
          Save Changes
        </v-btn>
      </div>

      <!-- Alerts in header area -->
      <v-alert v-if="settingsStore.error" type="error" variant="tonal" class="mt-4" closable>
        {{ settingsStore.error }}
      </v-alert>
      <v-alert
        v-if="settingsStore.saveSuccess"
        type="success"
        variant="tonal"
        class="mt-4"
        closable
        @click:close="settingsStore.saveSuccess = false"
      >
        Settings saved successfully.
      </v-alert>
    </div>

    <!-- Scrollable content -->
    <div class="settings-content px-6 pb-6">
      <!-- Loading -->
      <div v-if="settingsStore.loading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <template v-if="!settingsStore.loading">
      <!-- ─── REPOSITORIES ───────────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-source-repository-multiple" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">Repositories</span>
      </div>

      <v-card class="pa-5 settings-card mb-6" color="surface">
        <!-- Scan controls + stats header -->
        <div class="d-flex align-center justify-space-between flex-wrap ga-3 mb-4">
          <div class="d-flex align-center ga-3">
            <v-avatar size="36" color="primary" variant="tonal" rounded="lg">
              <v-icon icon="mdi-magnify-scan" size="22" />
            </v-avatar>
            <div>
              <div class="text-body-2 font-weight-medium">Code Index</div>
              <div class="text-caption text-medium-emphasis">
                Scan repositories to index features and skill profiles
              </div>
            </div>
          </div>
          <div class="d-flex align-center ga-2">
            <v-tooltip content-class="scan-tooltip" location="bottom" max-width="280">
              <template #activator="{ props }">
                <v-btn
                  v-bind="props"
                  color="primary"
                  variant="tonal"
                  prepend-icon="mdi-magnify-scan"
                  :loading="scanStatus === 'running'"
                  :disabled="settingsStore.repos.length === 0 || !settingsStore.allReposMapped"
                  @click="confirmAndScan(false)"
                >
                  Scan
                </v-btn>
              </template>
              Incremental scan — only indexes changes since the last scan. Fast and safe; existing items are kept.
            </v-tooltip>
            <v-tooltip content-class="scan-tooltip" location="bottom" max-width="280">
              <template #activator="{ props }">
                <v-btn
                  v-bind="props"
                  v-if="scanStatus !== 'running'"
                  variant="outlined"
                  size="small"
                  prepend-icon="mdi-refresh"
                  :disabled="settingsStore.repos.length === 0 || !settingsStore.allReposMapped"
                  @click="confirmAndScan(true)"
                >
                  Full Rescan
                </v-btn>
              </template>
              Rebuilds the entire index from scratch. Use when the index seems out of sync or after major refactors.
            </v-tooltip>
          </div>
        </div>

        <!-- Index stats -->
        <v-expand-transition>
          <div v-if="indexStats && indexStats.knowledgeItems.total > 0" class="mb-4">
            <div class="d-flex align-center ga-2 mb-3">
              <v-icon icon="mdi-database-check-outline" size="16" color="success" />
              <span class="text-body-2 font-weight-medium">Indexed</span>
              <v-chip v-if="indexStats.lastScan" size="x-small" variant="tonal" color="grey">
                {{ formatRelativeTime(indexStats.lastScan.completed_at) }}
              </v-chip>
            </div>
            <div class="d-flex flex-wrap ga-3">
              <div class="index-stat">
                <div class="text-h6 font-weight-bold">{{ indexStats.knowledgeItems.byCategory.feature_registry || 0 }}</div>
                <div class="text-caption text-medium-emphasis">Features</div>
              </div>
              <div class="index-stat">
                <div class="text-h6 font-weight-bold">{{ indexStats.knowledgeItems.embedded }}</div>
                <div class="text-caption text-medium-emphasis">Embedded</div>
              </div>
              <div class="index-stat">
                <div class="text-h6 font-weight-bold">{{ indexStats.skillProfiles }}</div>
                <div class="text-caption text-medium-emphasis">Profiles</div>
              </div>
              <div class="index-stat">
                <div class="text-h6 font-weight-bold">{{ settingsStore.repos.length }}</div>
                <div class="text-caption text-medium-emphasis">Repos</div>
              </div>
            </div>
          </div>
        </v-expand-transition>

        <!-- Scan progress / results -->
        <v-expand-transition>
          <div v-if="scanStatus === 'running' && scanProgress > 0" class="mb-4">
            <v-progress-linear
              :model-value="scanProgress"
              color="primary"
              class="mb-2"
              rounded
              height="6"
            />
            <div class="d-flex align-center ga-2">
              <div class="text-caption text-medium-emphasis">
                {{ scanStatusLabel }}... {{ scanProgress }}%
              </div>
              <v-btn
                variant="text"
                density="compact"
                size="x-small"
                icon="mdi-refresh"
                @click="refreshScanStatus"
              />
            </div>
          </div>
        </v-expand-transition>

        <v-expand-transition>
          <v-alert
            v-if="scanStatus === 'completed'"
            type="success"
            variant="tonal"
            density="compact"
            class="mb-4"
          >
            <span class="font-weight-medium">
              {{ scanResult.scanMode === 'incremental' ? 'Incremental scan' : 'Full scan' }} complete:
            </span>
            {{ scanResult.featuresIndexed }} features indexed,
            {{ scanResult.profilesFound }} skill profiles found.
            <template v-if="scanResult.staleCleaned > 0">
              {{ scanResult.staleCleaned }} stale references cleaned.
            </template>
            <template v-if="scanResult.unmatchedAuthors.length > 0">
              <br>Unmatched git authors: {{ scanResult.unmatchedAuthors.join(', ') }}
            </template>
          </v-alert>
        </v-expand-transition>

        <v-expand-transition>
          <v-alert
            v-if="scanStatus === 'completed' && scanResult.synthesisWarning"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-4"
          >
            {{ scanResult.synthesisWarning }}
          </v-alert>
        </v-expand-transition>

        <v-expand-transition>
          <v-alert
            v-if="scanStatus === 'failed'"
            type="error"
            variant="tonal"
            density="compact"
            class="mb-4"
          >
            Scan failed: {{ scanError }}
          </v-alert>
        </v-expand-transition>

        <!-- Repository table -->
        <div class="pt-4" style="border-top: 1px solid rgba(255,255,255,0.06)">
          <div v-if="settingsStore.reposLoading" class="d-flex justify-center py-4">
            <v-progress-circular indeterminate size="24" />
          </div>

          <template v-else>
            <!-- Branch mapping warning -->
            <v-alert
              v-if="settingsStore.repos.length > 0 && !settingsStore.allReposMapped"
              type="warning"
              variant="tonal"
              density="compact"
              class="mb-4"
            >
              Map main and develop branches for all active repos before scanning.
            </v-alert>

            <v-table v-if="settingsStore.repos.length > 0" density="compact" class="mb-4">
              <thead>
                <tr>
                  <th>Repository</th>
                  <th>Path</th>
                  <th class="text-center">Status</th>
                  <th class="text-center">Main Branch</th>
                  <th class="text-center">Dev Branch</th>
                  <th class="text-center">Knowledge</th>
                  <th class="text-center">Features</th>
                  <th class="text-center">Last SHA</th>
                  <th style="width: 100px;"></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="repo in settingsStore.repos"
                  :key="repo.id"
                  :class="{ 'opacity-50': repo.status === 'ignored' }"
                >
                  <td class="font-weight-medium">
                    {{ repo.name }}
                    <v-tooltip v-if="repo.hasUncommittedChanges" text="Uncommitted changes detected" location="top">
                      <template #activator="{ props }">
                        <v-icon v-bind="props" icon="mdi-alert-circle-outline" size="14" color="warning" class="ml-1" />
                      </template>
                    </v-tooltip>
                  </td>
                  <td class="text-caption text-medium-emphasis">{{ repo.path }}</td>
                  <td class="text-center">
                    <v-chip
                      :color="repo.status === 'active' ? 'success' : 'warning'"
                      size="x-small"
                      variant="tonal"
                    >
                      {{ repo.status }}
                    </v-chip>
                  </td>
                  <td class="text-center">
                    <v-chip
                      v-if="repo.mainBranch"
                      size="x-small"
                      variant="tonal"
                      color="success"
                      prepend-icon="mdi-source-branch"
                      style="cursor: pointer"
                      @click="openBranchDialog(repo)"
                    >
                      {{ repo.mainBranch }}
                    </v-chip>
                    <v-chip
                      v-else
                      size="x-small"
                      variant="tonal"
                      color="warning"
                      style="cursor: pointer"
                      @click="openBranchDialog(repo)"
                    >
                      Not mapped
                    </v-chip>
                  </td>
                  <td class="text-center">
                    <v-chip
                      v-if="repo.developBranch"
                      size="x-small"
                      variant="tonal"
                      color="success"
                      prepend-icon="mdi-source-branch"
                      style="cursor: pointer"
                      @click="openBranchDialog(repo)"
                    >
                      {{ repo.developBranch }}
                    </v-chip>
                    <v-chip
                      v-else
                      size="x-small"
                      variant="tonal"
                      color="warning"
                      style="cursor: pointer"
                      @click="openBranchDialog(repo)"
                    >
                      Not mapped
                    </v-chip>
                  </td>
                  <td class="text-center">{{ repo.knowledgeCount }}</td>
                  <td class="text-center">{{ repo.featureCount }}</td>
                  <td class="text-center">
                    <v-chip v-if="repo.sha" size="x-small" variant="tonal">
                      {{ repo.sha?.substring(0, 7) }}
                    </v-chip>
                    <span v-else class="text-caption text-medium-emphasis">-</span>
                  </td>
                  <td class="text-right">
                    <v-tooltip
                      :text="repo.status === 'active' ? 'Ignore (skip in scans)' : 'Activate'"
                      location="top"
                      content-class="text-white bg-grey-darken-3"
                    >
                      <template #activator="{ props }">
                        <v-btn
                          v-bind="props"
                          :icon="repo.status === 'active' ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
                          size="x-small"
                          variant="text"
                          :color="repo.status === 'active' ? 'warning' : 'success'"
                          @click="settingsStore.setRepoStatus(repo.id, repo.status === 'active' ? 'ignored' : 'active')"
                        />
                      </template>
                    </v-tooltip>
                    <v-tooltip text="Remove" location="top" content-class="text-white bg-grey-darken-3">
                      <template #activator="{ props }">
                        <v-btn
                          v-bind="props"
                          icon="mdi-close"
                          size="x-small"
                          variant="text"
                          color="error"
                          @click="settingsStore.removeRepo(repo.path)"
                        />
                      </template>
                    </v-tooltip>
                  </td>
                </tr>
              </tbody>
            </v-table>

            <div
              v-else
              class="text-body-2 text-medium-emphasis text-center py-6"
            >
              <v-icon icon="mdi-source-repository" size="40" class="mb-2 d-block mx-auto" />
              No repositories added yet. Add a repository to start indexing.
            </div>

            <v-btn
              variant="tonal"
              size="small"
              prepend-icon="mdi-plus"
              @click="showAddRepoDialog = true"
            >
              Add Repository
            </v-btn>
          </template>
        </div>

        <!-- Scan Settings -->
        <div class="mt-4 pt-4" style="border-top: 1px solid rgba(255,255,255,0.06)">
          <div class="d-flex align-center ga-2 mb-3">
            <v-icon icon="mdi-tune-vertical" size="16" color="primary" />
            <span class="text-body-2 font-weight-medium">Scan Settings</span>
          </div>
          <v-row dense>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="settingsStore.connections.scan.timeoutSeconds"
                label="Timeout (seconds)"
                type="number"
                :min="60"
                :max="1800"
                density="compact"
                variant="outlined"
              >
                <template #append-inner>
                  <v-tooltip content-class="scan-tooltip" location="top" max-width="280">
                    <template #activator="{ props }">
                      <v-icon v-bind="props" icon="mdi-help-circle-outline" size="18" color="grey" />
                    </template>
                    How long the scan can run before it stops. Large repos with many features
                    may need more time. Default: 300s (5 min). Try 600s if scans time out.
                  </v-tooltip>
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="12" sm="6">
              <v-select
                v-model="settingsStore.connections.scan.maxTurns"
                :items="maxTurnsOptions"
                label="Max AI steps"
                density="compact"
                variant="outlined"
              >
                <template #append-inner>
                  <v-tooltip content-class="scan-tooltip" location="top" max-width="280">
                    <template #activator="{ props }">
                      <v-icon v-bind="props" icon="mdi-help-circle-outline" size="18" color="grey" />
                    </template>
                    Number of actions the AI can take per repo (read files, write feature
                    descriptions, etc.). More steps = more features described but takes longer.
                  </v-tooltip>
                </template>
              </v-select>
            </v-col>
          </v-row>
          <v-switch
            v-model="settingsStore.connections.scan.autoCreateMembers"
            label="Auto-create members from git authors"
            color="primary"
            density="compact"
            hide-details
            class="mt-1"
          >
            <template #append>
              <v-tooltip content-class="scan-tooltip" location="top" max-width="280">
                <template #activator="{ props }">
                  <v-icon v-bind="props" icon="mdi-help-circle-outline" size="18" color="grey" />
                </template>
                When enabled, scanning a repo will automatically create org members from
                git commit authors (email + name). They get a default password and can be
                deactivated later from the Members page.
              </v-tooltip>
            </template>
          </v-switch>
        </div>
      </v-card>

      <!-- Rescan confirmation dialog -->
      <v-dialog v-model="showRescanDialog" max-width="420">
        <v-card>
          <v-card-title class="text-body-1 font-weight-bold pa-4 pb-2">
            {{ pendingFullRescan ? 'Full Rescan' : 'Re-scan Repository' }}?
          </v-card-title>
          <v-card-text class="text-body-2 pb-2">
            <template v-if="pendingFullRescan">
              This will rebuild the entire index from scratch. Existing knowledge items will be replaced.
            </template>
            <template v-else>
              This will scan for changes since the last index. Unchanged items are kept.
            </template>
            <div v-if="indexStats && indexStats.knowledgeItems.total > 0" class="mt-2 text-caption text-medium-emphasis">
              Current index: {{ indexStats.knowledgeItems.total }} knowledge items,
              {{ indexStats.skillProfiles }} skill profiles.
            </div>
          </v-card-text>
          <v-card-actions class="pa-4 pt-2">
            <v-spacer />
            <v-btn variant="text" @click="showRescanDialog = false">Cancel</v-btn>
            <v-btn color="primary" variant="tonal" @click="proceedWithScan">
              {{ pendingFullRescan ? 'Full Rescan' : 'Scan' }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Add Repo Dialog -->
      <v-dialog v-model="showAddRepoDialog" max-width="520">
        <v-card color="surface" class="pa-6">
          <div class="text-h6 font-weight-bold mb-4">Add Repositories</div>

          <!-- Selected paths list -->
          <div v-if="newRepoPaths.length" class="mb-3">
            <v-chip
              v-for="(p, idx) in newRepoPaths"
              :key="p"
              closable
              variant="tonal"
              size="small"
              class="ma-1"
              @click:close="newRepoPaths.splice(idx, 1)"
            >
              <v-icon icon="mdi-source-repository" size="14" start />
              {{ p.split('/').pop() }}
              <v-tooltip activator="parent" location="top" :text="p" />
            </v-chip>
          </div>

          <!-- Path input + browse -->
          <v-text-field
            v-model="newRepoPath"
            label="Absolute path to git repository"
            placeholder="/path/to/repo"
            variant="outlined"
            density="compact"
            hint="Add multiple repos — type or browse, then press Enter or click +"
            persistent-hint
            @keyup.enter="addPathToList"
          >
            <template #prepend-inner>
              <v-icon icon="mdi-folder-outline" size="20" class="text-medium-emphasis me-1" />
            </template>
            <template #append-inner>
              <v-btn
                icon="mdi-plus"
                size="small"
                variant="text"
                density="compact"
                :disabled="!newRepoPath.trim()"
                @click="addPathToList"
              />
              <v-btn
                icon="mdi-folder-search-outline"
                size="small"
                variant="text"
                density="compact"
                @click="directoryPicker?.open()"
              />
            </template>
          </v-text-field>
          <v-checkbox
            v-model="scanAfterAdd"
            label="Scan after adding"
            density="compact"
            hide-details
            class="mt-2"
          />
          <v-card-actions class="pa-0 mt-3">
            <v-spacer />
            <v-btn variant="text" @click="showAddRepoDialog = false">Cancel</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              :disabled="newRepoPaths.length === 0 && !newRepoPath.trim()"
              @click="addReposAndScan"
            >
              Add {{ newRepoPaths.length > 1 ? `(${newRepoPaths.length})` : '' }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Branch Mapping Dialog -->
      <v-dialog v-model="showBranchDialog" max-width="480">
        <v-card color="surface" class="pa-6">
          <div class="text-h6 font-weight-bold mb-1">Branch Mapping</div>
          <div class="text-body-2 text-medium-emphasis mb-4">
            {{ branchDialogRepo?.name }}
          </div>

          <div v-if="branchesLoading" class="d-flex justify-center py-6">
            <v-progress-circular indeterminate size="24" />
          </div>

          <template v-else>
            <v-select
              v-model="branchDialogMain"
              :items="branchDialogBranches"
              label="Main Branch *"
              variant="outlined"
              density="compact"
              prepend-inner-icon="mdi-source-branch"
              class="mb-3"
              :rules="[v => !!v || 'Required']"
            />
            <v-select
              v-model="branchDialogDev"
              :items="branchDialogBranches"
              label="Develop Branch *"
              variant="outlined"
              density="compact"
              prepend-inner-icon="mdi-source-branch"
              :rules="[v => !!v || 'Required']"
            />
          </template>

          <v-card-actions class="pa-0 mt-4">
            <v-spacer />
            <v-btn variant="text" @click="showBranchDialog = false">Cancel</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              :disabled="!branchDialogMain || !branchDialogDev"
              :loading="branchSaving"
              @click="saveBranchMapping"
            >
              Save
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Directory Picker (reusable component, multi-select mode) -->
      <DirectoryPicker
        ref="directoryPicker"
        :initial-path="newRepoPath || undefined"
        multi-select
        @select="onDirectorySelected"
        @select-multiple="onMultipleDirectoriesSelected"
      />

      <!-- ─── MCP INTEGRATION ─────────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-api" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">MCP Integration</span>
      </div>

      <v-card class="pa-5 settings-card mb-6" color="surface">
        <div class="d-flex align-center ga-3 mb-4">
          <v-avatar size="36" color="surface-variant" rounded="lg">
            <v-icon icon="mdi-connection" size="22" />
          </v-avatar>
          <div>
            <div class="text-body-2 font-weight-medium">Claude Code MCP</div>
            <div class="text-caption text-medium-emphasis">
              Connect Claude Code to Bodhigrove for BUDs, knowledge, and team context
            </div>
          </div>
        </div>

        <!-- Token status -->
        <div class="d-flex align-center ga-3 mb-4">
          <v-chip
            :color="mcpTokenSet ? 'success' : 'warning'"
            variant="tonal"
            size="small"
            :prepend-icon="mcpTokenSet ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'"
          >
            {{ mcpTokenSet ? 'Token configured' : 'No token set' }}
          </v-chip>
          <v-btn
            variant="tonal"
            density="compact"
            size="small"
            color="primary"
            class="text-none"
            :loading="regeneratingToken"
            @click="regenerateMcpToken"
          >
            {{ mcpTokenSet ? 'Regenerate Token' : 'Generate Token' }}
          </v-btn>
        </div>

        <!-- Token display (one-time) -->
        <v-expand-transition>
          <v-alert
            v-if="newMcpToken"
            type="info"
            variant="tonal"
            density="compact"
            class="mb-4"
          >
            <div class="text-body-2 font-weight-medium mb-1">
              Your MCP token (copy now — it won't be shown again):
            </div>
            <div class="d-flex align-center ga-2">
              <code class="flex-grow-1 pa-2" style="background: rgba(0,0,0,0.2); border-radius: 4px; word-break: break-all;">
                {{ newMcpToken }}
              </code>
              <v-btn
                icon="mdi-content-copy"
                variant="text"
                size="small"
                @click="copyToken"
              />
            </div>
          </v-alert>
        </v-expand-transition>

        <!-- Claude Code config snippet -->
        <div class="text-body-2 font-weight-medium mb-2">Claude Code Configuration</div>
        <div class="text-caption text-medium-emphasis mb-2">
          Add this to your Claude Code MCP settings (claude_desktop_config.json or .claude/settings.json):
        </div>
        <div class="config-snippet pa-3 rounded" style="background: rgba(0,0,0,0.3); position: relative;">
          <v-btn
            icon="mdi-content-copy"
            variant="text"
            size="x-small"
            style="position: absolute; top: 4px; right: 4px;"
            @click="copyConfig"
          />
          <pre class="text-caption" style="white-space: pre-wrap; margin: 0;">{{ mcpConfigSnippet }}</pre>
        </div>
      </v-card>

      <!-- ─── GIT PROVIDERS ────────────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-git" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">Git Providers</span>
      </div>

      <v-row class="mb-6">
        <!-- GitHub -->
        <v-col cols="12" md="6">
          <v-card
            class="pa-5 settings-card"
            :class="{ 'settings-card--active': settingsStore.connections.github.enabled }"
            color="surface"
          >
            <div class="d-flex align-center justify-space-between mb-1">
              <div class="d-flex align-center ga-3">
                <v-avatar size="36" color="surface-variant" rounded="lg">
                  <v-icon icon="mdi-github" size="22" />
                </v-avatar>
                <div>
                  <div class="text-body-2 font-weight-medium">GitHub</div>
                  <div class="text-caption text-medium-emphasis">PR tracking &amp; issue sync</div>
                </div>
              </div>
              <v-switch
                v-model="settingsStore.connections.github.enabled"
                hide-details
                density="compact"
                color="primary"
              />
            </div>

            <v-expand-transition>
              <div v-if="settingsStore.connections.github.enabled" class="mt-4">
                <v-text-field
                  v-model="settingsStore.connections.github.org"
                  label="Organization name (optional)"
                  placeholder="my-company"
                  prepend-inner-icon="mdi-domain"
                  density="compact"
                  variant="outlined"
                  class="mb-3"
                  hint="Find it at github.com/orgs/<org-name>. Leave empty for personal accounts — you can still add members manually."
                  persistent-hint
                />
                <v-text-field
                  v-model="settingsStore.connections.github.pat"
                  label="Personal Access Token"
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                  prepend-inner-icon="mdi-key-outline"
                  type="password"
                  density="compact"
                  variant="outlined"
                  hint="Leave unchanged to keep existing token"
                  persistent-hint
                />
                <div class="text-caption text-medium-emphasis mt-2">
                  <v-icon icon="mdi-help-circle-outline" size="14" class="mr-1" />
                  Go to
                  <a
                    href="https://github.com/settings/tokens?type=beta"
                    target="_blank"
                    rel="noopener"
                    class="text-primary"
                  >GitHub &rarr; Settings &rarr; Developer settings &rarr; Personal access tokens</a>.
                  Create a fine-grained token with: <strong>Organization permissions</strong> &rarr;
                  <em>Members: Read</em>, and <strong>Repository permissions</strong> &rarr;
                  <em>Contents: Read</em>.
                </div>
              </div>
            </v-expand-transition>
          </v-card>
        </v-col>

        <!-- Coming Soon -->
        <v-col cols="12" md="6">
          <div class="d-flex flex-column ga-3 h-100">
            <v-card class="pa-4 coming-soon-card flex-grow-1" color="surface" variant="outlined">
              <div class="d-flex align-center ga-3">
                <v-avatar size="36" rounded="lg" class="coming-soon-avatar">
                  <v-icon icon="mdi-bitbucket" size="20" />
                </v-avatar>
                <div class="flex-grow-1">
                  <div class="text-body-2 font-weight-medium">Bitbucket</div>
                  <div class="text-caption text-medium-emphasis">Cloud &amp; Server PR tracking</div>
                </div>
                <v-chip size="x-small" variant="tonal" color="grey">Soon</v-chip>
              </div>
            </v-card>
            <v-card class="pa-4 coming-soon-card flex-grow-1" color="surface" variant="outlined">
              <div class="d-flex align-center ga-3">
                <v-avatar size="36" rounded="lg" class="coming-soon-avatar">
                  <v-icon icon="mdi-gitlab" size="20" />
                </v-avatar>
                <div class="flex-grow-1">
                  <div class="text-body-2 font-weight-medium">GitLab</div>
                  <div class="text-caption text-medium-emphasis">SaaS &amp; self-managed MR tracking</div>
                </div>
                <v-chip size="x-small" variant="tonal" color="grey">Soon</v-chip>
              </div>
            </v-card>
          </div>
        </v-col>
      </v-row>

      <!-- ─── MESSAGING ──────────────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-message-text-outline" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">Messaging</span>
      </div>

      <v-row class="mb-6">
        <!-- Slack -->
        <v-col cols="12" md="6">
          <v-card
            class="pa-5 settings-card"
            :class="{ 'settings-card--active': settingsStore.connections.slack.enabled }"
            color="surface"
          >
            <div class="d-flex align-center justify-space-between mb-1">
              <div class="d-flex align-center ga-3">
                <v-avatar size="36" color="primary" variant="tonal" rounded="lg">
                  <v-icon icon="mdi-slack" size="22" />
                </v-avatar>
                <div>
                  <div class="text-body-2 font-weight-medium">Slack</div>
                  <div class="text-caption text-medium-emphasis">Feature intake &amp; agent triggers</div>
                </div>
              </div>
              <v-switch
                v-model="settingsStore.connections.slack.enabled"
                hide-details
                density="compact"
                color="primary"
              />
            </div>

            <v-expand-transition>
              <div v-if="settingsStore.connections.slack.enabled" class="mt-4">
                <v-text-field
                  v-model="settingsStore.connections.slack.botToken"
                  label="Bot Token"
                  placeholder="xoxb-..."
                  prepend-inner-icon="mdi-key-outline"
                  density="compact"
                  variant="outlined"
                  class="mb-2"
                  hint="Leave unchanged to keep existing token"
                  persistent-hint
                />
                <v-text-field
                  v-model="settingsStore.connections.slack.signingSecret"
                  label="Signing Secret"
                  placeholder="Enter signing secret"
                  prepend-inner-icon="mdi-shield-key-outline"
                  type="password"
                  density="compact"
                  variant="outlined"
                  hint="Leave unchanged to keep existing secret"
                  persistent-hint
                  class="mb-2"
                />
                <v-text-field
                  v-model="settingsStore.connections.slack.teamId"
                  label="Workspace Team ID"
                  placeholder="T0123ABC..."
                  prepend-inner-icon="mdi-identifier"
                  density="compact"
                  variant="outlined"
                  hint="Auto-detected from bot token. Override if needed."
                  persistent-hint
                  class="mb-3"
                />

                <!-- Collapsible: App Manifest -->
                <div
                  class="rounded-lg mb-2"
                  style="border: 1px solid rgba(var(--v-theme-on-surface), 0.08);"
                >
                  <div
                    class="d-flex align-center ga-2 pa-3 text-body-2"
                    style="cursor: pointer;"
                    @click="slackManifestOpen = !slackManifestOpen"
                  >
                    <v-icon
                      :icon="slackManifestOpen ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                      size="18"
                    />
                    <v-icon icon="mdi-rocket-launch-outline" size="16" color="primary" />
                    <span class="font-weight-medium">Quick setup with App Manifest</span>
                  </div>
                  <v-expand-transition>
                    <div v-if="slackManifestOpen" class="px-3 pb-3 text-body-2">
                      <div class="text-medium-emphasis mb-2" style="line-height: 1.6;">
                        1. Go to <strong class="text-high-emphasis">api.slack.com/apps</strong> →
                        <strong class="text-high-emphasis">Create New App</strong> →
                        <strong class="text-high-emphasis">From a manifest</strong>
                      </div>
                      <div class="text-medium-emphasis mb-2" style="line-height: 1.6;">
                        2. Select your workspace, pick <strong class="text-high-emphasis">JSON</strong>, and paste:
                      </div>
                      <div class="d-flex align-center ga-2 mb-2">
                        <v-btn
                          size="small"
                          variant="flat"
                          color="primary"
                          prepend-icon="mdi-content-copy"
                          @click="copySlackManifest"
                        >
                          {{ manifestCopied ? 'Copied!' : 'Copy manifest' }}
                        </v-btn>
                      </div>
                      <pre
                        class="pa-3 rounded text-caption mb-3"
                        style="background: rgba(0, 0, 0, 0.25); overflow-x: auto; white-space: pre; max-height: 150px; overflow-y: auto; color: rgba(var(--v-theme-on-surface), 0.7);"
                      >{{ slackManifest }}</pre>
                      <div class="text-medium-emphasis" style="line-height: 1.6;">
                        3. Review and click <strong class="text-high-emphasis">Create</strong><br>
                        4. Click <strong class="text-high-emphasis">Install to Workspace</strong> →
                        copy the <strong class="text-high-emphasis">Bot Token</strong>
                        <code style="opacity: 0.5;">xoxb-...</code><br>
                        5. Under <strong class="text-high-emphasis">Basic Information</strong> →
                        copy the <strong class="text-high-emphasis">Signing Secret</strong>
                      </div>
                    </div>
                  </v-expand-transition>
                </div>

                <!-- Collapsible: Event Subscriptions -->
                <div
                  class="rounded-lg mb-3"
                  style="border: 1px solid rgba(var(--v-theme-on-surface), 0.08);"
                >
                  <div
                    class="d-flex align-center ga-2 pa-3 text-body-2"
                    style="cursor: pointer;"
                    @click="slackEventsOpen = !slackEventsOpen"
                  >
                    <v-icon
                      :icon="slackEventsOpen ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                      size="18"
                    />
                    <v-icon icon="mdi-webhook" size="16" color="primary" />
                    <span class="font-weight-medium">Event Subscriptions</span>
                  </div>
                  <v-expand-transition>
                    <div v-if="slackEventsOpen" class="px-3 pb-3 text-body-2">
                      <div class="text-medium-emphasis mb-2" style="line-height: 1.6;">
                        In your Slack app → <strong class="text-high-emphasis">Event Subscriptions</strong>:
                      </div>
                      <div class="text-medium-emphasis mb-2" style="line-height: 1.6;">
                        1. Toggle <strong class="text-high-emphasis">Enable Events</strong> on
                      </div>
                      <div class="text-medium-emphasis mb-2" style="line-height: 1.6;">
                        2. Set <strong class="text-high-emphasis">Request URL</strong> to:
                      </div>
                      <div class="d-flex align-center ga-2 mb-3">
                        <code
                          class="pa-2 rounded flex-grow-1"
                          style="background: rgba(0, 0, 0, 0.25); font-size: 0.8rem; word-break: break-all;"
                        >{{ webhookUrl }}</code>
                        <v-btn
                          size="small"
                          variant="flat"
                          color="primary"
                          icon="mdi-content-copy"
                          @click="copyWebhookUrl"
                        />
                      </div>
                      <div class="text-medium-emphasis mb-1" style="line-height: 1.6;">
                        3. Under <strong class="text-high-emphasis">Subscribe to bot events</strong>, add:
                      </div>
                      <div class="d-flex flex-wrap ga-1 mb-2">
                        <v-chip size="x-small" variant="tonal" color="primary">reaction_added</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary">message.channels</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary">message.groups</v-chip>
                      </div>
                      <div class="text-medium-emphasis mb-2" style="line-height: 1.6;">
                        4. Under <strong class="text-high-emphasis">OAuth &amp; Permissions</strong> → <strong class="text-high-emphasis">Bot Token Scopes</strong>, ensure these are added:
                      </div>
                      <div class="d-flex flex-wrap ga-1 mb-2">
                        <v-chip size="x-small" variant="tonal" color="primary">chat:write</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary">channels:read</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary">channels:history</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary">channels:join</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary">reactions:read</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary">groups:history</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary">users:read</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary">users:read.email</v-chip>
                      </div>
                      <div class="text-medium-emphasis" style="line-height: 1.6;">
                        5. Click <strong class="text-high-emphasis">Save Changes</strong>
                        and reinstall the app when prompted
                      </div>
                      <div class="d-flex align-center ga-1 mt-3 pa-2 rounded" style="background: rgba(var(--v-theme-info), 0.08);">
                        <v-icon icon="mdi-information-outline" size="16" color="info" />
                        <span class="text-body-2 text-medium-emphasis">
                          Developer presence (online/offline) is tracked automatically
                          via the <code>users:read</code> scope — no additional event subscriptions needed.
                        </span>
                      </div>
                    </div>
                  </v-expand-transition>
                </div>

                <!-- Slack Member Sync -->
                <div
                  class="rounded-lg"
                  style="border: 1px solid rgba(var(--v-theme-on-surface), 0.08);"
                >
                  <div
                    class="d-flex align-center ga-2 pa-3 text-body-2"
                    style="cursor: pointer;"
                    @click="slackSyncOpen = !slackSyncOpen"
                  >
                    <v-icon
                      :icon="slackSyncOpen ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                      size="18"
                    />
                    <v-icon icon="mdi-account-sync-outline" size="16" color="primary" />
                    <span class="font-weight-medium">Sync Members</span>
                    <v-spacer />
                    <v-btn
                      size="small"
                      variant="tonal"
                      color="primary"
                      prepend-icon="mdi-sync"
                      :loading="slackSyncLoading"
                      @click.stop="fetchSlackMembers"
                    >
                      Sync
                    </v-btn>
                  </div>
                  <v-expand-transition>
                    <div v-if="slackSyncOpen" class="px-3 pb-3">
                      <div class="text-caption text-medium-emphasis mb-3">
                        Link Slack workspace users to FlowDev members so names appear correctly in triage and approvals.
                        <br />
                        <strong>Required scopes:</strong>
                        <v-chip size="x-small" variant="tonal" color="primary" class="ml-1">users:read</v-chip>
                        <v-chip size="x-small" variant="tonal" color="primary" class="ml-1">users:read.email</v-chip>
                        — add in your Slack app under <em>OAuth &amp; Permissions</em>, then reinstall.
                      </div>

                      <v-alert v-if="slackSyncError" type="error" variant="tonal" density="compact" class="mb-3">
                        {{ slackSyncError }}
                      </v-alert>

                      <div v-if="slackMembers.length > 0">
                        <div
                          v-for="member in slackMembers"
                          :key="member.slack_id"
                          class="d-flex align-center ga-3 py-2"
                          style="border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.05);"
                        >
                          <v-avatar size="32" :image="member.slack_avatar || undefined" color="primary" variant="tonal">
                            <span v-if="!member.slack_avatar" class="text-caption">
                              {{ member.slack_name.charAt(0).toUpperCase() }}
                            </span>
                          </v-avatar>
                          <div style="min-width: 140px;">
                            <div class="text-body-2 font-weight-medium">{{ member.slack_name }}</div>
                          </div>
                          <v-icon icon="mdi-arrow-right" size="16" class="text-medium-emphasis" />
                          <template v-if="!member.already_linked">
                            <v-autocomplete
                              v-model="slackLinkMap[member.slack_id]"
                              :items="flowdevMemberOptions"
                              item-title="name"
                              item-value="id"
                              density="compact"
                              variant="outlined"
                              hide-details
                              placeholder="Search member..."
                              clearable
                              auto-select-first
                              style="max-width: 240px;"
                            />
                            <v-btn
                              icon="mdi-close"
                              size="x-small"
                              variant="text"
                              color="medium-emphasis"
                              title="Remove from list"
                              @click="dismissSlackMember(member.slack_id)"
                            />
                          </template>
                          <div v-else class="d-flex align-center ga-2">
                            <v-icon icon="mdi-check-circle" size="16" color="success" />
                            <span class="text-body-2">{{ member.matched_user_name }}</span>
                            <v-btn
                              icon="mdi-link-variant-off"
                              size="x-small"
                              variant="text"
                              color="error"
                              title="Unlink"
                              @click="unlinkSlackMember(member.slack_id)"
                            />
                          </div>
                        </div>

                        <v-btn
                          class="mt-3"
                          color="primary"
                          variant="flat"
                          size="small"
                          prepend-icon="mdi-link-variant"
                          :loading="slackLinkLoading"
                          :disabled="Object.keys(slackLinkMap).length === 0"
                          @click="linkSlackMembers"
                        >
                          Link Selected
                        </v-btn>

                        <v-alert
                          v-if="slackLinkSuccess"
                          type="success"
                          variant="tonal"
                          density="compact"
                          class="mt-2"
                        >
                          {{ slackLinkSuccess }}
                        </v-alert>
                      </div>

                      <div v-else-if="!slackSyncLoading" class="text-caption text-medium-emphasis">
                        Click "Sync" to fetch Slack workspace members.
                      </div>
                    </div>
                  </v-expand-transition>
                </div>
              </div>
            </v-expand-transition>
          </v-card>
        </v-col>

        <!-- Telegram coming soon -->
        <v-col cols="12" md="6">
          <v-card class="pa-4 coming-soon-card h-100 d-flex align-center" color="surface" variant="outlined">
            <div class="d-flex align-center ga-3 w-100">
              <v-avatar size="36" rounded="lg" class="coming-soon-avatar">
                <v-icon icon="mdi-send" size="20" />
              </v-avatar>
              <div class="flex-grow-1">
                <div class="text-body-2 font-weight-medium">Telegram</div>
                <div class="text-caption text-medium-emphasis">Notifications &amp; workflow triggers</div>
              </div>
              <v-chip size="x-small" variant="tonal" color="grey">Soon</v-chip>
            </div>
          </v-card>
        </v-col>
      </v-row>

      <!-- ─── AI CONFIGURATION ───────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-robot-outline" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">AI Configuration</span>
      </div>

      <!-- Preset cards -->
      <v-row class="mb-4">
        <v-col v-for="preset in presets" :key="preset.value" cols="12" sm="6" md="3">
          <v-card
            class="pa-5 text-center cursor-pointer preset-card h-100"
            :class="{ 'preset-card--active': settingsStore.connections.aiConfig.preset === preset.value }"
            color="surface"
            @click="settingsStore.connections.aiConfig.preset = preset.value"
          >
            <v-icon
              :icon="preset.icon"
              size="36"
              :color="settingsStore.connections.aiConfig.preset === preset.value ? 'primary' : 'grey'"
              class="mb-3"
            />
            <div class="text-body-1 font-weight-medium mb-1">{{ preset.title }}</div>
            <div class="text-caption text-medium-emphasis mb-3">{{ preset.description }}</div>
            <v-chip
              v-if="preset.recommended"
              size="x-small"
              color="primary"
              variant="tonal"
            >
              Recommended
            </v-chip>
          </v-card>
        </v-col>
      </v-row>

      <!-- Claude Code connection (for presets that use it) -->
      <v-expand-transition>
        <v-card
          v-if="needsClaudeCode"
          class="pa-6 settings-card mb-4"
          color="surface"
        >
          <div class="d-flex align-center ga-3 mb-1">
            <v-avatar size="36" color="surface-variant" rounded="lg">
              <v-icon icon="mdi-console" size="22" />
            </v-avatar>
            <div class="flex-grow-1">
              <div class="text-body-1 font-weight-medium">Claude Code</div>
              <div class="text-caption text-medium-emphasis">
                Required for codebase-aware agents. Must be installed on this machine.
              </div>
            </div>
            <v-chip
              v-if="claudeStatus === 'passed'"
              color="success" variant="flat" size="small"
              prepend-icon="mdi-check-circle-outline"
            >
              Connected
            </v-chip>
            <v-chip
              v-else-if="claudeStatus === 'failed'"
              color="error" variant="flat" size="small"
              prepend-icon="mdi-alert-circle-outline"
            >
              Not Available
            </v-chip>
          </div>

          <div class="mt-4">
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-connection"
              :loading="claudeStatus === 'checking'"
              @click="checkClaudeCode"
            >
              {{ claudeStatus === 'idle' ? 'Test Connection' : 'Retest' }}
            </v-btn>

            <v-expand-transition>
              <div v-if="claudeStatus === 'failed'" class="mt-3">
                <v-alert type="warning" variant="tonal" density="compact">
                  <div class="text-body-2 mb-2">{{ claudeError }}</div>
                  <div class="text-caption">
                    Install Claude Code:
                    <code>curl -fsSL https://claude.ai/install.sh | bash</code>
                  </div>
                </v-alert>
              </div>
            </v-expand-transition>

            <v-expand-transition>
              <div v-if="claudeStatus === 'passed' && claudeVersion" class="mt-3">
                <div class="text-caption text-medium-emphasis">
                  <v-icon icon="mdi-information-outline" size="14" class="mr-1" />
                  Version: {{ claudeVersion }}
                </div>
              </div>
            </v-expand-transition>
          </div>
        </v-card>
      </v-expand-transition>

      <!-- Preset config fields -->
      <v-card class="pa-6 settings-card mb-6" color="surface">
        <div class="text-body-1 font-weight-medium mb-1">{{ activePresetTitle }} Settings</div>
        <div class="text-caption text-medium-emphasis mb-4">{{ activePresetHint }}</div>

        <!-- Local -->
        <template v-if="settingsStore.connections.aiConfig.preset === 'local'">
          <v-text-field
            v-model="settingsStore.connections.aiConfig.ollamaUrl"
            label="Ollama URL"
            placeholder="http://localhost:11434"
            prepend-inner-icon="mdi-server-outline"
            density="compact" variant="outlined" class="mb-3"
          />
          <v-text-field
            v-model="settingsStore.connections.aiConfig.ollamaModel"
            label="Model"
            placeholder="llama3:8b"
            prepend-inner-icon="mdi-cube-outline"
            density="compact" variant="outlined"
          />
        </template>

        <!-- Cloud -->
        <template v-if="settingsStore.connections.aiConfig.preset === 'cloud'">
          <v-select
            v-model="settingsStore.connections.aiConfig.cloudProvider"
            :items="cloudProviders"
            label="Provider"
            prepend-inner-icon="mdi-cloud-outline"
            density="compact" variant="outlined" class="mb-3"
          />
          <v-text-field
            v-model="settingsStore.connections.aiConfig.cloudApiKey"
            label="API Key"
            :placeholder="settingsStore.connections.aiConfig.cloudProvider === 'anthropic' ? 'sk-ant-...' : 'sk-...'"
            prepend-inner-icon="mdi-key-outline"
            type="password"
            density="compact" variant="outlined" class="mb-3"
            hint="Leave unchanged to keep existing key"
            persistent-hint
          />
          <v-text-field
            v-model="settingsStore.connections.aiConfig.cloudModel"
            label="Model"
            :placeholder="settingsStore.connections.aiConfig.cloudProvider === 'anthropic' ? 'claude-sonnet-4-5-20250514' : 'gpt-4o'"
            prepend-inner-icon="mdi-cube-outline"
            density="compact" variant="outlined"
          />
        </template>

        <!-- Hybrid -->
        <template v-if="settingsStore.connections.aiConfig.preset === 'hybrid'">
          <v-alert type="info" variant="tonal" density="compact" class="mb-4">
            Codebase agents use Claude Code. Other agents use the Cloud API.
          </v-alert>
          <v-select
            v-model="settingsStore.connections.aiConfig.cloudProvider"
            :items="cloudProviders"
            label="Cloud Provider"
            prepend-inner-icon="mdi-cloud-outline"
            density="compact" variant="outlined" class="mb-3"
          />
          <v-text-field
            v-model="settingsStore.connections.aiConfig.cloudApiKey"
            label="Cloud API Key"
            :placeholder="settingsStore.connections.aiConfig.cloudProvider === 'anthropic' ? 'sk-ant-...' : 'sk-...'"
            prepend-inner-icon="mdi-key-outline"
            type="password"
            density="compact" variant="outlined" class="mb-3"
            hint="Leave unchanged to keep existing key"
            persistent-hint
          />
          <v-text-field
            v-model="settingsStore.connections.aiConfig.cloudModel"
            label="Cloud Model"
            :placeholder="settingsStore.connections.aiConfig.cloudProvider === 'anthropic' ? 'claude-sonnet-4-5-20250514' : 'gpt-4o'"
            prepend-inner-icon="mdi-cube-outline"
            density="compact" variant="outlined"
          />
        </template>

        <!-- Claude + Ollama -->
        <template v-if="settingsStore.connections.aiConfig.preset === 'claude-ollama'">
          <v-alert type="info" variant="tonal" density="compact" class="mb-4">
            Codebase agents use Claude Code. Other agents use Ollama locally.
          </v-alert>
          <v-text-field
            v-model="settingsStore.connections.aiConfig.ollamaUrl"
            label="Ollama URL"
            placeholder="http://localhost:11434"
            prepend-inner-icon="mdi-server-outline"
            density="compact" variant="outlined" class="mb-3"
          />
          <v-text-field
            v-model="settingsStore.connections.aiConfig.ollamaModel"
            label="Ollama Model"
            placeholder="llama3:8b"
            prepend-inner-icon="mdi-cube-outline"
            density="compact" variant="outlined"
          />
        </template>
      </v-card>

      <!-- Bottom save button -->
      <div class="d-flex justify-end">
        <v-btn
          color="primary"
          prepend-icon="mdi-content-save-outline"
          :loading="settingsStore.saving"
          @click="save"
        >
          Save Changes
        </v-btn>
      </div>
    </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useMembersStore } from '@/stores/members'
import DirectoryPicker from '@/components/setup/DirectoryPicker.vue'
import api from '@/services/api'
import type { RepoInfo } from '@/types'

const settingsStore = useSettingsStore()
const membersStore = useMembersStore()

// Claude Code connection state
const claudeStatus = ref<'idle' | 'checking' | 'passed' | 'failed'>('idle')
const claudeError = ref('')
const claudeVersion = ref('')

// Scan state
const scanStatus = ref<'idle' | 'running' | 'completed' | 'failed'>('idle')
const scanProgress = ref(0)
const scanStatusLabel = ref('')
const scanError = ref('')
const scanResult = ref({
  scanMode: 'full',
  featuresIndexed: 0,
  featuresSkipped: 0,
  profilesFound: 0,
  staleCleaned: 0,
  unmatchedAuthors: [] as string[],
  synthesisWarning: '' as string,
})
let scanPollInterval: ReturnType<typeof setInterval> | null = null
let currentScanId = ''

// Index stats
const indexStats = ref<{
  lastScan: { completed_at: string; repos_scanned: number; features_indexed: number; profiles_found: number } | null
  knowledgeItems: { total: number; byCategory: Record<string, number>; embedded: number }
  skillProfiles: number
  reposTracked: number
} | null>(null)

// Repo management
const showAddRepoDialog = ref(false)
const newRepoPath = ref('')
const newRepoPaths = ref<string[]>([])
const scanAfterAdd = ref(true)
const directoryPicker = ref<InstanceType<typeof DirectoryPicker> | null>(null)

function onDirectorySelected(path: string) {
  if (path && !newRepoPaths.value.includes(path)) {
    newRepoPaths.value.push(path)
  }
}

function onMultipleDirectoriesSelected(paths: string[]) {
  for (const p of paths) {
    if (!newRepoPaths.value.includes(p)) {
      newRepoPaths.value.push(p)
    }
  }
}

function addPathToList(): void {
  const p = newRepoPath.value.trim()
  if (p && !newRepoPaths.value.includes(p)) {
    newRepoPaths.value.push(p)
  }
  newRepoPath.value = ''
}

async function addReposAndScan(): Promise<void> {
  // If there's text in the input, add it to the list first
  addPathToList()
  if (newRepoPaths.value.length === 0) return

  let anyOk = false
  for (const p of newRepoPaths.value) {
    const ok = await settingsStore.addRepo(p)
    if (ok) anyOk = true
  }
  if (anyOk) {
    showAddRepoDialog.value = false
    newRepoPaths.value = []
    newRepoPath.value = ''
    if (scanAfterAdd.value) {
      triggerScan(false)
    }
  }
}

// Branch mapping dialog
const showBranchDialog = ref(false)
const branchDialogRepo = ref<RepoInfo | null>(null)
const branchDialogBranches = ref<string[]>([])
const branchDialogMain = ref<string | null>(null)
const branchDialogDev = ref<string | null>(null)
const branchesLoading = ref(false)
const branchSaving = ref(false)

async function openBranchDialog(repo: RepoInfo): Promise<void> {
  branchDialogRepo.value = repo
  branchDialogMain.value = repo.mainBranch
  branchDialogDev.value = repo.developBranch
  branchDialogBranches.value = []
  showBranchDialog.value = true
  branchesLoading.value = true

  const data = await settingsStore.fetchRepoBranches(repo.id)
  if (data) {
    branchDialogBranches.value = data.branches
    if (!branchDialogMain.value && data.currentMain) {
      branchDialogMain.value = data.currentMain
    }
    if (!branchDialogDev.value && data.currentDevelop) {
      branchDialogDev.value = data.currentDevelop
    }
  }
  branchesLoading.value = false
}

async function saveBranchMapping(): Promise<void> {
  if (!branchDialogRepo.value) return
  branchSaving.value = true
  await settingsStore.updateRepoBranches(
    branchDialogRepo.value.id,
    branchDialogMain.value,
    branchDialogDev.value,
  )
  branchSaving.value = false
  showBranchDialog.value = false
}

// Rescan confirmation
const showRescanDialog = ref(false)
const pendingFullRescan = ref(false)

// MCP token state
const mcpTokenSet = ref(false)
const newMcpToken = ref('')
const regeneratingToken = ref(false)

const needsClaudeCode = computed(() =>
  settingsStore.connections.aiConfig.preset === 'hybrid'
  || settingsStore.connections.aiConfig.preset === 'claude-ollama'
)

const mcpConfigSnippet = computed(() => {
  const token = newMcpToken.value || '<your-bodhigrove-token>'
  return JSON.stringify({
    mcpServers: {
      bodhigrove: {
        url: 'http://localhost:8000/mcp',
        headers: { Authorization: `Bearer ${token}` },
      },
      gitnexus: {
        command: 'gitnexus',
        args: ['mcp'],
      },
    },
  }, null, 2)
})

onMounted(async () => {
  await settingsStore.fetchConnections()
  checkMcpTokenStatus()
  fetchIndexStats()
  settingsStore.fetchRepos()
})

onUnmounted(() => {
  if (scanPollInterval) {
    clearInterval(scanPollInterval)
    scanPollInterval = null
  }
})

async function save(): Promise<void> {
  await settingsStore.saveConnections()
}

async function checkClaudeCode(): Promise<void> {
  claudeStatus.value = 'checking'
  claudeError.value = ''
  claudeVersion.value = ''

  try {
    const { data } = await api.get('/setup/check-claude', { timeout: 120_000 })
    if (data.cli_available && data.test_passed) {
      claudeStatus.value = 'passed'
      claudeVersion.value = data.output || ''
    } else {
      claudeStatus.value = 'failed'
      claudeError.value = data.error || 'Claude Code CLI is not available or test failed.'
    }
  } catch {
    claudeStatus.value = 'failed'
    claudeError.value = 'Could not reach the server to test Claude Code.'
  }
}

async function fetchIndexStats(): Promise<void> {
  try {
    const { data } = await api.get('/v1/skills/index-stats')
    indexStats.value = data
  } catch {
    // Non-critical
  }
}

function confirmAndScan(fullRescan: boolean): void {
  // If no existing index, skip confirmation
  if (!indexStats.value || indexStats.value.knowledgeItems.total === 0) {
    triggerScan(fullRescan)
    return
  }
  pendingFullRescan.value = fullRescan
  showRescanDialog.value = true
}

function proceedWithScan(): void {
  showRescanDialog.value = false
  triggerScan(pendingFullRescan.value)
}

function formatRelativeTime(isoDate: string): string {
  const now = Date.now()
  const then = new Date(isoDate).getTime()
  const diffMs = now - then
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  return `${diffDay}d ago`
}

async function triggerScan(fullRescan: boolean = false): Promise<void> {
  scanStatus.value = 'running'
  scanProgress.value = 0
  scanStatusLabel.value = 'Saving path...'
  scanError.value = ''

  try {
    // Auto-save source code settings before scanning so the backend has the latest path
    await api.patch('/v1/settings/connections', {
      sourceCode: {
        localPath: settingsStore.connections.sourceCode.localPath,
        type: settingsStore.connections.sourceCode.type,
      },
    })
  } catch {
    scanStatus.value = 'failed'
    scanError.value = 'Failed to save source code path. Please try saving settings first.'
    return
  }

  try {
    scanStatusLabel.value = 'Starting'
    const { data } = await api.post('/v1/skills/scan', { fullRescan: Boolean(fullRescan) })
    currentScanId = data.scanId
    startPolling()
  } catch (err: unknown) {
    scanStatus.value = 'failed'
    const axiosErr = err as { response?: { data?: { detail?: string } } }
    scanError.value = axiosErr?.response?.data?.detail || 'Failed to start scan.'
  }
}

function startPolling(): void {
  if (scanPollInterval) clearInterval(scanPollInterval)

  // Request notification permission early
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }

  scanPollInterval = setInterval(async () => {
    try {
      const { data } = await api.get(`/v1/skills/scan/${currentScanId}/status`)
      scanProgress.value = data.progressPct || 0
      scanStatusLabel.value = formatStatusLabel(data.status)

      if (data.status === 'completed') {
        scanStatus.value = 'completed'
        scanResult.value = {
          scanMode: data.scanMode || 'full',
          featuresIndexed: data.featuresIndexed || 0,
          featuresSkipped: data.featuresSkipped || 0,
          profilesFound: data.profilesFound || 0,
          staleCleaned: data.staleCleaned || 0,
          unmatchedAuthors: data.unmatchedAuthors || [],
          synthesisWarning: data.synthesisWarning || '',
        }
        stopPolling()
        fetchIndexStats()
        notifyScanDone(true, data.featuresIndexed || 0, data.profilesFound || 0)
      } else if (data.status === 'failed') {
        scanStatus.value = 'failed'
        scanError.value = data.error || 'Scan failed.'
        stopPolling()
        notifyScanDone(false)
      }
    } catch {
      scanStatus.value = 'failed'
      scanError.value = 'Lost connection while polling scan status.'
      stopPolling()
    }
  }, 2000)
}

function notifyScanDone(success: boolean, features = 0, profiles = 0): void {
  if (!('Notification' in window) || Notification.permission !== 'granted') return

  const title = success ? 'Repository Scan Complete' : 'Repository Scan Failed'
  const body = success
    ? `${features} features indexed, ${profiles} skill profiles found.`
    : scanError.value || 'An error occurred during scanning.'

  new Notification(title, { body, icon: '/favicon.ico' })
}

async function refreshScanStatus(): Promise<void> {
  if (!currentScanId) return
  try {
    const { data } = await api.get(`/v1/skills/scan/${currentScanId}/status`)
    scanProgress.value = data.progressPct || 0
    scanStatusLabel.value = formatStatusLabel(data.status)

    if (data.status === 'completed') {
      scanStatus.value = 'completed'
      scanResult.value = {
        scanMode: data.scanMode || 'full',
        featuresIndexed: data.featuresIndexed || 0,
        featuresSkipped: data.featuresSkipped || 0,
        profilesFound: data.profilesFound || 0,
        staleCleaned: data.staleCleaned || 0,
        unmatchedAuthors: data.unmatchedAuthors || [],
        synthesisWarning: data.synthesisWarning || '',
      }
      stopPolling()
    } else if (data.status === 'failed') {
      scanStatus.value = 'failed'
      scanError.value = data.error || 'Scan failed.'
      stopPolling()
    }
  } catch {
    // Non-critical, user can try again
  }
}

function stopPolling(): void {
  if (scanPollInterval) {
    clearInterval(scanPollInterval)
    scanPollInterval = null
  }
}

function formatStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    started: 'Starting',
    analyzing_changes: 'Analyzing changes',
    indexing: 'Indexing codebase',
    synthesizing_features: 'Synthesizing feature descriptions',
    merging_features: 'Merging cross-repo features',
    cleaning_stale: 'Cleaning stale references',
    analyzing_skills: 'Analyzing skills',
    embedding: 'Generating embeddings',
    completed: 'Complete',
    failed: 'Failed',
  }
  return labels[status] || status
}

async function checkMcpTokenStatus(): Promise<void> {
  try {
    const { data } = await api.get('/v1/settings/mcp-token/status')
    mcpTokenSet.value = data.has_token
  } catch {
    // Token status check is non-critical
  }
}

async function regenerateMcpToken(): Promise<void> {
  regeneratingToken.value = true
  try {
    const { data } = await api.post('/v1/settings/mcp-token')
    newMcpToken.value = data.mcp_token
    mcpTokenSet.value = true
  } catch {
    settingsStore.error = 'Failed to generate MCP token.'
  } finally {
    regeneratingToken.value = false
  }
}

function copyToken(): void {
  navigator.clipboard.writeText(newMcpToken.value)
}

function copyConfig(): void {
  navigator.clipboard.writeText(mcpConfigSnippet.value)
}

// Slack manifest for quick app creation
const slackManifest = JSON.stringify({
  display_information: {
    name: 'Bodhigrove',
    description: 'Bodhigrove code intelligence notifications and agent triggers',
  },
  features: {
    bot_user: {
      display_name: 'Bodhigrove',
      always_online: true,
    },
  },
  oauth_config: {
    scopes: {
      bot: [
        'chat:write',
        'channels:read',
        'channels:history',
        'channels:join',
        'reactions:read',
        'users:read',
        'users:read.email',
        'groups:history',
      ],
    },
  },
  settings: {
    event_subscriptions: {
      bot_events: [
        'reaction_added',
        'message.channels',
        'message.groups',
      ],
    },
    org_deploy_enabled: false,
    socket_mode_enabled: false,
    token_rotation_enabled: false,
  },
}, null, 2)

const slackManifestOpen = ref(false)
const slackEventsOpen = ref(false)
const slackSyncOpen = ref(false)

// Slack member sync
interface SlackMemberPreview {
  slack_id: string
  slack_name: string
  slack_avatar: string | null
  matched_user_id: string | null
  matched_user_name: string | null
  already_linked: boolean
}

const slackMembers = ref<SlackMemberPreview[]>([])
const slackLinkMap = ref<Record<string, string>>({})
const slackSyncLoading = ref(false)
const slackSyncError = ref('')
const slackLinkLoading = ref(false)
const slackLinkSuccess = ref('')

const flowdevMemberOptions = computed(() =>
  membersStore.members
    .filter(m => m.isActive)
    .map(m => ({ id: m.id, name: `${m.name} (${m.email})` }))
)

async function fetchSlackMembers(): Promise<void> {
  slackSyncLoading.value = true
  slackSyncError.value = ''
  slackLinkSuccess.value = ''
  try {
    const { data } = await api.post('/v1/settings/slack/sync-members')
    slackMembers.value = data
    // Pre-populate link map with email-matched suggestions
    slackLinkMap.value = {}
    for (const m of data) {
      if (m.matched_user_id && !m.already_linked) {
        slackLinkMap.value[m.slack_id] = m.matched_user_id
      }
    }
    slackSyncOpen.value = true
    // Ensure we have members loaded for the dropdown
    if (membersStore.members.length === 0) {
      await membersStore.fetchMembers()
    }
  } catch {
    slackSyncError.value = 'Failed to fetch Slack members. Check bot token.'
  } finally {
    slackSyncLoading.value = false
  }
}

async function linkSlackMembers(): Promise<void> {
  slackLinkLoading.value = true
  slackLinkSuccess.value = ''
  try {
    const links = Object.entries(slackLinkMap.value)
      .filter(([, userId]) => userId)
      .map(([slackId, userId]) => ({ slack_id: slackId, user_id: userId }))
    const { data } = await api.post('/v1/settings/slack/link-members', { links })
    slackLinkSuccess.value = `Linked ${data.linked} member${data.linked !== 1 ? 's' : ''} successfully.`
    // Refresh to show updated links
    await fetchSlackMembers()
  } catch {
    slackSyncError.value = 'Failed to link members.'
  } finally {
    slackLinkLoading.value = false
  }
}

async function unlinkSlackMember(slackId: string): Promise<void> {
  try {
    await api.post('/v1/settings/slack/unlink-member', { slack_id: slackId })
    await fetchSlackMembers()
  } catch {
    slackSyncError.value = 'Failed to unlink member.'
  }
}

function dismissSlackMember(slackId: string): void {
  slackMembers.value = slackMembers.value.filter(m => m.slack_id !== slackId)
  delete slackLinkMap.value[slackId]
}

const manifestCopied = ref(false)
let manifestCopyTimer: ReturnType<typeof setTimeout> | undefined

function copySlackManifest(): void {
  navigator.clipboard.writeText(slackManifest)
  manifestCopied.value = true
  clearTimeout(manifestCopyTimer)
  manifestCopyTimer = setTimeout(() => { manifestCopied.value = false }, 2000)
}

// Webhook URL for Slack Event Subscriptions
const webhookUrl = `${window.location.origin}/api/v1/slack/events`

function copyWebhookUrl(): void {
  navigator.clipboard.writeText(webhookUrl)
}

// Preset definitions
const presets = [
  {
    value: 'hybrid',
    icon: 'mdi-shuffle-variant',
    title: 'Hybrid',
    description: 'Claude Code for codebase agents, Cloud API for the rest.',
    recommended: true,
  },
  {
    value: 'claude-ollama',
    icon: 'mdi-console-network',
    title: 'Claude + Ollama',
    description: 'Claude Code for codebase agents, Ollama for the rest.',
  },
  {
    value: 'cloud',
    icon: 'mdi-cloud-outline',
    title: 'Cloud API',
    description: 'Use Anthropic or OpenAI for all agents.',
  },
  {
    value: 'local',
    icon: 'mdi-server-outline',
    title: 'Local (Ollama)',
    description: 'Run everything locally. No API keys needed.',
  },
]

const cloudProviders = [
  { title: 'Anthropic', value: 'anthropic' },
  { title: 'OpenAI', value: 'openai' },
]

const maxTurnsOptions = [
  { title: '20 steps', value: 20 },
  { title: '40 steps (default)', value: 40 },
  { title: '60 steps', value: 60 },
  { title: '80 steps', value: 80 },
  { title: '100 steps', value: 100 },
  { title: 'Unlimited', value: 0 },
]

const activePresetTitle = computed(() => {
  const p = presets.find(p => p.value === settingsStore.connections.aiConfig.preset)
  return p?.title ?? 'AI'
})

const activePresetHint = computed(() => {
  switch (settingsStore.connections.aiConfig.preset) {
    case 'local': return 'All 11 agents will use Ollama running on your machine.'
    case 'cloud': return 'All 11 agents will use the selected cloud provider.'
    case 'hybrid': return 'Codebase agents use Claude Code; other agents use the Cloud API.'
    case 'claude-ollama': return 'Codebase agents use Claude Code; other agents use Ollama locally.'
    default: return ''
  }
})
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.settings-header {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgb(var(--v-theme-background));
  z-index: 1;
}

.settings-content {
  flex: 1;
  overflow-y: auto;
  padding-top: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.settings-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.2s ease;
}

.settings-card--active {
  border-color: rgba(var(--v-theme-primary), 0.4);
}

.preset-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.preset-card--active {
  border-color: rgb(var(--v-theme-primary)) !important;
  background: rgba(var(--v-theme-primary), 0.04) !important;
}

.coming-soon-card {
  opacity: 0.45;
  border-style: dashed !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
  transition: opacity 0.2s ease;
}

.coming-soon-card:hover {
  opacity: 0.6;
}

.coming-soon-avatar {
  background: rgba(255, 255, 255, 0.04);
}

.index-stat {
  min-width: 64px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  text-align: center;
}
</style>

<style>
/* Global (not scoped) — Vuetify renders tooltips in a portal outside this component */
.scan-tooltip {
  color: #fff !important;
  background: #1e1e2e !important;
  font-size: 13px !important;
  line-height: 1.5 !important;
  padding: 10px 14px !important;
}
</style>
