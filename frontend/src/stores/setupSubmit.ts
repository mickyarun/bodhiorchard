// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Submit-side actions for the setup store.
 *
 * Phase H split the legacy single-shot ``POST /setup/initialize`` into the
 * Phase D two-stage flow:
 *
 *   1. ``POST /setup/init-org``         — org/admin/claude/scan settings.
 *   2. ``POST /setup/finalize-with-repos`` — repo selection (legacy paste shape
 *      OR Phase B installable items shape).
 *
 * The legacy ``submitSetup()`` action stays as a back-compat shim that calls
 * both internally.
 */

import type { Ref } from 'vue'
import type { SetupState } from '@/types/setup'
import api from '@/services/api'
import { resetSetupCache } from '@/router'
import { useAuthStore } from '@/stores/auth'

const ENDPOINT_INIT_ORG = '/setup/init-org'
const ENDPOINT_FINALIZE = '/setup/finalize-with-repos'
const TOKEN_KEY = 'bodhiorchard_token'
const SETUP_COMPLETE_KEY = 'bodhiorchard_setup_complete'

export interface OrgInitResult {
  orgSlug: string
  orgId: string
  accessToken: string
}

export interface FinalizeResult {
  jobId?: string
  scanId?: string
  isSetupComplete: true
}

export interface SubmitContext {
  state: Ref<SetupState>
  submitError: Ref<string | null>
  scanId: Ref<string | null>
  jobId: Ref<string | null>
}

function applyAxiosError(ctx: SubmitContext, err: unknown, fallback: string): void {
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as {
      response?: { status?: number; data?: { detail?: string; message?: string } }
    }
    ctx.submitError.value =
      axiosErr.response?.data?.detail
      || axiosErr.response?.data?.message
      || fallback
  } else {
    ctx.submitError.value = 'Network error. Please check your connection.'
  }
}

export async function submitOrgInit(ctx: SubmitContext): Promise<OrgInitResult | null> {
  ctx.submitError.value = null
  try {
    const s = ctx.state.value
    const payload = {
      organization: s.organization,
      admin: s.admin,
      scan: s.scan,
      claude: {
        authMode: s.claude.authMode,
        apiKey:
          s.claude.authMode === 'api_key' && s.claude.apiKey
            ? s.claude.apiKey
            : null,
      },
    }
    const { data } = await api.post(ENDPOINT_INIT_ORG, payload)
    const result: OrgInitResult = {
      orgSlug: data.orgSlug || data.org_slug,
      orgId: data.orgId || data.org_id,
      accessToken: data.accessToken || data.access_token,
    }
    if (result.accessToken) {
      localStorage.setItem(TOKEN_KEY, result.accessToken)
      // Populate auth.user so subsequent wizard steps that depend on
      // user.org_id (e.g. WS subscription in GitHubAppConnectionCard's
      // useInstallSocket) have the id available immediately. Without
      // this the user object is null until the next route navigation
      // triggers the router-guard fetchUser, which never happens
      // inside the single-route wizard.
      try {
        await useAuthStore().fetchUser()
      } catch {
        // Non-fatal — the wizard can proceed; downstream features that
        // need user.org_id will retry on their own watchers.
      }
    }
    return result
  } catch (err: unknown) {
    applyAxiosError(ctx, err, 'Org init failed. Please try again.')
    return null
  }
}

export async function submitFinalize(ctx: SubmitContext): Promise<FinalizeResult | null> {
  ctx.submitError.value = null
  try {
    const repos = ctx.state.value.sourceCode.repos
    const bulkRepos = repos.filter(r => !!r.gitHubFullName)
    const useInstallableShape = bulkRepos.length > 0 && bulkRepos.length === repos.length
    const body = useInstallableShape
      ? {
          installableItems: bulkRepos.map(r => ({
            fullName: r.gitHubFullName as string,
            mainBranch: r.mainBranch || '',
            developBranch: r.developBranch || undefined,
          })),
        }
      : {
          sourceCode: ctx.state.value.sourceCode,
        }
    const { data } = await api.post(ENDPOINT_FINALIZE, body)
    localStorage.setItem(SETUP_COMPLETE_KEY, 'true')
    if (data.scanId) ctx.scanId.value = data.scanId
    if (data.jobId) ctx.jobId.value = data.jobId
    resetSetupCache()
    return {
      jobId: data.jobId,
      scanId: data.scanId,
      isSetupComplete: true,
    }
  } catch (err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const axiosErr = err as { response?: { status?: number } }
      if (axiosErr.response?.status === 409) {
        localStorage.setItem(SETUP_COMPLETE_KEY, 'true')
        resetSetupCache()
        return { isSetupComplete: true }
      }
    }
    applyAxiosError(ctx, err, 'Setup finalize failed. Please try again.')
    return null
  }
}
