/**
 * Local types for tree dashboard panels.
 * These were previously defined in the Three.js garden/ system.
 * Now standalone for use by PlayCanvas engine callbacks and detail panels.
 */
import type { MemberActivity } from '@/types/dashboard'

export type HouseActivity = 'sleeping' | 'home' | 'away' | 'coffee_bar' | 'cafeteria'

export interface HouseInfo {
  name: string
  activity: HouseActivity
}

export interface CharacterInfo {
  name: string
  modelName: string
  isAgent: boolean
  careMode: 'water' | 'fertilizer' | null
  member: MemberActivity | null
  clipNames: string[]
}
