<template>
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
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useMembersStore } from '@/stores/members'
import api from '@/services/api'

const settingsStore = useSettingsStore()
const membersStore = useMembersStore()

const slackManifestOpen = ref(false)
const slackEventsOpen = ref(false)
const slackSyncOpen = ref(false)

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
    slackLinkMap.value = {}
    for (const m of data) {
      if (m.matched_user_id && !m.already_linked) {
        slackLinkMap.value[m.slack_id] = m.matched_user_id
      }
    }
    slackSyncOpen.value = true
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
</script>
