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

        <!-- Slack Member Sync — NOT collapsible, always visible when Slack is enabled -->
        <div
          class="rounded-lg pa-4"
          style="border: 1px solid rgba(var(--v-theme-on-surface), 0.08);"
        >
          <div class="d-flex align-center ga-2 mb-3">
            <v-icon icon="mdi-account-sync-outline" size="18" color="primary" />
            <span class="text-body-2 font-weight-medium">Sync Members</span>
            <v-spacer />
            <v-btn
              size="small"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-sync"
              :loading="slackSyncLoading"
              @click="fetchSlackMembers"
            >
              Sync
            </v-btn>
          </div>

          <div class="text-caption text-medium-emphasis mb-3">
            Link Slack workspace users to Bodhigrove members, or import them as new members.
            <br />
            <strong>Required scopes:</strong>
            <v-chip size="x-small" variant="tonal" color="primary" class="ml-1">users:read</v-chip>
            <v-chip size="x-small" variant="tonal" color="primary" class="ml-1">users:read.email</v-chip>
          </div>

          <v-alert v-if="slackSyncError" type="error" variant="tonal" density="compact" class="mb-3">
            {{ slackSyncError }}
          </v-alert>

          <template v-if="slackMembers.length > 0">
            <!-- Member list -->
            <div
              v-for="member in slackMembers"
              :key="member.slack_id"
              class="d-flex align-center ga-3 py-2"
              style="border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.05);"
            >
              <!-- Avatar -->
              <v-avatar size="32" color="primary" variant="tonal">
                <v-img
                  v-if="member.slack_avatar"
                  :src="member.slack_avatar"
                  :alt="member.slack_name"
                  referrerpolicy="no-referrer"
                  cover
                />
                <span v-else class="text-caption">
                  {{ member.slack_name.charAt(0).toUpperCase() }}
                </span>
              </v-avatar>

              <!-- Name + email -->
              <div style="min-width: 130px;">
                <div class="text-body-2 font-weight-medium">{{ member.slack_name }}</div>
                <div v-if="member.slack_email" class="text-caption text-medium-emphasis" style="margin-top: -2px;">
                  {{ member.slack_email }}
                </div>
              </div>

              <v-icon icon="mdi-arrow-right" size="16" class="text-medium-emphasis" />

              <!-- Already linked -->
              <template v-if="member.already_linked">
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
              </template>

              <!-- Unlinked -->
              <template v-else>
                <!-- Action toggle: two plain buttons -->
                <v-btn
                  :variant="getAction(member.slack_id) === 'link' ? 'flat' : 'outlined'"
                  :color="getAction(member.slack_id) === 'link' ? 'primary' : 'default'"
                  size="x-small"
                  @click="setAction(member.slack_id, 'link')"
                >
                  Link
                </v-btn>
                <v-btn
                  :variant="getAction(member.slack_id) === 'import' ? 'flat' : 'outlined'"
                  :color="getAction(member.slack_id) === 'import' ? 'success' : 'default'"
                  size="x-small"
                  @click="setAction(member.slack_id, 'import')"
                >
                  Import
                </v-btn>

                <!-- Link mode: autocomplete -->
                <v-autocomplete
                  v-if="getAction(member.slack_id) === 'link'"
                  :model-value="slackLinkMap[member.slack_id] ?? null"
                  :items="memberOptions"
                  item-title="name"
                  item-value="id"
                  density="compact"
                  variant="outlined"
                  hide-details
                  placeholder="Search member..."
                  clearable
                  auto-select-first
                  style="max-width: 220px;"
                  @update:model-value="onLinkSelect(member.slack_id, $event)"
                />

                <!-- X to remove from list -->
                <v-btn
                  icon="mdi-close"
                  size="x-small"
                  variant="text"
                  color="medium-emphasis"
                  title="Remove from list"
                  @click="dismissSlackMember(member.slack_id)"
                />
              </template>
            </div>

            <!-- Summary + Save -->
            <div class="d-flex align-center ga-3 mt-4">
              <v-chip v-if="linkCount > 0" color="primary" variant="tonal" size="small" prepend-icon="mdi-link-variant">
                {{ linkCount }} to link
              </v-chip>
              <v-chip v-if="importCount > 0" color="success" variant="tonal" size="small" prepend-icon="mdi-account-plus">
                {{ importCount }} to import
              </v-chip>
              <v-spacer />
              <v-btn
                color="primary"
                variant="flat"
                size="small"
                prepend-icon="mdi-content-save"
                :loading="slackLinkLoading || slackImportLoading"
                :disabled="linkCount === 0 && importCount === 0"
                @click="saveChanges"
              >
                Save Changes
              </v-btn>
            </div>

            <v-alert
              v-if="importNoEmailCount > 0"
              type="warning"
              variant="tonal"
              density="compact"
              class="mt-2"
            >
              {{ importNoEmailCount }} member{{ importNoEmailCount !== 1 ? 's' : '' }} set to Import but missing email.
              Add <strong>users:read.email</strong> to <strong>Bot Token Scopes</strong> (not User Token Scopes) in your Slack app, then reinstall and re-sync.
            </v-alert>

            <v-alert
              v-if="slackLinkSuccess"
              type="success"
              variant="tonal"
              density="compact"
              class="mt-2"
            >
              {{ slackLinkSuccess }}
            </v-alert>
          </template>

          <div v-else-if="!slackSyncLoading" class="text-caption text-medium-emphasis">
            Click "Sync" to fetch Slack workspace members.
          </div>
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

