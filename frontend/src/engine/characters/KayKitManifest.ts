/**
 * KayKitManifest — Character definitions for KayKit Adventurers pack.
 *
 * Each character has a unique id, display name, GLB path, thumbnail, and lock state.
 * Lock state is visual-only in V1 (no unlock logic yet — reserved for XP system).
 *
 * Animation categories map to the KayKit Animation GLBs, split by function.
 * All free-tier characters use the Rig_Medium skeleton.
 */

// ─── Character Definitions ─────────────────────

export interface KayKitCharacterDef {
  /** Unique identifier used in character_model encoding. */
  id: string
  /** Display name shown in the selection UI. */
  name: string
  /** Path to the character GLB (relative to public root). */
  glb: string
  /** Path to the thumbnail preview image. */
  thumbnail: string
  /** If true, shows a lock icon in the selection UI (V1: visual only). */
  locked: boolean
}

const BASE = 'characters/kaykit'

const CHARACTERS: KayKitCharacterDef[] = [
  { id: 'barbarian',    name: 'Barbarian',    glb: `${BASE}/characters/barbarian.glb`,     thumbnail: `${BASE}/thumbnails/barbarian.png`,     locked: false },
  { id: 'knight',       name: 'Knight',       glb: `${BASE}/characters/knight.glb`,        thumbnail: `${BASE}/thumbnails/knight.png`,        locked: false },
  { id: 'mage',         name: 'Mage',         glb: `${BASE}/characters/mage.glb`,          thumbnail: `${BASE}/thumbnails/mage.png`,          locked: false },
  { id: 'ranger',       name: 'Ranger',       glb: `${BASE}/characters/ranger.glb`,        thumbnail: `${BASE}/thumbnails/ranger.png`,        locked: false },
  { id: 'rogue',        name: 'Rogue',        glb: `${BASE}/characters/rogue.glb`,         thumbnail: `${BASE}/thumbnails/rogue.png`,         locked: false },
  { id: 'rogue_hooded', name: 'Rogue Hooded', glb: `${BASE}/characters/rogue_hooded.glb`,  thumbnail: `${BASE}/thumbnails/rogue_hooded.png`,  locked: false },
]

export function getCharacterDef(id: string): KayKitCharacterDef | undefined {
  return CHARACTERS.find(c => c.id === id)
}

export function getAllCharacters(): readonly KayKitCharacterDef[] {
  return CHARACTERS
}

export function getUnlockedCharacters(): KayKitCharacterDef[] {
  return CHARACTERS.filter(c => !c.locked)
}

// ─── Animation Categories ──────────────────────

export type AnimationCategory =
  | 'general'
  | 'movement_basic'
  | 'movement_advanced'
  | 'simulation'
  | 'tools'
  | 'combat_melee'
  | 'combat_ranged'
  | 'special'

const ANIMATION_GLBS: Record<AnimationCategory, string> = {
  general:           `${BASE}/animations/general.glb`,
  movement_basic:    `${BASE}/animations/movement_basic.glb`,
  movement_advanced: `${BASE}/animations/movement_advanced.glb`,
  simulation:        `${BASE}/animations/simulation.glb`,
  tools:             `${BASE}/animations/tools.glb`,
  combat_melee:      `${BASE}/animations/combat_melee.glb`,
  combat_ranged:     `${BASE}/animations/combat_ranged.glb`,
  special:           `${BASE}/animations/special.glb`,
}

export function getAnimationGLB(category: AnimationCategory): string {
  return ANIMATION_GLBS[category]
}

/** Animation categories needed for the garden engine (idle, walk, sit). */
export const CORE_ANIMATION_CATEGORIES: AnimationCategory[] = [
  'general',
  'movement_basic',
  'simulation',
]

export function getCoreAnimationGLBs(): string[] {
  return CORE_ANIMATION_CATEGORIES.map(c => ANIMATION_GLBS[c])
}

// ─── Accessories ───────────────────────────────

export type AccessorySlot = 'right_hand' | 'left_hand'

/** Bone names in the KayKit Rig_Medium skeleton for accessory attachment. */
export const SLOT_BONE_NAMES: Record<AccessorySlot, string> = {
  right_hand: 'handslot.r',
  left_hand:  'handslot.l',
}

export interface KayKitAccessoryDef {
  id: string
  name: string
  glb: string
  slot: AccessorySlot
  locked: boolean
}

const ACCESSORIES: KayKitAccessoryDef[] = [
  { id: 'sword',   name: 'Sword',     glb: `${BASE}/accessories/sword_1handed.glb`, slot: 'right_hand', locked: false },
  { id: 'axe',     name: 'Axe',       glb: `${BASE}/accessories/axe_1handed.glb`,   slot: 'right_hand', locked: false },
  { id: 'dagger',  name: 'Dagger',    glb: `${BASE}/accessories/dagger.glb`,        slot: 'right_hand', locked: false },
  { id: 'staff',   name: 'Staff',     glb: `${BASE}/accessories/staff.glb`,         slot: 'right_hand', locked: false },
  { id: 'wand',    name: 'Wand',      glb: `${BASE}/accessories/wand.glb`,          slot: 'right_hand', locked: false },
  { id: 'bow',     name: 'Bow',       glb: `${BASE}/accessories/bow.glb`,           slot: 'right_hand', locked: false },
  { id: 'shield',  name: 'Shield',    glb: `${BASE}/accessories/shield_badge.glb`,  slot: 'left_hand',  locked: false },
  { id: 'mug',     name: 'Coffee Mug',glb: `${BASE}/accessories/mug_full.glb`,      slot: 'right_hand', locked: false },
]

export function getAccessoryDef(id: string): KayKitAccessoryDef | undefined {
  return ACCESSORIES.find(a => a.id === id)
}

export function getAllAccessories(): readonly KayKitAccessoryDef[] {
  return ACCESSORIES
}

export function getAccessoriesForSlot(slot: AccessorySlot): KayKitAccessoryDef[] {
  return ACCESSORIES.filter(a => a.slot === slot)
}
