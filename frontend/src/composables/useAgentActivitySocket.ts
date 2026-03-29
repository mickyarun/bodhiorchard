/**
 * Composable for subscribing to real-time agent activity WebSocket events.
 *
 * Subscribes to `agent_activity:{orgId}` topic. When the backend receives
 * a Claude Code hook event, it publishes to this topic. The callback
 * forwards the event to the 3D engine for live robot spawn/update/remove.
 */
import { onUnmounted } from 'vue'
import { subscribe, unsubscribe } from '@/services/socket'
import type { EngineAgentActivity } from '@/engine/types'

export function useAgentActivitySocket(
  orgId: string,
  onEvent: (activity: EngineAgentActivity) => void,
) {
  const topic = `agent_activity:${orgId}`

  function onMessage(data: unknown): void {
    const raw = data as Record<string, unknown>
    const activity: EngineAgentActivity = {
      agent_name: (raw.actor_name as string) || (raw.skill_slug as string) || 'agent',
      action: (raw.message as string) || '',
      timestamp: (raw.created_at as string) || '',
      status: (raw.status as string) || 'in_progress',
      skill_slug: (raw.skill_slug as string) || '',
      repo_name: (raw.repo_name as string) || null,
      bud_number: (raw.bud_number as number) || null,
      session_id: (raw.session_id as string) || null,
      event_type: (raw.event_type as string) || '',
      task_id: (raw.task_id as string) || null,
      bud_title: (raw.bud_title as string) || null,
      impacted_repo_names: (raw.impacted_repo_names as string[]) || [],
    }
    onEvent(activity)
  }

  subscribe(topic, onMessage)

  onUnmounted(() => {
    unsubscribe(topic, onMessage)
  })

  return { topic }
}
