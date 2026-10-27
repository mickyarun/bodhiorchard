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

// Follows the agents working on the open BUD through the workflow
// component (BUDWorkflowActions), and derives whether the BUD is locked
// while they run.

import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type BUDWorkflowActions from '@/components/buds/BUDWorkflowActions.vue'
import type { BUDDocument } from '@/types'

type Workflow = InstanceType<typeof BUDWorkflowActions>

export function useBudAgentTracking(
  bud: ComputedRef<BUDDocument | null>,
  workflowRef: Ref<Workflow | null>,
  /** Runs each time the BUD unlocks after an agent run. */
  onAgentFinished: () => void,
) {
  const authStore = useAuthStore()

  // Watch the job id, not the task object: every refetch builds a new
  // task object, and re-tracking on each one fired a job-status REST call
  // per refetch. During the design stage the per-design trackers in
  // BUDDesignPanel own job tracking (each design has its own job id and
  // the task row records only the first); tracking the task here too
  // looped after a per-design cancel.
  const activeAgentJobId = computed(() => {
    const t = bud.value?.active_agent_task
    if (!t?.job_id || (t.status !== 'pending' && t.status !== 'running')) return null
    return bud.value?.status === 'design' ? null : t.job_id
  })
  watch(
    [activeAgentJobId, workflowRef],
    ([jobId, wf]) => {
      const task = bud.value?.active_agent_task
      if (jobId && wf && task) wf.trackAgentTask(task)
    },
    { immediate: true },
  )

  // The org-wide agent_activity stream covers phase workers that have no
  // task row (assignment, todo generation, estimation), so the banner and
  // the lock stay accurate end to end. The workflow dedupes per BUD and
  // unsubscribes itself before it unmounts.
  watch(
    [() => bud.value?.id, () => authStore.user?.org_id, workflowRef],
    ([budId, orgId, wf]) => {
      if (budId && orgId && wf) wf.trackAgentActivity(orgId, budId)
    },
    { immediate: true },
  )

  // Locked while an agent task is pending or running, or any phase worker
  // is in flight: the stage menu and every gated control disable.
  const agentLocked = computed(() => {
    const t = bud.value?.active_agent_task
    const taskActive = !!t && (t.status === 'pending' || t.status === 'running')
    return taskActive || !!workflowRef.value?.phaseInFlight
  })
  watch(agentLocked, (locked, wasLocked) => {
    if (!locked && wasLocked) onAgentFinished()
  })

  // The shared agent banner: any agent outside the design stage (where the
  // per-design banners speak for it), or a worker waiting on a person.
  const agentRunning = computed(() => {
    const wf = workflowRef.value
    return Boolean((wf?.agentGenerating && bud.value?.status !== 'design') || wf?.awaitingDecision)
  })

  const generatingDesigns = computed(() => bud.value?.designs?.filter(d => d.status === 'generating') ?? [])

  return { agentLocked, agentRunning, generatingDesigns }
}
