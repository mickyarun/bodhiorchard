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
 * The connected GitHub organization's people for the Members import
 * dialog: who is there, who is already added, and the current selection
 * (everyone importable is selected when the list loads).
 */
import { computed, ref } from 'vue'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

export interface GithubOrgMember {
  login: string
  name: string | null
  avatar_url: string
  email: string | null
  already_added: boolean
}

export function useGithubOrgMembers() {
  const members = ref<GithubOrgMember[]>([])
  const selected = ref<GithubOrgMember[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref('')

  const importable = computed(() => members.value.filter(m => !m.already_added))
  const addedCount = computed(() => members.value.length - importable.value.length)
  const allSelected = computed(
    () => importable.value.length > 0 && selected.value.length === importable.value.length,
  )

  async function load(): Promise<void> {
    loading.value = true
    loaded.value = false
    error.value = ''
    selected.value = []
    try {
      const { data } = await api.get<GithubOrgMember[]>('/v1/settings/github/org-members')
      members.value = data
      selected.value = data.filter(m => !m.already_added)
    } catch (err) {
      members.value = []
      error.value = extractApiError(err, 'Could not load the GitHub organization. Check the GitHub settings.')
    } finally {
      loading.value = false
      loaded.value = true
    }
  }

  function isSelected(login: string): boolean {
    return selected.value.some(m => m.login === login)
  }

  function toggle(member: GithubOrgMember): void {
    if (member.already_added) return
    selected.value = isSelected(member.login)
      ? selected.value.filter(m => m.login !== member.login)
      : [...selected.value, member]
  }

  function toggleAll(): void {
    selected.value = allSelected.value ? [] : [...importable.value]
  }

  return { members, selected, loading, loaded, error, importable, addedCount, allSelected, load, isSelected, toggle, toggleAll }
}
