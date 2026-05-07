// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * State + orchestration for adding repositories on /settings/code.
 *
 * Two flows share this composable:
 *   - Local pick: user selects directories via DirectoryPicker; we POST
 *     each path to /v1/settings/repos one at a time.
 *   - GitHub clone: user queues HTTPS / SSH URLs (with optional shared
 *     PAT); we POST each to /v1/settings/repos/clone serially so failures
 *     are isolated and partial successes are visible.
 *
 * The per-item `status` field drives the chip colours in the UI; the
 * page never has to introspect the URL/path itself.
 */

import { computed, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'

export type ImportItemStatus = 'pending' | 'running' | 'done' | 'error'

export interface ImportItem {
  /** URL for clone, absolute path for local pick. */
  source: string
  status: ImportItemStatus
  error?: string
}

/** Classify a git URL string. `null` means we don't recognise the shape
 * — the form uses this for both validation and choosing which auth path
 * (PAT vs deploy key) the runner threads through.
 *
 * The patterns are deliberately strict: requiring at least owner/repo
 * after the host catches the common paste mistake of dropping the repo
 * segment.
 */
function classifyGitUrl(url: string): 'https' | 'ssh' | null {
  const v = url.trim()
  if (!v) return null
  if (/^https?:\/\/[^\s/]+\/[^\s/]+\/[^\s/]+/.test(v)) return 'https'
  if (/^git@[^\s:]+:[^\s/]+\/[^\s]+$/.test(v)) return 'ssh'
  if (/^ssh:\/\/git@[^\s/]+\/[^\s/]+\/[^\s/]+/.test(v)) return 'ssh'
  return null
}

function isSshUrl(url: string): boolean {
  return classifyGitUrl(url) === 'ssh'
}

export function useRepoImport() {
  const settingsStore = useSettingsStore()

  const localPaths = ref<ImportItem[]>([])
  const cloneItems = ref<ImportItem[]>([])
  const sharedPat = ref<string>('')
  const usePrivateAuth = ref<boolean>(false)
  const running = ref<boolean>(false)
  const lastError = ref<string>('')

  const hasPendingLocal = computed(() =>
    localPaths.value.some(i => i.status === 'pending' || i.status === 'error'),
  )
  const hasPendingClones = computed(() =>
    cloneItems.value.some(i => i.status === 'pending' || i.status === 'error'),
  )

  function addLocalPath(path: string): void {
    if (!path) return
    if (localPaths.value.some(i => i.source === path)) return
    localPaths.value.push({ source: path, status: 'pending' })
  }

  function addLocalPaths(paths: string[]): void {
    for (const p of paths) addLocalPath(p)
  }

  function removeLocalPath(idx: number): void {
    if (localPaths.value[idx]?.status === 'running') return
    localPaths.value.splice(idx, 1)
  }

  function addCloneUrl(url: string): boolean {
    const trimmed = url.trim()
    if (!trimmed) return false
    if (cloneItems.value.some(i => i.source === trimmed)) return false
    cloneItems.value.push({ source: trimmed, status: 'pending' })
    return true
  }

  function removeCloneItem(idx: number): void {
    if (cloneItems.value[idx]?.status === 'running') return
    cloneItems.value.splice(idx, 1)
  }

  function reset(): void {
    localPaths.value = []
    cloneItems.value = []
    sharedPat.value = ''
    usePrivateAuth.value = false
    lastError.value = ''
  }

  async function runLocal(): Promise<boolean> {
    if (running.value) return false
    running.value = true
    lastError.value = ''
    let allOk = true
    try {
      for (const item of localPaths.value) {
        if (item.status === 'done') continue
        item.status = 'running'
        item.error = undefined
        const ok = await settingsStore.addRepo(item.source)
        if (ok) {
          item.status = 'done'
        } else {
          item.status = 'error'
          item.error = settingsStore.error || 'Add failed.'
          allOk = false
        }
      }
    } finally {
      running.value = false
    }
    return allOk
  }

  async function runClones(): Promise<boolean> {
    if (running.value) return false
    running.value = true
    lastError.value = ''
    let allOk = true
    try {
      for (const item of cloneItems.value) {
        if (item.status === 'done') continue
        item.status = 'running'
        item.error = undefined
        const pat = usePrivateAuth.value && !isSshUrl(item.source)
          ? sharedPat.value.trim() || null
          : null
        const ok = await settingsStore.cloneRepo(item.source, pat)
        if (ok) {
          item.status = 'done'
        } else {
          item.status = 'error'
          item.error = settingsStore.error || 'Clone failed.'
          allOk = false
        }
      }
    } finally {
      running.value = false
    }
    return allOk
  }

  return {
    // state
    localPaths,
    cloneItems,
    sharedPat,
    usePrivateAuth,
    running,
    lastError,
    // derived
    hasPendingLocal,
    hasPendingClones,
    // actions
    addLocalPath,
    addLocalPaths,
    removeLocalPath,
    addCloneUrl,
    removeCloneItem,
    runLocal,
    runClones,
    reset,
    // helpers
    isSshUrl,
    classifyGitUrl,
  }
}
