// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Caches /setup/deployment-info + /setup/deploy-key for the lifetime of
 * the SPA. Both endpoints are immutable per session (mode is decided by
 * how the backend was launched; the deploy key is generated once on
 * first call and persisted) so a single fetch is enough.
 *
 * Module-level refs make the cache shared across every consumer without
 * pulling in Pinia.
 */

import { ref } from 'vue'
import api from '@/services/api'

export type DeploymentMode = 'docker' | 'host'

const mode = ref<DeploymentMode | null>(null)
const deployPublicKey = ref<string>('')
let modeInflight: Promise<void> | null = null
let keyInflight: Promise<void> | null = null

async function loadMode(): Promise<void> {
  if (mode.value !== null) return
  if (modeInflight) return modeInflight
  modeInflight = (async () => {
    try {
      const { data } = await api.get<{ mode?: string }>('/setup/deployment-info')
      mode.value = data.mode === 'docker' ? 'docker' : 'host'
    } catch {
      // Endpoint can fail in odd dev setups — fall back to host so the
      // local-pick tab stays available rather than silently disappearing.
      mode.value = 'host'
    } finally {
      modeInflight = null
    }
  })()
  return modeInflight
}

async function loadDeployKey(): Promise<void> {
  if (deployPublicKey.value) return
  if (keyInflight) return keyInflight
  keyInflight = (async () => {
    // Post-setup endpoint — the /setup/deploy-key route returns 403 once an
    // organization exists. The authenticated /v1/settings/repos/deploy-key
    // helper returns the same public key for ongoing clone-dialog use.
    try {
      const { data } = await api.get<{ public_key?: string }>('/v1/settings/repos/deploy-key')
      deployPublicKey.value = data.public_key || ''
    } catch {
      deployPublicKey.value = ''
    } finally {
      keyInflight = null
    }
  })()
  return keyInflight
}

export function useDeploymentMode() {
  return {
    mode,
    deployPublicKey,
    loadMode,
    loadDeployKey,
  }
}
