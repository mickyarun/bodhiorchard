// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Slack member sync for Settings → Integrations → Slack: fetch the
 * workspace's people, decide per person whether to link them to an
 * existing member or import them as a new one, then save both lists.
 */
import { computed, ref } from 'vue'
import api from '@/services/api'
import { useMembersStore } from '@/stores/members'
import { plural } from '@/utils/format'

export interface SlackMemberPreview {
  slack_id: string
  slack_name: string
  slack_avatar: string | null
  slack_email: string | null
  matched_user_id: string | null
  matched_user_name: string | null
  already_linked: boolean
}

export type SlackAction = 'link' | 'import'

export function useSlackMemberSync() {
  const membersStore = useMembersStore()

  const members = ref<SlackMemberPreview[]>([])
  const actions = ref<Record<string, SlackAction>>({})
  const links = ref<Record<string, string>>({})
  const syncing = ref(false)
  const saving = ref(false)
  const error = ref('')
  const success = ref('')

  function actionFor(slackId: string): SlackAction {
    return actions.value[slackId] ?? 'link'
  }

  function setAction(slackId: string, action: SlackAction): void {
    actions.value = { ...actions.value, [slackId]: action }
  }

  function setLink(slackId: string, userId: string | null): void {
    const next = { ...links.value }
    if (userId) next[slackId] = userId
    else delete next[slackId]
    links.value = next
  }

  function dismiss(slackId: string): void {
    members.value = members.value.filter(m => m.slack_id !== slackId)
    const a = { ...actions.value }
    delete a[slackId]
    actions.value = a
    setLink(slackId, null)
  }

  const toLink = computed(() =>
    Object.entries(links.value)
      .filter(([id, userId]) => actionFor(id) === 'link' && userId)
      .map(([slackId, userId]) => ({ slack_id: slackId, user_id: userId })),
  )
  const importing = computed(() => members.value.filter(m => actions.value[m.slack_id] === 'import'))
  const toImport = computed(() => importing.value.filter(m => m.slack_email))
  const importWithoutEmail = computed(() => importing.value.length - toImport.value.length)

  async function sync(): Promise<void> {
    syncing.value = true
    error.value = ''
    success.value = ''
    try {
      const { data } = await api.post<SlackMemberPreview[]>('/v1/settings/slack/sync-members')
      members.value = data
      const nextActions: Record<string, SlackAction> = {}
      const nextLinks: Record<string, string> = {}
      for (const m of data) {
        if (m.already_linked) continue
        nextActions[m.slack_id] = m.matched_user_id ? 'link' : 'import'
        if (m.matched_user_id) nextLinks[m.slack_id] = m.matched_user_id
      }
      actions.value = nextActions
      links.value = nextLinks
      if (membersStore.members.length === 0) await membersStore.fetchMembers()
    } catch {
      error.value = 'Could not fetch Slack members. Check the bot token.'
    } finally {
      syncing.value = false
    }
  }

  async function unlink(slackId: string): Promise<void> {
    try {
      await api.post('/v1/settings/slack/unlink-member', { slack_id: slackId })
      await sync()
    } catch {
      error.value = 'Could not unlink the member.'
    }
  }

  async function save(): Promise<void> {
    saving.value = true
    error.value = ''
    success.value = ''
    const messages: string[] = []
    try {
      if (toLink.value.length > 0) {
        const { data } = await api.post('/v1/settings/slack/link-members', { links: toLink.value })
        messages.push(`Linked ${plural(data.linked, 'member')}`)
      }
      if (toImport.value.length > 0) {
        // No photo URL: the backend fetches it from Slack itself.
        const imports = toImport.value.map(m => ({ slack_id: m.slack_id, slack_name: m.slack_name, slack_email: m.slack_email }))
        const { data } = await api.post('/v1/settings/slack/import-members', { imports })
        messages.push(`Imported ${plural(data.imported, 'member')}`)
        if (data.skipped?.length) messages.push(`skipped ${data.skipped.length} who already exist`)
        await membersStore.fetchMembers()
      }
      success.value = `${messages.join(', ')}.`
      members.value = []
      actions.value = {}
      links.value = {}
    } catch {
      error.value = 'Could not save the changes.'
    } finally {
      saving.value = false
    }
  }

  return {
    members, links, syncing, saving, error, success,
    toLink, toImport, importWithoutEmail,
    actionFor, setAction, setLink, dismiss, sync, unlink, save,
  }
}
