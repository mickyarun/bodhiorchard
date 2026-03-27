/**
 * DemoFeatures — mock feature data for the tree demo.
 *
 * No PlayCanvas dependency. Pure data generation.
 * Status colors match the main FeatureSystem in the garden engine.
 */
import type { Color3 } from './TreeRules'

export interface DemoFeature {
  title:  string
  status: 'planned' | 'in_progress' | 'implemented'
}

export const STATUS_COLOR: Record<DemoFeature['status'], Color3> = {
  planned:     [ 60, 200,  80],
  in_progress: [240, 150,  40],
  implemented: [220,  50,  50],
}

/** Map a feature list to Color3 values for Tree3DSystem.setFeatureColors(). */
export function featureColors(features: DemoFeature[]): Color3[] {
  return features.map(f => STATUS_COLOR[f.status])
}

// ─── Mock Generation ─────────────────────────────────────────────────────────

const WORDS_A = [
  'Auth', 'Payment', 'Search', 'Export', 'Import', 'User', 'Audit',
  'Report', 'Notify', 'Cache', 'Queue', 'Media', 'Chart', 'Admin',
  'Invite', 'Config', 'Token', 'Webhook', 'Access', 'Session',
]
const WORDS_B = [
  'Flow', 'API', 'Index', 'Layer', 'Profile', 'Log', 'Module',
  'Service', 'Panel', 'Handler', 'Pipeline', 'Guard', 'Store',
  'Router', 'Sync', 'Stream', 'Hook', 'Schema', 'Policy', 'Worker',
]

/** Deterministic seeded pseudo-random (xorshift32). Same count → same names. */
function xor32(seed: number): () => number {
  let s = seed >>> 0 || 1
  return () => {
    s ^= s << 13; s ^= s >>> 17; s ^= s << 5
    return (s >>> 0) / 0xffffffff
  }
}

const STATUS_POOL: DemoFeature['status'][] = [
  'planned', 'planned', 'planned', 'planned',
  'in_progress', 'in_progress', 'in_progress',
  'implemented', 'implemented',
]

/**
 * Generate N mock features with deterministic names (seeded by count)
 * and a realistic status distribution (~40% planned, 35% in_progress, 25% implemented).
 */
export function generateFeatures(count: number): DemoFeature[] {
  const rand = xor32(count * 7919)
  const used = new Set<string>()
  const out:  DemoFeature[] = []

  for (let i = 0; i < count; i++) {
    let title: string
    let tries = 0
    do {
      title = `${WORDS_A[Math.floor(rand() * WORDS_A.length)]} ${WORDS_B[Math.floor(rand() * WORDS_B.length)]}`
      tries++
    } while (used.has(title) && tries < 20)
    used.add(title)
    out.push({ title, status: STATUS_POOL[Math.floor(rand() * STATUS_POOL.length)] })
  }
  return out
}
