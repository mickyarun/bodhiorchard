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
  id: string
  name: string
  glb: string
  thumbnail: string
  locked: boolean
  /** Minimum level required to unlock. Used for UI badge display. */
  unlockLevel: number
  /** Level name for unlock tooltip (e.g., "Sprout"). */
  unlockName: string
}

const BASE = 'characters/kaykit'

const CHARACTERS: KayKitCharacterDef[] = [
  { id: 'barbarian',    name: 'Barbarian',    glb: `${BASE}/characters/barbarian.glb`,     thumbnail: `${BASE}/thumbnails/barbarian.png`,     locked: false, unlockLevel: 1, unlockName: 'Seedling' },
  { id: 'knight',       name: 'Knight',       glb: `${BASE}/characters/knight.glb`,        thumbnail: `${BASE}/thumbnails/knight.png`,        locked: false, unlockLevel: 1, unlockName: 'Seedling' },
  { id: 'mage',         name: 'Mage',         glb: `${BASE}/characters/mage.glb`,          thumbnail: `${BASE}/thumbnails/mage.png`,          locked: false, unlockLevel: 2, unlockName: 'Sprout' },
  { id: 'ranger',       name: 'Ranger',       glb: `${BASE}/characters/ranger.glb`,        thumbnail: `${BASE}/thumbnails/ranger.png`,        locked: false, unlockLevel: 3, unlockName: 'Sapling' },
  { id: 'rogue',        name: 'Rogue',        glb: `${BASE}/characters/rogue.glb`,         thumbnail: `${BASE}/thumbnails/rogue.png`,         locked: false, unlockLevel: 4, unlockName: 'Tree' },
  { id: 'rogue_hooded', name: 'Rogue Hooded', glb: `${BASE}/characters/rogue_hooded.glb`,  thumbnail: `${BASE}/thumbnails/rogue_hooded.png`,  locked: false, unlockLevel: 5, unlockName: 'Ancient Oak' },
]

export function getCharacterDef(id: string): KayKitCharacterDef | undefined {
  return CHARACTERS.find(c => c.id === id)
}

export function getAllCharacters(): readonly KayKitCharacterDef[] {
  return CHARACTERS
}

/** Return characters with lock state based on unlocked IDs from XP system. */
export function getCharactersWithUnlocks(unlockedIds: Set<string>): KayKitCharacterDef[] {
  return CHARACTERS.map(c => ({ ...c, locked: !unlockedIds.has(c.id) }))
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
  icon: string
  glb: string
  slot: AccessorySlot
  locked: boolean
}

const ACCESSORIES: KayKitAccessoryDef[] = [
  { id: 'sword',   name: 'Sword',      icon: 'mdi-sword',                glb: `${BASE}/accessories/sword_1handed.glb`, slot: 'right_hand', locked: false },
  { id: 'axe',     name: 'Axe',        icon: 'mdi-axe',                  glb: `${BASE}/accessories/axe_1handed.glb`,   slot: 'right_hand', locked: false },
  { id: 'dagger',  name: 'Dagger',     icon: 'mdi-knife-military',       glb: `${BASE}/accessories/dagger.glb`,        slot: 'right_hand', locked: false },
  { id: 'staff',   name: 'Staff',      icon: 'mdi-magic-staff',          glb: `${BASE}/accessories/staff.glb`,         slot: 'right_hand', locked: false },
  { id: 'wand',    name: 'Wand',       icon: 'mdi-auto-fix',             glb: `${BASE}/accessories/wand.glb`,          slot: 'right_hand', locked: false },
  { id: 'bow',     name: 'Bow',        icon: 'mdi-bow-arrow',            glb: `${BASE}/accessories/bow.glb`,           slot: 'right_hand', locked: false },
  { id: 'shield',  name: 'Shield',     icon: 'mdi-shield',               glb: `${BASE}/accessories/shield_badge.glb`,  slot: 'left_hand',  locked: false },
  { id: 'mug',     name: 'Coffee Mug', icon: 'mdi-coffee',               glb: `${BASE}/accessories/mug_full.glb`,      slot: 'right_hand', locked: false },
]

export function getAccessoryDef(id: string): KayKitAccessoryDef | undefined {
  return ACCESSORIES.find(a => a.id === id)
}

export function getAllAccessories(): readonly KayKitAccessoryDef[] {
  return ACCESSORIES
}

/** Return accessories with lock state based on unlocked IDs from XP system. */
export function getAccessoriesWithUnlocks(
  slot: AccessorySlot,
  unlockedIds: Set<string>,
): KayKitAccessoryDef[] {
  return ACCESSORIES
    .filter(a => a.slot === slot)
    .map(a => ({ ...a, locked: !unlockedIds.has(a.id) }))
}

export function getAccessoriesForSlot(slot: AccessorySlot): KayKitAccessoryDef[] {
  return ACCESSORIES.filter(a => a.slot === slot)
}