// ─── Slack Member Sync ──────────────────────────

interface SlackMemberPreview {
  slack_id: string
  slack_name: string
  slack_avatar: string | null
  slack_email: string | null
  matched_user_id: string | null
  matched_user_name: string | null
  already_linked: boolean
}

type SlackAction = 'link' | 'import'

const slackMembers = ref<SlackMemberPreview[]>([])
const slackLinkMap = ref<Record<string, string>>({})
const slackActionMap = ref<Record<string, SlackAction>>({})
const slackSyncLoading = ref(false)
const slackSyncError = ref('')
const slackLinkLoading = ref(false)
const slackImportLoading = ref(false)
const slackLinkSuccess = ref('')

const memberOptions = computed(() =>
  membersStore.members
    .filter(m => m.isActive)
    .map(m => ({ id: m.id, name: `${m.name} (${m.email})` })),
)

// ─── Explicit getters/setters (avoid v-model on dynamic record keys) ───

function getAction(slackId: string): SlackAction {
  return slackActionMap.value[slackId] ?? 'link'
}

function setAction(slackId: string, action: SlackAction): void {
  slackActionMap.value = { ...slackActionMap.value, [slackId]: action }
}

function onLinkSelect(slackId: string, userId: string | null): void {
  if (userId) {
    slackLinkMap.value = { ...slackLinkMap.value, [slackId]: userId }
  } else {
    const copy = { ...slackLinkMap.value }
    delete copy[slackId]
    slackLinkMap.value = copy
  }
}

function dismissSlackMember(slackId: string): void {
  slackMembers.value = slackMembers.value.filter(m => m.slack_id !== slackId)
  const a = { ...slackActionMap.value }; delete a[slackId]; slackActionMap.value = a
  const l = { ...slackLinkMap.value }; delete l[slackId]; slackLinkMap.value = l
}

// ─── Counts ─────────────────────────────────────

const linkCount = computed(() => {
  let n = 0
  for (const [id, action] of Object.entries(slackActionMap.value)) {
    if (action === 'link' && slackLinkMap.value[id]) n++
  }
  return n
})

const importCount = computed(() => {
  let n = 0
  for (const [id, action] of Object.entries(slackActionMap.value)) {
    const member = slackMembers.value.find(m => m.slack_id === id)
    if (action === 'import' && member?.slack_email) n++
  }
  return n
})

const importNoEmailCount = computed(() => {
  let n = 0
  for (const [id, action] of Object.entries(slackActionMap.value)) {
    const member = slackMembers.value.find(m => m.slack_id === id)
    if (action === 'import' && !member?.slack_email) n++
  }
  return n
})

// ─── API calls ──────────────────────────────────

async function fetchSlackMembers(): Promise<void> {
  slackSyncLoading.value = true
  slackSyncError.value = ''
  slackLinkSuccess.value = ''
  try {
    const { data } = await api.post('/v1/settings/slack/sync-members')

    slackMembers.value = data
    const newActions: Record<string, SlackAction> = {}
    const newLinks: Record<string, string> = {}

    for (const m of data as SlackMemberPreview[]) {
      if (m.already_linked) continue
      if (m.matched_user_id) {
        newActions[m.slack_id] = 'link'
        newLinks[m.slack_id] = m.matched_user_id
      } else {
        newActions[m.slack_id] = 'import'
      }
    }

    // Replace entire objects for guaranteed reactivity
    slackActionMap.value = newActions
    slackLinkMap.value = newLinks
    if (membersStore.members.length === 0) {
      await membersStore.fetchMembers()
    }
  } catch (err) {
    slackSyncError.value = 'Failed to fetch Slack members. Check bot token.'
  } finally {
    slackSyncLoading.value = false
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

async function saveChanges(): Promise<void> {
  slackLinkSuccess.value = ''
  slackSyncError.value = ''
  const messages: string[] = []

  try {
    // Link
    if (linkCount.value > 0) {
      slackLinkLoading.value = true
      const links = Object.entries(slackLinkMap.value)
        .filter(([id]) => slackActionMap.value[id] === 'link')
        .filter(([, userId]) => userId)
        .map(([slackId, userId]) => ({ slack_id: slackId, user_id: userId }))
      const { data } = await api.post('/v1/settings/slack/link-members', { links })
      messages.push(`Linked ${data.linked} member${data.linked !== 1 ? 's' : ''}`)
    }

    // Import
    if (importCount.value > 0) {
      slackImportLoading.value = true
      const imports = slackMembers.value
        .filter(m => slackActionMap.value[m.slack_id] === 'import' && m.slack_email)
        .map(m => ({
          slack_id: m.slack_id,
          slack_name: m.slack_name,
          slack_email: m.slack_email!,
          slack_avatar: m.slack_avatar,
        }))
      const { data } = await api.post('/v1/settings/slack/import-members', { imports })
      messages.push(`Imported ${data.imported} member${data.imported !== 1 ? 's' : ''}`)
      if (data.skipped?.length) {
        messages.push(`Skipped ${data.skipped.length} (already exist)`)
      }
      await membersStore.fetchMembers()
    }

    slackLinkSuccess.value = messages.join('. ') + '.'
    // Reset to pre-sync state
    slackMembers.value = []
    slackActionMap.value = {}
    slackLinkMap.value = {}
  } catch (err) {
    slackSyncError.value = 'Failed to save changes.'
  } finally {
    slackLinkLoading.value = false
    slackImportLoading.value = false
  }
}
</script>
